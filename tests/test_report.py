import logging
import os
import tempfile
import threading
import unittest
from datetime import date, datetime

from finnfinn import config, db, report, tg

logging.disable(logging.CRITICAL)
WIB = config.WIB
TX = {"jenis": "keluar", "jumlah": 35000, "kategori": "Makanan & Minuman", "subkategori": "Makan di luar",
      "catatan": "Nasi padang", "tanggal": "2026-09-06", "waktu": "14:03"}


def at(y, m, d, hh, mm, ss=0):
    return datetime(y, m, d, hh, mm, ss, tzinfo=WIB)


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.init(os.path.join(self.tmp.name, "t.db"))
        self.saved = (config.OWNER_IDS, config.FIRST_OWNER, config.DB_PATH, tg.tg_send, report.HARIAN_AT, report._alert_at)
        config.OWNER_IDS, config.FIRST_OWNER, config.DB_PATH = {1, 2}, 1, db._path
        report.HARIAN_AT, report._alert_at = "23:00", None
        self.sent = []
        tg.tg_send = lambda chat_id, text, parse_mode="HTML", buttons=None: self.sent.append((chat_id, text)) or {"result": {"message_id": 1}}

    def tearDown(self):
        config.OWNER_IDS, config.FIRST_OWNER, config.DB_PATH, tg.tg_send, report.HARIAN_AT, report._alert_at = self.saved
        db.close()
        self.tmp.cleanup()

    def kinds(self, now):
        return [(k, key) for k, key, _ in report.due(now)]

    def keys(self, now, kind):
        return [key for k, key, _ in report.due(now) if k == kind]

    # ---------- periods ----------

    def test_labels(self):
        self.assertEqual(report.tanggal(date(2026, 9, 6)), "Min, 6 Sep 2026")
        self.assertEqual(report.tanggal(date(2026, 9, 5), year=False), "Sab, 5 Sep")
        self.assertEqual(report._rentang(date(2025, 12, 29), date(2026, 1, 4)), "29 Des–4 Jan 2026")
        self.assertEqual(report._rentang(date(2026, 8, 31), date(2026, 9, 6)), "31 Agu–6 Sep 2026")
        self.assertEqual(report._rentang(date(2026, 9, 7), date(2026, 9, 13)), "7–13 Sep 2026")
        self.assertEqual(report.rp(-187500), "−Rp 187.500")
        self.assertEqual([report.short(n) for n in (43000, 320000, 1200000, 1000000, 0)], ["43rb", "320rb", "1,2jt", "1jt", "0"])

    def test_due_harian_and_backup(self):
        self.assertEqual(self.kinds(at(2026, 9, 10, 22, 59, 59)), [])
        self.assertEqual(self.kinds(at(2026, 9, 10, 23, 0, 30)), [("harian", "2026-09-10")])
        self.assertEqual(self.kinds(at(2026, 9, 10, 23, 7)), [("harian", "2026-09-10")])  # same-day catch-up after a miss
        self.assertEqual(self.kinds(at(2026, 9, 10, 23, 31)), [("harian", "2026-09-10"), ("backup", "2026-09-10")])
        self.assertEqual(self.kinds(at(2026, 9, 11, 0, 10)), [])  # yesterday's misses are not caught up
        report.HARIAN_AT = "10:00"  # REPORT_TIME_OVERRIDE
        self.assertEqual(self.kinds(at(2026, 9, 11, 10, 0, 5)), [("harian", "2026-09-11")])

    def test_due_weekly_window(self):
        self.assertEqual(date(2026, 1, 4).weekday(), 6)  # Mon 29 Dec 2025 – Sun 4 Jan 2026 = ISO week 2026-W01
        self.assertEqual(self.keys(at(2026, 1, 3, 23, 5), "mingguan"), [])
        self.assertEqual(self.keys(at(2026, 1, 4, 23, 4, 59), "mingguan"), [])
        self.assertEqual(self.keys(at(2026, 1, 4, 23, 5), "mingguan"), ["2026-W01"])
        self.assertEqual(self.keys(at(2026, 1, 7, 23, 4), "mingguan"), ["2026-W01"])  # 3-day window still open
        self.assertEqual(self.keys(at(2026, 1, 7, 23, 5), "mingguan"), [])  # closed: skipped
        self.assertEqual(self.kinds(at(2026, 9, 6, 23, 31)),
                         [("harian", "2026-09-06"), ("backup", "2026-09-06"), ("mingguan", "2026-W36")])

    def test_due_last_day_and_new_year(self):
        self.assertEqual(self.keys(at(2026, 2, 27, 23, 10), "bulanan"), [])
        self.assertEqual(self.keys(at(2026, 2, 28, 23, 10), "bulanan"), ["2026-02"])
        self.assertEqual(self.keys(at(2028, 2, 28, 23, 10), "bulanan"), [])
        self.assertEqual(self.keys(at(2028, 2, 29, 23, 10), "bulanan"), ["2028-02"])
        self.assertEqual(self.keys(at(2026, 12, 31, 23, 10), "bulanan"), ["2026-12"])
        self.assertEqual(self.keys(at(2026, 12, 31, 23, 9), "bulanan"), [])
        self.assertEqual(self.kinds(at(2026, 1, 1, 8, 0)), [("tahunan", "2025"), ("bulanan", "2025-12")])
        self.assertEqual(self.kinds(at(2026, 1, 1, 7, 59)), [("bulanan", "2025-12")])
        self.assertEqual(self.keys(at(2026, 1, 4, 8, 0), "tahunan"), [])  # 3 days later: skipped
        self.assertEqual(self.keys(at(2026, 1, 4, 7, 59), "tahunan"), ["2025"])

    def test_guest_only_instance(self):
        config.OWNER_IDS, config.FIRST_OWNER = set(), None
        db.guest_upsert(42)
        db.guest_set_remind(42, True)
        self.assertEqual(self.kinds(at(2026, 9, 6, 23, 5)), [("pengingat", "2026-09-06:42")])

    # ---------- ticker ----------

    def test_tick_exactly_once(self):
        report.tick(at(2026, 9, 6, 23, 0, 30))
        self.assertEqual([c for c, _ in self.sent], [1, 2])
        self.assertTrue(self.sent[0][1].startswith("🌙 <b>Laporan Harian — Min, 6 Sep 2026</b>"))
        report.tick(at(2026, 9, 6, 23, 1))  # restart / next pass: claimed already
        self.assertEqual(len(self.sent), 2)

    def failing(self, fail, desc):
        def send(chat_id, text, parse_mode="HTML", buttons=None):
            self.sent.append((chat_id, text))
            if chat_id in fail:
                raise RuntimeError(desc)
            return {"result": {"message_id": 1}}
        tg.tg_send = send

    def test_tick_transient_failure_unclaims_and_alerts(self):
        self.failing({1, 2}, "Bad Gateway")
        report.tick(at(2026, 9, 6, 23, 0, 30))
        self.assertTrue(db.claim("harian", "2026-09-06"))  # every owner failed → unclaimed → the same-day window retries
        self.assertTrue(self.sent[-1][1].startswith("⚠️ Finn Finn error: RuntimeError: Bad Gateway"))

    def test_tick_terminal_failure_keeps_claim(self):
        self.failing({1, 2}, "Forbidden: bot was blocked by the user")
        report.tick(at(2026, 9, 6, 23, 0, 30))
        report.tick(at(2026, 9, 6, 23, 1))
        harian = [c for c, t in self.sent if t.startswith("🌙")]
        self.assertEqual(harian, [1, 2])  # a 4xx is not retried on the next pass
        self.assertFalse(db.claim("harian", "2026-09-06"))
        self.assertEqual(sum(t.startswith("⚠️") for _, t in self.sent), 1)

    def test_tick_partial_failure_never_resends(self):
        self.failing({2}, "Bad Gateway")
        report.tick(at(2026, 9, 6, 23, 0, 30))
        report.tick(at(2026, 9, 6, 23, 1))
        self.assertEqual([c for c, t in self.sent if t.startswith("🌙")], [1, 2])  # owner 1 got it exactly once
        self.assertFalse(db.claim("harian", "2026-09-06"))
        self.assertTrue(self.sent[-1][1].startswith("⚠️ Finn Finn error: RuntimeError: Bad Gateway"))

    def test_reminder_dead_chat_deletes_guest(self):
        for g in (41, 42, 43):
            db.guest_upsert(g)
            db.guest_set_remind(g, True)
        descs = {41: "Bad Request: chat not found", 42: "Forbidden: bot was blocked by the user"}

        def send(chat_id, text, parse_mode="HTML", buttons=None):
            self.sent.append((chat_id, text))
            if chat_id in descs:
                raise RuntimeError(descs[chat_id])
            return {"result": {"message_id": 1}}
        tg.tg_send = send
        report.tick(at(2026, 9, 6, 23, 0, 30))
        self.assertEqual(db.guests_to_remind(), [43])
        self.assertIn((43, report.REMINDER), self.sent)
        self.assertFalse(db.claim("pengingat", "2026-09-06:42"))  # a dead chat is a completed job, not a retry
        self.assertFalse(db.claim("pengingat", "2026-09-06:41"))
        self.assertFalse(any(t.startswith("⚠️") for _, t in self.sent))

    def test_loop_idle_pass_refreshes_last_tick(self):
        db.meta_set("last_tick", "2026-01-01T00:00:00+07:00")  # stale boot: only a log line, nothing claimed
        before = report.last_tick
        stop = threading.Event()
        threading.Timer(0.05, stop.set).start()
        report.loop(stop)
        self.assertGreater(report.last_tick, before)
        self.assertRegex(db.meta_get("last_tick"), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+07:00$")
        self.assertTrue(db.claim("mingguan", "2026-W35"))

    # ---------- builders ----------

    def test_harian(self):
        db.add_tx({**TX, "jumlah": 87500, "catatan": "Indomaret", "waktu": "19:42"})
        db.add_tx({**TX, "jumlah": 45000, "kategori": "Transportasi", "subkategori": "Ojek-Taxi", "catatan": "Ojek-Taxi"})
        db.add_tx({**TX, "jumlah": 25000, "catatan": "Kopi"})
        db.add_tx({**TX, "jumlah": 30000, "catatan": "Roti"})
        db.add_tx({**TX, "jumlah": 10000, "tanggal": "2026-09-05"})
        text = report.build_harian(date(2026, 9, 6))
        self.assertEqual(text, "🌙 <b>Laporan Harian — Min, 6 Sep 2026</b>\n\n"
                               "💸 Keluar: Rp 187.500 (4 transaksi)\n💰 Masuk: Rp 0\n📉 Selisih: −Rp 187.500\n\n"
                               "Terbesar hari ini:\n1. 🍽 Makan di luar — Rp 87.500 · Indomaret\n2. 🚗 Ojek-Taxi — Rp 45.000\n"
                               "3. 🍽 Makan di luar — Rp 30.000 · Roti\n\n"
                               "📊 Minggu ini: keluar Rp 197.500 · Bulan ini: Rp 197.500")
        self.assertIn("Hari ini belum ada catatan 🙂 Kalau ada yang terlewat, ketik saja sekarang — misalnya <code>25000 makan siang</code>.",
                      report.build_harian(date(2026, 9, 7)))

    def test_mingguan(self):
        for d, n in zip(("08-31", "09-01", "09-02", "09-03", "09-04", "09-05", "09-06"), (320000, 150000, 240000, 80000, 410000, 187000, 43000)):
            db.add_tx({**TX, "jumlah": n, "tanggal": "2026-" + d})
        db.add_tx({**TX, "jenis": "masuk", "jumlah": 7500000, "kategori": "Gaji", "subkategori": "Umum", "tanggal": "2026-09-01"})
        db.add_tx({**TX, "jumlah": 1000000, "tanggal": "2026-08-25"})
        text = report.build_mingguan(date(2026, 8, 31))
        self.assertTrue(text.startswith("📆 <b>Laporan Mingguan — 31 Agu–6 Sep 2026</b>\n💰 Masuk Rp 7.500.000 · 💸 Keluar Rp 1.430.000\n"
                                        "✅ Surplus Rp 6.070.000 (81% tersimpan)\n\n"))
        self.assertIn("<pre>Traffic harian (keluar)\nSen ▇▇▇▇   320rb\nSel ▇▇     150rb\nRab ▇▇▇    240rb\nKam ▇       80rb\n"
                      "Jum ▇▇▇▇▇  410rb\nSab ▇▇     187rb\nMin ▇       43rb</pre>\nPer kategori:\n"
                      "🍽 Makanan &amp; Minuman  Rp 1.430.000 (100%)", text)
        self.assertTrue(text.endswith("\n\nvs minggu lalu: keluar ▲ 43% 👀\n"
                                       "💡 Tip Mingguan: Coba kurangi pengeluaran di sektor Makanan &amp; Minuman untuk minggu depan, ya!"))

    def test_bulanan_and_tahunan(self):
        db.add_tx({**TX, "jumlah": 1200000, "tanggal": "2026-01-15"})
        db.add_tx({**TX, "jumlah": 300000, "tanggal": "2026-02-02", "kategori": "Transportasi", "subkategori": "BBM"})
        db.meta_set("nama", "Donny")
        b = report.build_bulanan(2026, 2)
        self.assertTrue(b.startswith("🗓 <b>Laporan Bulanan — Februari 2026</b>\n💰 Masuk Rp 0 · 💸 Keluar Rp 300.000\n⚠️ Defisit Rp 300.000\n"
                                     "📅 Rata-rata harian: Rp 10.714\n\n<pre>Traffic mingguan (keluar)\nW1 ▇▇▇▇▇  300rb\nW2 "))
        self.assertIn("\nTop 5 sub-kategori:\n1. 🚗 BBM — Rp 300.000 (100%)\n🔥 Hari terboros: Sen, 2 Feb (Rp 300.000)\n\n"
                      "vs bulan lalu: keluar ▼ 75% 👍", b)
        t = report.build_tahunan(2026)
        self.assertIn("<pre>Traffic bulanan (keluar)\nJan ▇▇▇▇▇  1,2jt\nFeb ▇      300rb\nMar            0\n", t)
        self.assertIn("🌱 Bulan paling hemat: Feb (Rp 300.000)\n🔥 Bulan paling boros: Jan (Rp 1.200.000)\nTop 3 kategori:\n", t)
        self.assertTrue(t.endswith("Selamat tahun baru, Donny! Tahun ini kita catat lebih rapi lagi 🌱"))
        today = datetime.now(WIB).date()  # on-demand /bulan mid-month averages over the elapsed days only
        db.add_tx({**TX, "jumlah": 90000, "tanggal": today.replace(day=1).isoformat()})
        keluar = report.sums(today.replace(day=1).isoformat(), today.isoformat())[1]
        self.assertIn(f"📅 Rata-rata harian: {report.rp(keluar // today.day)}\n", report.build_bulanan(today.year, today.month))

    def test_sisa_kuota_harian(self):
        self.assertIsNone(report.sisa_kuota_harian(date(2026, 9, 6)))  # no budget set
        db.meta_set("budget_bulanan", "3000000")  # 3jt / 30 hari = 100rb/hari
        self.assertEqual(report.sisa_kuota_harian(date(2026, 9, 6)), 600000)  # day 6, no spending yet
        db.add_tx({**TX, "jumlah": 100000, "tanggal": "2026-09-06"})
        self.assertEqual(report.sisa_kuota_harian(date(2026, 9, 6)), 500000)
        text = report.build_harian(date(2026, 9, 6))
        self.assertIn("💡 Sisa Kuota Harianmu: Rp 500.000\n", text)
        db.add_tx({**TX, "jumlah": 900000, "tanggal": "2026-09-06"})
        self.assertIn("⚠️ Kuota harianmu sudah lewat Rp 400.000\n", report.build_harian(date(2026, 9, 6)))

    def test_bulanan_disisihkan_and_budgetbaru_hint(self):
        db.add_tx({**TX, "jenis": "masuk", "jumlah": 5000000, "kategori": "Gaji", "subkategori": "Umum", "tanggal": "2026-09-01"})
        db.add_tx({**TX, "jumlah": 2000000, "tanggal": "2026-09-01"})
        text = report.build_bulanan(2026, 9)
        self.assertTrue(text.endswith("🏦 Disisihkan (Tabungan/Investasi): Rp 3.000.000\n"
                                       "📣 Siap merencanakan budget bulan depan? Ketik <code>/budgetbaru [nominal]</code> untuk mulai!"))

    def test_backup_prunes(self):
        bdir = os.path.join(self.tmp.name, "backups")
        os.makedirs(bdir)
        for n in range(15):
            open(os.path.join(bdir, f"finnfinn-202608{n + 10:02d}.db"), "w").close()
        db.add_tx(TX)
        dest = report.backup(date(2026, 9, 6))
        self.assertEqual(dest, os.path.join(bdir, "finnfinn-20260906.db"))
        left = sorted(os.listdir(bdir))
        self.assertEqual(len(left), 14)
        self.assertEqual(left[0], "finnfinn-20260812.db")
        self.assertEqual(left[-1], "finnfinn-20260906.db")


if __name__ == "__main__":
    unittest.main()
