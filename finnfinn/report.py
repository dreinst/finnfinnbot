import logging
import os
import time
from datetime import date, datetime, time as dtime, timedelta
from html import escape

from . import config, db, tg

log = logging.getLogger("finnfinn.report")
last_tick = time.monotonic()  # refreshed every ticker pass; the watchdog in __main__ restarts the process once it is > 300 s old
HARIAN_AT = os.environ.get("REPORT_TIME_OVERRIDE", "23:00")  # testing aid: harian + pengingat fire at HH:MM instead of 23:00
WINDOW = timedelta(days=3)  # catch-up for mingguan/bulanan/tahunan; harian/pengingat/backup catch up within the same WIB day
WEB_APP = {"web_app": {"url": config.WEBAPP_URL}} if config.WEBAPP_URL.startswith("https") else None  # Telegram needs HTTPS for web_app
DASH = [[{"text": "📊 Buka Dashboard", **WEB_APP}]] if WEB_APP else []
BUKA_APP = [[{"text": "📱 Buka Finn Finn", **WEB_APP}]] if WEB_APP else []
HARI = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"]
BULAN = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
BULAN_FULL = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
IKON = {"Makanan & Minuman": "🍽", "Transportasi": "🚗", "Tagihan": "🧾", "Belanja": "🛍", "Kesehatan": "💊", "Hiburan": "🎬",
        "Pendidikan": "📚", "Rumah Tangga": "🏠", "Gaji": "💼", "Bonus": "🎁", "Investasi": "📈"}
REMINDER = "🌙 Sudah catat pengeluaran hari ini? Yuk, 1 menit saja sebelum tidur 😌"
_alert_at = None


def esc(s):
    return escape(s, quote=False)


def rp(n):
    return ("−" if n < 0 else "") + "Rp " + f"{abs(n):,}".replace(",", ".")


