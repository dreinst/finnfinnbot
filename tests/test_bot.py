import json
import logging
import os
import tempfile
import threading
import time
import unittest
from datetime import timedelta
from pathlib import Path

from finnfinn import bot, config, db, ocr, report, tg

logging.disable(logging.CRITICAL)
OWNER, GUEST = 1, 2
FIX = Path(__file__).parent / "fixtures" / "receipts"


def msg(uid, text=None, chat_type="private", **extra):
    m = {"message_id": 7, "date": int(time.time()), "chat": {"id": uid if chat_type == "private" else -100, "type": chat_type},
         "from": {"id": uid, "first_name": "Donny <3"}}
    if text is not None:
        m["text"] = text
    m.update(extra)
    return {"update_id": 1, "message": m}


def cb(uid, data, mid):
    return {"update_id": 2, "callback_query": {"id": "q1", "from": {"id": uid}, "data": data,
                                               "message": {"message_id": mid, "chat": {"id": uid, "type": "private"}}}}


PHOTO = {"photo": [{"file_id": "small", "width": 90, "height": 120, "file_size": 1000},
                   {"file_id": "big", "width": 900, "height": 1200, "file_size": 90000}]}
if not hasattr(ocr, "LOCK"):  # Phase 0 stub (pre-1C merge): the real ocr.py defines both
    ocr.LOCK, ocr.Busy = threading.Lock(), type("Busy", (Exception,), {})


class BotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.init(os.path.join(self.tmp.name, "t.db"))
        self.saved = (config.OWNER_IDS, config.FIRST_OWNER, config.OCR_ENABLED, tg.tg_send, tg.tg_edit, tg.tg_answer_cb,
                      tg.tg_get_file, tg.tg_send_document, ocr.run, report._alert_at)
        config.OWNER_IDS, config.FIRST_OWNER, config.OCR_ENABLED, report._alert_at = {OWNER}, OWNER, True, None
        self.sent, self.edited, self.answered, self.files, self.n = [], [], [], [], 100
        tg.tg_send = self.send
        tg.tg_edit = lambda chat_id, msg_id, text=None, buttons=None, parse_mode="HTML": self.edited.append((chat_id, msg_id, text, buttons))
        tg.tg_answer_cb = lambda cb_id, text=None: self.answered.append(text)
        tg.tg_get_file = lambda file_id, max_bytes: self.files.append(file_id) or b"img"
        ocr.run = lambda img: (FIX / "01.txt").read_text().splitlines()
        bot.drafts.clear()
        bot._guest_seen.clear()

    def tearDown(self):
        (config.OWNER_IDS, config.FIRST_OWNER, config.OCR_ENABLED, tg.tg_send, tg.tg_edit, tg.tg_answer_cb,
         tg.tg_get_file, tg.tg_send_document, ocr.run, report._alert_at) = self.saved
        db.close()
        self.tmp.cleanup()

    def send(self, chat_id, text, parse_mode="HTML", buttons=None):
        self.n += 1
        self.sent.append((chat_id, text, buttons))
        return {"result": {"message_id": self.n}}

    def photo(self, uid, **extra):
        bot.handle_update(msg(uid, **PHOTO, **extra))
        for t in threading.enumerate():
            if t.name == "ocr":
                t.join(5)

    def last_edit(self):
        return self.edited[-1]

    # ---------- /start ----------

    def test_start_owner_vs_guest(self):
        bot.handle_update(msg(OWNER, "/start"))
        chat, text, buttons = self.sent[-1]
        self.assertEqual(chat, OWNER)
        self.assertTrue(text.startswith("Halo Donny &lt;3! 👋 Aku <b>Finn Finn</b>, pencatat keuangan pribadimu.\n\nCara pakai:\n"))
        self.assertTrue(text.endswith("ringkasan tahunan tiap tahun baru 🎉"))
        self.assertEqual(buttons, [["📝 Catat Pengeluaran"], ["📊 Lihat Pengeluaran"]])
        self.assertEqual(db.meta_get("nama"), "Donny <3")
        self.assertFalse(db.guest_known(OWNER))
        bot.handle_update(msg(GUEST, "/start"))
        chat, text, buttons = self.sent[-1]
        self.assertEqual(chat, GUEST)
        self.assertTrue(text.startswith("Halo Donny &lt;3! 👋 Aku <b>Finn Finn</b>.\nUntuk kamu, semua catatan disimpan <b>di akun Telegram-mu sendiri</b>"))
        self.assertTrue(text.endswith("lewat aplikasi di bawah ini 👇" + report.LINK))  # http WEBAPP_URL: plain link, no web_app button
        self.assertEqual(buttons[-1], [{"text": "🔔 Ingatkan aku tiap malam (23.00 WIB)", "callback_data": "r:1"}])
        self.assertTrue(db.guest_known(GUEST))
        self.assertEqual(db.guests_to_remind(), [])

    # ---------- free text → kategori → sub → simpan → hapus ----------

    def test_free_text_flow(self):
        bot.handle_update(msg(OWNER, "50000 kopi"))
        chat, text, buttons = self.sent[-1]
        self.assertTrue(text.startswith("❤️ <b>Pengeluaran</b> Rp 50.000 — <i>Kopi</i>\n📅 "))
        self.assertTrue(text.endswith("\n\nPilih kategori:"))
        self.assertEqual(buttons[0][0], {"text": "✅ Makanan & Minuman", "callback_data": "c:0"})
        self.assertEqual([b["callback_data"] for b in buttons[-1]], ["e:t", "x"])
        mid = bot.drafts[OWNER]["msg_id"]
        self.assertEqual(bot.drafts[OWNER]["step"], bot.PICK_KATEGORI)

        bot.handle_update(cb(OWNER, "c:0", mid))
        _, m, text, buttons = self.last_edit()
        self.assertEqual((m, text), (mid, "Kategori: <b>Makanan &amp; Minuman</b>\nPilih sub-kategori:"))
        self.assertEqual(buttons[0], [{"text": "✅ Makan di luar", "callback_data": "s:0"}, {"text": "Groceries", "callback_data": "s:1"}])
        self.assertEqual([b["callback_data"] for b in buttons[-1]], ["b:c", "x"])

        bot.handle_update(cb(OWNER, "s:0", mid))
        _, _, text, buttons = self.last_edit()
        self.assertTrue(text.startswith("Cek dulu ya 👇\n❤️ <b>Pengeluaran</b> Rp 50.000\n📂 Makanan &amp; Minuman › Makan di luar\n📝 Kopi\n📅 "))
        self.assertEqual([[b["callback_data"] for b in row] for row in buttons], [["ok"], ["e:j", "b:c"], ["x"]])

        bot.handle_update(cb(OWNER, "ok", mid))
        rows = db.list_tx("2000-01-01", "2100-01-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["jumlah"], rows[0]["kategori"], rows[0]["subkategori"], rows[0]["catatan"], rows[0]["sumber"]),
                         (50000, "Makanan & Minuman", "Makan di luar", "Kopi", "teks"))
        _, _, text, buttons = self.last_edit()
        self.assertEqual(text, "✅ Tersimpan! Pengeluaran Rp 50.000 · Makanan &amp; Minuman › Makan di luar\n"
                               "📊 Hari ini keluar Rp 50.000 · Bulan ini Rp 50.000")
        self.assertEqual(buttons[0], [{"text": "↩️ Hapus catatan ini", "callback_data": f"d:{rows[0]['id']}"}])
        self.assertNotIn(OWNER, bot.drafts)

        bot.handle_update(cb(OWNER, f"d:{rows[0]['id']}", mid))
        self.assertEqual(db.list_tx("2000-01-01", "2100-01-01"), [])
        self.assertEqual(self.last_edit()[2], "Dihapus 🗑 Catatan dibatalkan.")

    def test_retype_edits_same_card_and_toggle(self):
        bot.handle_update(msg(OWNER, "50000 kopi"))
        mid = bot.drafts[OWNER]["msg_id"]
        bot.handle_update(msg(OWNER, "60000 bensin kemarin"))
        _, m, text, buttons = self.last_edit()
        self.assertEqual(m, mid)
        self.assertTrue(text.startswith("❤️ <b>Pengeluaran</b> Rp 60.000 — <i>Bensin</i>\n"))
        self.assertEqual(buttons[0][0]["text"], "✅ Transportasi")
        bot.handle_update(msg(OWNER, "gaji 7.500.000"))  # a guessed jenis is re-guessed on retype
        _, m, text, buttons = self.last_edit()
        self.assertEqual(m, mid)
        self.assertTrue(text.startswith("💚 <b>Pemasukan</b> Rp 7.500.000 — <i>Gaji</i>\n"))
        self.assertEqual(buttons[0][0]["text"], "✅ Gaji")
        bot.handle_update(cb(OWNER, "e:t", mid))
        _, _, text, buttons = self.last_edit()
        self.assertTrue(text.startswith("❤️ <b>Pengeluaran</b> Rp 7.500.000 — <i>Gaji</i>\n"))
        self.assertEqual(buttons[0][0]["text"], "Makanan & Minuman")  # no keluar guess for "gaji": plain seed order
        self.assertEqual(buttons[-1][0]["text"], "🔁 Jadikan Pemasukan")
        bot.handle_update(msg(OWNER, "bonus 500rb"))  # 🔁 fixed the jenis: it sticks
        _, m, text, buttons = self.last_edit()
        self.assertEqual(m, mid)
        self.assertTrue(text.startswith("❤️ <b>Pengeluaran</b> Rp 500.000 — <i>Bonus</i>\n"))
        bot.handle_update(cb(OWNER, "x", mid))
        self.assertEqual(self.last_edit()[2], "Oke, dibatalkan. Kapan pun siap, ketik lagi ya 🙂")
        self.assertNotIn(OWNER, bot.drafts)

    def test_guided_flow_keeps_chosen_jenis(self):
        bot.handle_update(msg(OWNER, "📝 Catat Pengeluaran"))
        _, text, buttons = self.sent[-1]
        self.assertEqual(text, "Mau catat apa? 🙂")
        self.assertEqual([b["callback_data"] for b in buttons[0]], ["j:m", "j:k"])
        mid = bot.drafts[OWNER]["msg_id"]
        bot.handle_update(cb(OWNER, "j:m", mid))
        self.assertEqual(self.last_edit()[2], "Oke, <b>Pemasukan</b>. Ketik nominal + keterangan (contoh: <code>35000 nasi padang</code>) "
                                              "atau kirim foto struk 📸.")
        bot.handle_update(msg(OWNER, "7500000 kantor"))
        _, text, buttons = self.sent[-1]  # a new card below the typed text
        self.assertTrue(text.startswith("💚 <b>Pemasukan</b> Rp 7.500.000 — <i>Kantor</i>\n"))
        self.assertEqual(buttons[0][0]["text"], "✅ Lainnya")
        self.assertNotEqual(bot.drafts[OWNER]["msg_id"], mid)
        bot.handle_update(cb(OWNER, "c:0", bot.drafts[OWNER]["msg_id"]))  # Lainnya has only Umum → straight to CONFIRM
        self.assertTrue(self.last_edit()[2].startswith("Cek dulu ya 👇\n💚 <b>Pemasukan</b> Rp 7.500.000\n📂 Lainnya › Umum\n📝 Kantor\n"))
        bot.handle_update(msg(OWNER, "/catat"))
        bot.handle_update(msg(OWNER, "bonus 500rb"))  # typed before choosing: jenis is guessed
        self.assertTrue(self.sent[-1][1].startswith("💚 <b>Pemasukan</b> Rp 500.000 — <i>Bonus</i>\n"))
        self.assertEqual(self.sent[-1][2][0][0]["text"], "✅ Bonus")

    def test_ambiguous_and_errors(self):
        bot.handle_update(msg(OWNER, "50 kopi"))
        _, text, buttons = self.sent[-1]
        self.assertEqual(text, "Maksudnya berapa? 🤔")
        self.assertEqual(buttons, [[{"text": "Rp 50.000", "callback_data": "a:50000"}, {"text": "Rp 50", "callback_data": "a:50"}]])
        mid = bot.drafts[OWNER]["msg_id"]
        bot.handle_update(cb(OWNER, "a:50000", mid))
        _, m, text, buttons = self.last_edit()
        self.assertEqual(m, mid)
        self.assertTrue(text.startswith("❤️ <b>Pengeluaran</b> Rp 50.000 — <i>Kopi</i>\n"))
        self.assertEqual(buttons[0][0]["text"], "✅ Makanan & Minuman")
        bot.handle_update(msg(OWNER, "halo"))
        self.assertEqual(self.sent[-1][1], bot.NO_AMOUNT)
        bot.handle_update(msg(OWNER, "5 kopi"))
        self.assertEqual(self.sent[-1][1], "Nominal Rp 5 kelihatannya salah ketik 🤔 Coba lagi ya.")

    def test_ubah_nominal_from_confirm(self):
        bot.handle_update(msg(OWNER, "50000 kopi"))
        mid = bot.drafts[OWNER]["msg_id"]
        bot.handle_update(cb(OWNER, "c:0", mid))
        bot.handle_update(cb(OWNER, "s:0", mid))
        bot.handle_update(cb(OWNER, "e:j", mid))
        self.assertEqual(self.last_edit()[2], "❤️ <b>Pengeluaran</b> Rp 50.000\n\n✏️ Ketik nominal barunya ya (contoh: <code>35000</code>)")
        bot.handle_update(msg(OWNER, "35000"))
        self.assertTrue(self.last_edit()[2].startswith("Cek dulu ya 👇\n❤️ <b>Pengeluaran</b> Rp 35.000\n📂 Makanan &amp; Minuman › Makan di luar\n📝 Kopi\n"))
        today = bot.wib().date()
        self.assertEqual(bot.drafts[OWNER]["tanggal"], today.isoformat())
        bot.handle_update(cb(OWNER, "e:j", mid))
        bot.handle_update(msg(OWNER, "40000 kemarin"))  # a date hint next to the bare number travels with it
        self.assertEqual((bot.drafts[OWNER]["jumlah"], bot.drafts[OWNER]["tanggal"]), (40000, (today - timedelta(1)).isoformat()))
        self.assertEqual(bot.drafts[OWNER]["step"], bot.CONFIRM)

    def test_stale_callbacks(self):
        bot.handle_update(cb(OWNER, "c:0", 55))
        self.assertEqual(self.answered[-1], "Sesi ini sudah lewat. Ketik ulang catatannya ya 🙂")
        self.assertEqual(self.last_edit(), (OWNER, 55, None, []))
        for data in ("d:abc", "d:", "a:x"):  # malformed ids never raise
            bot.handle_update(cb(OWNER, data, 55))
            self.assertEqual(self.answered[-1], "Sesi ini sudah lewat. Ketik ulang catatannya ya 🙂")
        bot.handle_update(msg(OWNER, "50000 kopi"))
        mid = bot.drafts[OWNER]["msg_id"]
        bot.drafts[OWNER]["ts"] -= 901
        bot.handle_update(cb(OWNER, "c:0", mid))
        self.assertEqual(self.answered[-1], "Sesi ini sudah lewat. Ketik ulang catatannya ya 🙂")
        self.assertEqual(self.last_edit(), (OWNER, mid, None, []))
        self.assertNotIn(OWNER, bot.drafts)

    def test_lihat_and_reports(self):
        bot.handle_update(msg(OWNER, "📊 Lihat Pengeluaran"))
        _, text, buttons = self.sent[-1]
        self.assertRegex(text, r"^📊 Hari ini \(\w{3}, \d{1,2} \w{3}\): keluar Rp 0 · masuk Rp 0\nMinggu ini: keluar Rp 0 · Bulan ini: Rp 0\nDashboard-mu siap 👇")
        self.assertTrue(text.endswith("👇" + report.LINK))
        self.assertEqual(buttons, report.DASH)
        bot.handle_update(msg(OWNER, "/hari"))
        self.assertTrue(self.sent[-1][1].startswith("🌙 <b>Laporan Harian — "))
        bot.handle_update(msg(OWNER, "/minggu"))
        self.assertTrue(self.sent[-1][1].startswith("📆 <b>Laporan Mingguan — "))
        bot.handle_update(msg(OWNER, "/tahun"))
        self.assertTrue(self.sent[-1][1].startswith("🎉 <b>Ringkasan Tahunan "))
        bot.handle_update(msg(OWNER, "/pengingat"))
        self.assertEqual(self.sent[-1][1], "Laporan harianmu selalu aktif tiap 23.00 WIB 📊")

    # ---------- guests ----------

    def test_guest_throttle_and_no_getfile(self):
        bot.handle_update(msg(GUEST, "50000 kopi"))
        self.assertTrue(self.sent[-1][1].startswith("Halo "))  # first contact = the /start copy
        bot.handle_update(msg(GUEST, "50000 kopi"))
        self.assertEqual(self.sent[-1][1], bot.GUEST_REPLY)
        self.assertEqual(self.sent[-1][2][-1][0]["callback_data"], "r:1")
        bot.handle_update(msg(GUEST, "lagi"))
        bot.handle_update(msg(GUEST, **PHOTO))
        bot.handle_update(msg(GUEST, "/pengingat"))
        self.assertEqual(len(self.sent), 2)  # throttled within 60 s (/pengingat too; only /start is exempt)
        bot._guest_seen[GUEST] -= 61
        bot.handle_update(msg(GUEST, **PHOTO))
        self.assertEqual(len(self.sent), 3)
        bot._guest_seen[GUEST] -= 61
        bot.handle_update(msg(GUEST, "/pengingat"))
        self.assertEqual(self.sent[-1][1], "Pengingat malam (23.00 WIB) saat ini <b>nonaktif</b>.")
        self.assertEqual(self.files, [])
        self.assertEqual(db.list_tx("2000-01-01", "2100-01-01"), [])
        bot.handle_update(cb(GUEST, "r:1", 9))
        self.assertEqual(db.guests_to_remind(), [GUEST])
        self.assertEqual(self.sent[-1][1], "🔔 Siap! Tiap 23.00 WIB aku ingatkan untuk mencatat. Matikan kapan saja lewat /pengingat.")
        bot.handle_update(cb(GUEST, "r:0", 9))
        self.assertEqual(db.guests_to_remind(), [])
        self.assertEqual(self.sent[-1][1], "🔕 Pengingat dimatikan.")
        bot.handle_update(cb(GUEST, "c:0", 9))  # owner-only callbacks: answered, nothing else
        self.assertEqual(len(self.sent), 6)

    def test_group(self):
        bot.handle_update(msg(OWNER, "/start@finnfinnnn_bot", chat_type="group"))
        self.assertEqual(self.sent[-1], (-100, "Aku hanya bekerja di chat pribadi 🙂", None))
        bot.handle_update(msg(OWNER, "50000 kopi", chat_type="group"))
        self.assertEqual(len(self.sent), 1)

    # ---------- photos ----------

    def test_photo_ok(self):
        expect = json.loads((FIX / "01.json").read_text())
        self.photo(OWNER)
        self.assertEqual(self.sent[-1][1], "⏳ Sedang membaca struk…")
        self.assertEqual(self.files, ["big"])
        _, mid, text, buttons = self.last_edit()
        self.assertEqual(mid, self.n)
        self.assertTrue(text.startswith(f"📸 Struk terbaca!\n💰 Total: {report.rp(expect['jumlah'])}\n🏪 {expect['merchant']}\n📅 "))
        self.assertTrue(text.endswith("\n\nBenar totalnya?"))
        self.assertEqual([[b["callback_data"] for b in row] for row in buttons], [["ok", "e:j"], ["x"]])
        d = bot.drafts[OWNER]
        self.assertEqual((d["step"], d["sumber"], d["jenis"]), (bot.ASK_JUMLAH, "struk", "keluar"))
        bot.handle_update(cb(OWNER, "ok", mid))
        _, _, text, buttons = self.last_edit()
        self.assertTrue(text.startswith(f"❤️ <b>Pengeluaran</b> {report.rp(expect['jumlah'])} — <i>{expect['merchant']}</i>\n"))
        self.assertEqual(buttons[0][0]["text"], "✅ Makanan & Minuman")
        bot.handle_update(cb(OWNER, "c:0", mid))
        self.assertEqual(self.last_edit()[3][0][0]["text"], "✅ " + expect["subkategori"])

    def test_photo_errors(self):
        for exc, copy in ((ocr.Busy(), bot.BUSY), (TimeoutError(), bot.KELAMAAN), (ValueError("bukan gambar"), bot.TOO_BIG),
                          (RuntimeError("child died"), bot.KURANG_JELAS)):
            def run(img, exc=exc):
                raise exc
            ocr.run = run
            self.photo(OWNER)
            self.assertEqual(self.last_edit()[2], copy)
        self.assertEqual(bot.drafts[OWNER]["step"], bot.ASK_JUMLAH)  # merchant/date kept: a typed amount completes it
        bot.handle_update(msg(OWNER, "87500"))
        self.assertTrue(self.last_edit()[2].startswith("❤️ <b>Pengeluaran</b> Rp 87.500 — <i>Struk</i>\n"))
        ocr.run = lambda img: []
        self.photo(OWNER)
        self.assertEqual(self.last_edit()[2], bot.KURANG_JELAS)
        with ocr.LOCK:
            self.photo(OWNER)
        self.assertEqual(self.sent[-1][1], bot.BUSY)
        config.OCR_ENABLED = False
        self.photo(OWNER)
        self.assertEqual(self.sent[-1][1], bot.OCR_OFF)
        config.OCR_ENABLED = True
        self.photo(OWNER, date=int(time.time()) - 601)
        self.assertEqual(self.sent[-1][1], bot.OFFLINE)
        bot.handle_update(msg(OWNER, document={"file_id": "doc", "mime_type": "image/jpeg", "file_size": 6 * 1024 * 1024}))
        self.assertEqual(self.sent[-1][1], bot.TOO_BIG)
        bot.handle_update(msg(OWNER, document={"file_id": "pdf", "mime_type": "application/pdf", "file_size": 100}))
        self.assertEqual(self.sent[-1][1], bot.TOO_BIG)
        self.assertEqual(self.files.count("doc") + self.files.count("pdf"), 0)

    def test_photo_worker_failure_is_reported(self):
        calls = []

        def edit(chat_id, msg_id, text=None, buttons=None, parse_mode="HTML"):
            calls.append(text)
            if len(calls) == 1:
                raise RuntimeError("Bad Request: message to edit not found")
        tg.tg_edit = edit

        def run(img):
            raise ocr.Busy()
        ocr.run = run
        self.photo(OWNER)
        self.assertEqual(calls, [bot.BUSY, bot.KURANG_JELAS])  # the failed edit is retried once with the fallback copy
        self.assertTrue(self.sent[-1][1].startswith("⚠️ Finn Finn error: RuntimeError: Bad Request: message to edit not found"))
        self.assertNotIn(OWNER, bot.drafts)


if __name__ == "__main__":
    unittest.main()