def short(n):
    """Bar label: 320rb, 1,2jt."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}".rstrip("0").rstrip(".").replace(".", ",") + "jt"
    return f"{n // 1000}rb" if n >= 1000 else str(n)


def tanggal(d, year=True):
    return f"{HARI[d.weekday()]}, {d.day} {BULAN[d.month - 1]}" + (f" {d.year}" if year else "")


def ikon(kategori):
    return IKON.get(kategori, "•")


def alert(text):
    """DM the first owner, at most once per 10 min (shared by the poll loop, the ticker and the watchdog)."""
    global _alert_at
    if not config.FIRST_OWNER or (_alert_at and time.monotonic() - _alert_at < 600):
        return
    _alert_at = time.monotonic()
    try:
        tg.tg_send(config.FIRST_OWNER, text)
    except Exception as e:
        log.error("DM peringatan gagal: %s", e)


def send_owners(text):
    for uid in sorted(config.OWNER_IDS):
        tg.tg_send(uid, text, buttons=DASH)


def sums(frm, to):
    """→ (masuk, keluar, keluar rows per leaf sorted desc, {tanggal: keluar}) for the inclusive range."""
    by_cat, by_day = db.summary(frm, to)
    cat = [r for r in by_cat if r["jenis"] == "keluar"]
    day = {r["tanggal"]: r["total"] for r in by_day if r["jenis"] == "keluar"}
    return sum(r["total"] for r in by_cat if r["jenis"] == "masuk"), sum(r["total"] for r in cat), cat, day


# ---------- text builders ----------

def _bars(title, rows):
    """[(label, value)] → <pre> block, ▇ bars scaled so the largest value gets 5."""
    top = max((v for _, v in rows), default=0)
    amts = [short(v) for _, v in rows]
    w = max(len(a) for a in amts)
    lines = [f"{l} {'▇' * max(1, round(v * 5 / top)) if v else '':<5}  {a:>{w}}" for (l, v), a in zip(rows, amts)]
    return f"<pre>{title}\n" + "\n".join(lines) + "</pre>"


def _saldo(masuk, keluar):
    diff = masuk - keluar
    if diff < 0:
        return f"⚠️ Defisit {rp(-diff)}"
    return f"✅ Surplus {rp(diff)}" + (f" ({round(diff * 100 / masuk)}% tersimpan)" if masuk else "")


def _vs(label, cur, prev):
    if not prev:
        return f"vs {label}: belum ada pembanding"
    pct = round((cur - prev) * 100 / prev)
    return f"vs {label}: keluar " + (f"▼ {-pct}% 👍" if pct < 0 else f"▲ {pct}% 👀" if pct > 0 else "sama 😐")


def _per_kat(cat, keluar, top=None):
    agg = {}
    for r in cat:
        agg[r["kategori"]] = agg.get(r["kategori"], 0) + r["total"]
    items = sorted(agg.items(), key=lambda kv: -kv[1])[:top]
    w = max((len(k) for k, _ in items), default=0)
    return [f"{ikon(k)} {esc(f'{k:<{w}}')}  {rp(v)} ({round(v * 100 / keluar)}%)" for k, v in items]


def _rentang(a, b):
    left = str(a.day) if (a.year, a.month) == (b.year, b.month) else f"{a.day} {BULAN[a.month - 1]}"
    return f"{left}–{b.day} {BULAN[b.month - 1]} {b.year}"


def build_harian(day):
    """HTML daily report for the WIB date `day`."""
    masuk, keluar, cat, _ = sums(day.isoformat(), day.isoformat())
    head = f"🌙 <b>Laporan Harian — {tanggal(day)}</b>\n\n"
    tail = (f"\n📊 Minggu ini: keluar {rp(sums((day - timedelta(day.weekday())).isoformat(), day.isoformat())[1])}"
            f" · Bulan ini: {rp(sums(day.replace(day=1).isoformat(), day.isoformat())[1])}")
    if not masuk and not keluar:
        return head + "Hari ini belum ada catatan 🙂 Kalau ada yang terlewat, ketik saja sekarang — misalnya <code>25000 makan siang</code>.\n" + tail
    diff = masuk - keluar
    body = (f"💸 Keluar: {rp(keluar)} ({sum(r['n'] for r in cat)} transaksi)\n💰 Masuk: {rp(masuk)}\n"
            f"{'📈' if diff >= 0 else '📉'} Selisih: {rp(diff)}\n")
    top = sorted((t for t in db.list_tx(day.isoformat(), day.isoformat()) if t["jenis"] == "keluar"), key=lambda t: -t["jumlah"])[:3]
    if top:
        body += "\nTerbesar hari ini:\n" + "\n".join(
            f"{i}. {ikon(t['kategori'])} {esc(t['subkategori'])} — {rp(t['jumlah'])}"
            + (f" · {esc(t['catatan'])}" if t["catatan"] and t["catatan"] != t["subkategori"] else "")
            for i, t in enumerate(top, 1)) + "\n"
    return head + body + tail


def build_mingguan(monday):
    """HTML weekly report for the Mon–Sun week starting at `monday`."""
    sunday = monday + timedelta(6)
    masuk, keluar, cat, day = sums(monday.isoformat(), sunday.isoformat())
    prev = sums((monday - timedelta(7)).isoformat(), (monday - timedelta(1)).isoformat())[1]
    return (f"📆 <b>Laporan Mingguan — {_rentang(monday, sunday)}</b>\n💰 Masuk {rp(masuk)} · 💸 Keluar {rp(keluar)}\n{_saldo(masuk, keluar)}\n\n"
            + _bars("Traffic harian (keluar)", [(HARI[i], day.get((monday + timedelta(i)).isoformat(), 0)) for i in range(7)])
            + ("\nPer kategori:\n" + "\n".join(_per_kat(cat, keluar)) if cat else "")
            + f"\n\n{_vs('minggu lalu', keluar, prev)}")


def build_bulanan(year, month):
    """HTML monthly report."""
    first = date(year, month, 1)
    last = (first + timedelta(31)).replace(day=1) - timedelta(1)
    masuk, keluar, cat, day = sums(first.isoformat(), last.isoformat())
    prev = sums((first - timedelta(1)).replace(day=1).isoformat(), (first - timedelta(1)).isoformat())[1]
    weeks = [(f"W{w + 1}", sum(v for t, v in day.items() if (int(t[8:]) - 1) // 7 == w)) for w in range((last.day + 6) // 7)]
    subs = [f"{i}. {ikon(r['kategori'])} {esc(r['subkategori'])} — {rp(r['total'])} ({round(r['total'] * 100 / keluar)}%)"
            for i, r in enumerate(cat[:5], 1)]
    boros = max(day.items(), key=lambda kv: kv[1], default=None)
    return (f"🗓 <b>Laporan Bulanan — {BULAN_FULL[month - 1]} {year}</b>\n💰 Masuk {rp(masuk)} · 💸 Keluar {rp(keluar)}\n"
            f"{_saldo(masuk, keluar)}\n📅 Rata-rata harian: {rp(keluar // last.day)}\n\n"
            + _bars("Traffic mingguan (keluar)", weeks)
            + ("\nTop 5 sub-kategori:\n" + "\n".join(subs) if subs else "")
            + (f"\n🔥 Hari terboros: {tanggal(date.fromisoformat(boros[0]), year=False)} ({rp(boros[1])})" if boros else "")
            + f"\n\n{_vs('bulan lalu', keluar, prev)}")


def build_tahunan(year):
    """HTML yearly report."""
    masuk, keluar, cat, day = sums(f"{year}-01-01", f"{year}-12-31")
    months = [0] * 12
    for t, v in day.items():
        months[int(t[5:7]) - 1] += v
    rows = list(zip(BULAN, months))
    aktif = [r for r in rows if r[1]]
    nama = db.meta_get("nama")
    return (f"🎉 <b>Ringkasan Tahunan {year}</b>\n💰 Masuk {rp(masuk)} · 💸 Keluar {rp(keluar)}\n{_saldo(masuk, keluar)}\n\n"
            + _bars("Traffic bulanan (keluar)", rows)
            + (f"\n🌱 Bulan paling hemat: {min(aktif, key=lambda r: r[1])[0]} ({rp(min(aktif, key=lambda r: r[1])[1])})"
               f"\n🔥 Bulan paling boros: {max(aktif, key=lambda r: r[1])[0]} ({rp(max(aktif, key=lambda r: r[1])[1])})" if aktif else "")
            + ("\nTop 3 kategori:\n" + "\n".join(_per_kat(cat, keluar, 3)) if cat else "")
            + f"\n\nSelamat tahun baru{', ' + esc(nama) if nama else ''}! Tahun ini kita catat lebih rapi lagi 🌱")


# ---------- jobs ----------

def backup(day=None):
    """Snapshot to <DB dir>/backups/finnfinn-YYYYMMDD.db, keep the newest 14, truncate the WAL; → path."""
    day = day or datetime.now(config.WIB).date()
    bdir = os.path.join(os.path.dirname(config.DB_PATH) or ".", "backups")
    dest = db.snapshot(os.path.join(bdir, f"finnfinn-{day:%Y%m%d}.db"))
    for f in sorted(f for f in os.listdir(bdir) if f.startswith("finnfinn-"))[:-14]:
        os.remove(os.path.join(bdir, f))
    db.connect().execute("PRAGMA wal_checkpoint(TRUNCATE)")
    return dest


def _remind(tg_id):
    time.sleep(0.05)  # < 30 msg/s
    try:
        tg.tg_send(tg_id, REMINDER, buttons=BUKA_APP + [[{"text": "🔕 Matikan pengingat", "callback_data": "r:0"}]])
    except RuntimeError as e:
        if "forbidden" not in str(e).lower() and "403" not in str(e):
            raise
        db.guest_delete(tg_id)  # blocked / never started: drop the id entirely


def _bulanan(year, month):
    send_owners(build_bulanan(year, month))
    if config.BACKUP_TO_TELEGRAM:
        path = backup()
        for uid in sorted(config.OWNER_IDS):
            tg.tg_send_document(uid, path, f"🗄️ Backup Finn Finn — {BULAN_FULL[month - 1]} {year} (simpan di Saved Messages)")


def _windowed(d, tz):
    """Owner reports whose period ends on the WIB date d → [(kind, period_key, fn, fires_at)]."""
    at = lambda h, m: datetime.combine(d, dtime(h, m), tz)
    jobs = []
    if d.weekday() == 6:
        jobs.append(("mingguan", "%d-W%02d" % d.isocalendar()[:2], lambda: send_owners(build_mingguan(d - timedelta(6))), at(23, 5)))
    if (d + timedelta(1)).month != d.month:
        jobs.append(("bulanan", d.strftime("%Y-%m"), lambda: _bulanan(d.year, d.month), at(23, 10)))
    if (d.month, d.day) == (1, 1):
        jobs.append(("tahunan", str(d.year - 1), lambda: send_owners(build_tahunan(d.year - 1)), at(8, 0)))
    return jobs


def due(now):
    """→ [(kind, period_key, fn)] due at the WIB datetime `now`, including catch-up windows."""
    today, hhmm, jobs = now.date(), now.strftime("%H:%M"), []
    if hhmm >= HARIAN_AT:
        if config.OWNER_IDS:
            jobs.append(("harian", today.isoformat(), lambda: send_owners(build_harian(today))))
        jobs += [("pengingat", f"{today}:{g}", lambda g=g: _remind(g)) for g in db.guests_to_remind()]
    if hhmm >= "23:30":
        jobs.append(("backup", today.isoformat(), lambda: backup(today)))
    if config.OWNER_IDS:
        for n in range(4):
            jobs += [(k, key, fn) for k, key, fn, at in _windowed(today - timedelta(n), now.tzinfo) if at <= now < at + WINDOW]
    return jobs


def skip_missed(now):
    """Boot: the newest period per kind whose 3-day window closed unsent is logged and marked so it never fires."""
    seen = set()
    for n in range(3, 400):
        for kind, key, _, at in _windowed(now.date() - timedelta(n), now.tzinfo):
            if kind not in seen and now >= at + WINDOW:
                seen.add(kind)
                if db.claim(kind, key):
                    log.warning("%s %s terlewat lebih dari 3 hari, dilewati", kind, key)


def tick(now):
    """One ticker pass: claim + run every due job; a failure releases the claim so the catch-up window retries it."""
    for kind, key, fn in due(now):
        if db.claim(kind, key):
            try:
                fn()
                log.info("%s %s selesai", kind, key)
            except Exception as e:
                db.unclaim(kind, key)
                log.exception("%s %s gagal", kind, key)
                alert(f"⚠️ Finn Finn error: {type(e).__name__}: {str(e)[:120]}")


def loop(stop):
    """30-s WIB ticker: claim due jobs via db.claim, run them, refresh last_tick every pass."""
    global last_tick
    try:
        if config.OWNER_IDS:
            skip_missed(datetime.now(config.WIB))
    except Exception:
        log.exception("cek laporan terlewat gagal")
    while not stop.is_set():
        now = datetime.now(config.WIB)
        try:
            tick(now)
            db.meta_set("last_tick", now.isoformat(timespec="seconds"))
        except Exception:
            log.exception("ticker gagal")
        last_tick = time.monotonic()
        stop.wait(30)
