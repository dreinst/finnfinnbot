import json
import logging
import threading
import time
from datetime import date, datetime, timedelta

from . import config, db, ocr, parse, report, tg
from .report import BUKA_APP, DASH, esc, rp, tanggal

log = logging.getLogger("finnfinn.bot")
drafts = {}  # uid → {step, jenis, jumlah, catatan, tanggal, waktu, sumber, kategori, subkategori, guess, cats, subs, msg_id, ts}
poll_status = "ok"  # "ok" | "conflict" (409 seen on the last getUpdates)
_guest_seen = {}  # uid → monotonic time of the last canned reply
TTL = 900
MAX_PHOTO = 5 * 1024 * 1024
ASK_JENIS, ASK_INPUT, ASK_JUMLAH, PICK_KATEGORI, PICK_SUB, CONFIRM = "ASK_JENIS", "ASK_INPUT", "ASK_JUMLAH", "PICK_KATEGORI", "PICK_SUB", "CONFIRM"
CARD = (ASK_JUMLAH, PICK_KATEGORI, PICK_SUB, CONFIRM)  # steps whose message is edited in place by new text
EMPTY = {"jenis": "keluar", "jumlah": None, "catatan": "", "tanggal": "", "waktu": "", "sumber": "teks", "kategori": None,
         "subkategori": None, "guess": (None, None), "cats": [], "subs": [], "msg_id": None}
MENU = [["📝 Catat Pengeluaran"], ["📊 Lihat Pengeluaran"]]
BATAL = {"text": "❌ Batal", "callback_data": "x"}
REMIND_ON = {"text": "🔔 Ingatkan aku tiap malam (23.00 WIB)", "callback_data": "r:1"}
REMIND_OFF = {"text": "🔕 Matikan pengingat", "callback_data": "r:0"}
GUEST_BUTTONS = BUKA_APP + [[REMIND_ON]]
COMMANDS = [("start", "Mulai"), ("catat", "Catat pemasukan / pengeluaran"), ("lihat", "Ringkasan + dashboard"),
            ("hari", "Laporan hari ini"), ("minggu", "Laporan minggu ini"), ("bulan", "Laporan bulan ini"),
            ("tahun", "Ringkasan tahun ini"), ("backup", "Kirim backup database"), ("pengingat", "Pengingat malam")]

START_OWNER = (
    "Halo {nama}! 👋 Aku <b>Finn Finn</b>, pencatat keuangan pribadimu.\n\n"
    "Cara pakai:\n"
    "• Ketik langsung, contoh: <code>50000 kopi</code> atau <code>gaji 7.500.000</code>\n"
    "• Atau kirim <b>foto struk</b> 📸, nanti aku baca totalnya\n"
    "• Tekan <b>📝 Catat Pengeluaran</b> untuk dipandu\n"
    "• Tekan <b>📊 Lihat Pengeluaran</b> untuk buka dashboard\n\n"
    "Setiap catatan selalu kutanya dulu kategorinya sebelum disimpan — tidak ada yang tersimpan diam-diam 🙂\n"
    "Laporan harian kukirim tiap 23.00 WIB, rekap mingguan tiap Minggu malam, bulanan di akhir bulan, "
    "dan ringkasan tahunan tiap tahun baru 🎉")
START_GUEST = (
    "Halo {nama}! 👋 Aku <b>Finn Finn</b>.\n"
    "Untuk kamu, semua catatan disimpan <b>di akun Telegram-mu sendiri</b> (Telegram Cloud) — tidak ada data keuangan "
    "yang tersimpan di server kami. Foto struk pun dibaca langsung di HP-mu 🔒\n\n"
    "Catat &amp; lihat pengeluaranmu lewat aplikasi di bawah ini 👇")
GUEST_REPLY = "Di sini aku cuma bisa membantu lewat aplikasi ya 🙂 Pesan di chat tidak kusimpan. Tekan tombol di bawah untuk mencatat."
NO_AMOUNT = "Hmm, aku belum menemukan nominalnya 🙈\nContoh: <code>50000 kopi</code>, <code>bensin 100rb</code>, <code>gaji 7,5jt</code>"
MANUAL = "ketik manual: <code>87500 indomaret</code>"
KURANG_JELAS = "Maaf, struknya kurang jelas 🙏 Coba foto lebih dekat &amp; terang, atau " + MANUAL
KELAMAAN = "Maaf, struknya kelamaan dibaca (lebih dari 30 detik) 🙏 Coba foto yang lebih kecil &amp; jelas, atau " + MANUAL
BUSY = "Sedang membaca struk lain, tunggu sebentar ya ⏳"
TOO_BIG = "Fotonya terlalu besar (maks 5 MB) atau bukan gambar. Kirim sebagai foto biasa ya 📷"
OFFLINE = "Struk yang dikirim saat aku offline tidak kubaca, kirim ulang ya 📸"
OCR_OFF = "Baca struk sedang nonaktif. Ketik manual ya: <code>87500 indomaret</code>"
STALE = "Sesi ini sudah lewat. Ketik ulang catatannya ya 🙂"
OWNER_REMIND = "Laporan harianmu selalu aktif tiap 23.00 WIB 📊"


def wib():
    return datetime.now(config.WIB)


def draft(uid):
    """The owner's live draft, or None (missing / older than TTL)."""
    d = drafts.get(uid)
    if d and time.time() - d["ts"] > TTL:
        drafts.pop(uid, None)
        return None
    return d


def head(d):
    masuk = d["jenis"] == "masuk"
    return f"{'💚' if masuk else '❤️'} <b>{'Pemasukan' if masuk else 'Pengeluaran'}</b> {rp(d['jumlah'])}"


def when(d):
    return f"📅 {tanggal(date.fromisoformat(d['tanggal']))}" + (f" · {d['waktu']}" if d["waktu"] else "")


def grid(items, prefix, pick):
    """2-per-row inline grid; `pick` (when present) goes first with a ✅ → (ordered items, rows)."""
    items = [pick] + [i for i in items if i != pick] if pick in items else list(items)
    btn = [{"text": ("✅ " if i == 0 and pick in items else "") + t, "callback_data": f"{prefix}:{i}"} for i, t in enumerate(items)]
    return items, [btn[i:i + 2] for i in range(0, len(btn), 2)]


def show(uid, d, step, text, buttons):
    """Move the draft to `step` and edit its card in place (or send a new one)."""
    d["step"], d["ts"] = step, time.time()
    drafts[uid] = d
    if d["msg_id"]:
        try:
            tg.tg_edit(uid, d["msg_id"], text, buttons)
            return
        except RuntimeError as e:
            log.warning("edit kartu gagal, kirim baru: %s", e)
    d["msg_id"] = tg.tg_send(uid, text, buttons=buttons)["result"]["message_id"]


def pick_kategori(uid, d):
    cats = list(dict.fromkeys(c["kategori"] for c in db.categories() if c["aktif"] and c["jenis"] == d["jenis"]))
    d["cats"], rows = grid(cats, "c", d["guess"][0])
    lines = [head(d) + (f" — <i>{esc(d['catatan'])}</i>" if d["catatan"] else ""), when(d)]
    if d.get("multiple"):
        lines.append("Aku ambil satu dulu ya, kirim yang lain terpisah 🙂")
    flip = "🔁 Jadikan Pengeluaran" if d["jenis"] == "masuk" else "🔁 Jadikan Pemasukan"
    show(uid, d, PICK_KATEGORI, "\n".join(lines) + "\n\nPilih kategori:", rows + [[{"text": flip, "callback_data": "e:t"}, BATAL]])


def pick_sub(uid, d):
    subs = [c["subkategori"] for c in db.categories() if c["aktif"] and c["jenis"] == d["jenis"] and c["kategori"] == d["kategori"]]
    if len(subs) == 1:
        d["subkategori"] = subs[0]
        return confirm(uid, d)
    d["subs"], rows = grid(subs, "s", d["guess"][1] if d["guess"][0] == d["kategori"] else None)
    show(uid, d, PICK_SUB, f"Kategori: <b>{esc(d['kategori'])}</b>\nPilih sub-kategori:",
         rows + [[{"text": "◀️ Kategori", "callback_data": "b:c"}, BATAL]])


def confirm(uid, d):
    text = (f"Cek dulu ya 👇\n{head(d)}\n📂 {esc(d['kategori'])} › {esc(d['subkategori'])}\n"
            f"📝 {esc(d['catatan'] or d['subkategori'])}\n{when(d)}")
    show(uid, d, CONFIRM, text, [[{"text": "✅ Simpan", "callback_data": "ok"}],
                                 [{"text": "✏️ Ubah nominal", "callback_data": "e:j"}, {"text": "📂 Ubah kategori", "callback_data": "b:c"}],
                                 [BATAL]])


def after_amount(uid, d):
    return confirm(uid, d) if d["subkategori"] else pick_kategori(uid, d)


def save(uid, d):
    tx = db.add_tx({**d, "catatan": d["catatan"] or d["subkategori"]})
    drafts.pop(uid, None)
    today = wib().date()
    hari = report.sums(today.isoformat(), today.isoformat())[1]
    bulan = report.sums(today.replace(day=1).isoformat(), today.isoformat())[1]
    text = (f"✅ Tersimpan! {'Pemasukan' if tx['jenis'] == 'masuk' else 'Pengeluaran'} {rp(tx['jumlah'])} · "
            f"{esc(tx['kategori'])} › {esc(tx['subkategori'])}\n📊 Hari ini keluar {rp(hari)} · Bulan ini {rp(bulan)}")
    tg.tg_edit(uid, d["msg_id"], text, [[{"text": "↩️ Hapus catatan ini", "callback_data": f"d:{tx['id']}"}]] + DASH)


def on_text(uid, text):
    t = wib()
    p = parse.parse_text(text, t.date())
    if p["error"] == "kosong":
        return tg.tg_send(uid, NO_AMOUNT)
    if p["error"]:
        return tg.tg_send(uid, f"Nominal {rp(p['jumlah'])} kelihatannya salah ketik 🤔 Coba lagi ya.")
    d = draft(uid)
    if d and d["step"] == ASK_JUMLAH and not p["catatan"]:  # a bare number answers the nominal prompt
        d["jumlah"] = p["jumlah"]
    else:
        jenis = d["jenis"] if d and d["step"] != ASK_JENIS else p["jenis"]  # a chosen/guessed jenis sticks; 🔁 flips it
        d = {**EMPTY, "jenis": jenis, "jumlah": p["jumlah"], "catatan": p["catatan"], "tanggal": p["tanggal"],
             "waktu": t.strftime("%H:%M"), "multiple": p["multiple"], "msg_id": d["msg_id"] if d and d["step"] in CARD else None,
             "guess": (p["kategori"], p["subkategori"]) if jenis == p["jenis"] else parse.guess_kategori(p["catatan"], jenis)}
    if p["ambiguous"]:
        n = p["jumlah"]
        return show(uid, d, ASK_JUMLAH, "Maksudnya berapa? 🤔",
                    [[{"text": rp(n * 1000), "callback_data": f"a:{n * 1000}"}, {"text": rp(n), "callback_data": f"a:{n}"}]])
    after_amount(uid, d)


def read_receipt(uid, mid, file_id):
    """Per-photo worker: download → ocr.run (serialized inside) → parse_receipt → draft → card."""
    try:
        lines = ocr.run(tg.tg_get_file(file_id, MAX_PHOTO))
    except ocr.Busy:
        return tg.tg_edit(uid, mid, BUSY)
    except TimeoutError:
        return tg.tg_edit(uid, mid, KELAMAAN)
    except ValueError:
        return tg.tg_edit(uid, mid, TOO_BIG)
    except Exception as e:  # RuntimeError from the OCR child or a download hiccup: no total
        log.warning("OCR gagal: %s", e)
        lines = []
    r = parse.parse_receipt(lines, wib().date())
    d = {**EMPTY, "jumlah": r["jumlah"], "catatan": r["catatan"], "tanggal": r["tanggal"], "waktu": r["waktu"], "sumber": "struk",
         "guess": (r["kategori"], r["subkategori"]), "msg_id": mid}
    if r["jumlah"] is None:
        return show(uid, d, ASK_JUMLAH, KURANG_JELAS, [[BATAL]])
    text = (("⚠️ Aku kurang yakin dengan totalnya, cek dulu ya.\n" if r["confidence"] == "low" else "")
            + f"📸 Struk terbaca!\n💰 Total: {rp(r['jumlah'])}\n🏪 {esc(r['catatan'])}\n📅 {date.fromisoformat(r['tanggal']):%d/%m/%Y}"
            + (f" · {r['waktu']}" if r["waktu"] else "") + "\n\nBenar totalnya?")
    show(uid, d, ASK_JUMLAH, text, [[{"text": "✅ Benar", "callback_data": "ok"}, {"text": "✏️ Ubah nominal", "callback_data": "e:j"}], [BATAL]])


def on_photo(uid, msg, file):
    if msg.get("date", 0) < time.time() - 600:
        return tg.tg_send(uid, OFFLINE)
    if not config.OCR_ENABLED:
        return tg.tg_send(uid, OCR_OFF)
    if (file.get("file_size") or 0) > MAX_PHOTO:
        return tg.tg_send(uid, TOO_BIG)
    if ocr.LOCK.locked():
        return tg.tg_send(uid, BUSY)
    mid = tg.tg_send(uid, "⏳ Sedang membaca struk…")["result"]["message_id"]
    threading.Thread(target=read_receipt, args=(uid, mid, file["file_id"]), daemon=True, name="ocr").start()


def ask_jenis(uid):
    r = tg.tg_send(uid, "Mau catat apa? 🙂",
                   buttons=[[{"text": "💚 Pemasukan", "callback_data": "j:m"}, {"text": "❤️ Pengeluaran", "callback_data": "j:k"}]])
    drafts[uid] = {**EMPTY, "step": ASK_JENIS, "msg_id": r["result"]["message_id"], "ts": time.time()}


def lihat(uid):
    today = wib().date()
    hari = report.sums(today.isoformat(), today.isoformat())
    minggu = report.sums((today - timedelta(today.weekday())).isoformat(), today.isoformat())[1]
    bulan = report.sums(today.replace(day=1).isoformat(), today.isoformat())[1]
    tg.tg_send(uid, f"📊 Hari ini ({tanggal(today, year=False)}): keluar {rp(hari[1])} · masuk {rp(hari[0])}\n"
                    f"Minggu ini: keluar {rp(minggu)} · Bulan ini: {rp(bulan)}\nDashboard-mu siap 👇", buttons=DASH)


def send_report(uid, kind):
    t = wib().date()
    build = {"h": lambda: report.build_harian(t), "m": lambda: report.build_mingguan(t - timedelta(t.weekday())),
             "b": lambda: report.build_bulanan(t.year, t.month), "t": lambda: report.build_tahunan(t.year)}.get(kind)
    if build:
        tg.tg_send(uid, build(), buttons=DASH)


def on_command(uid, msg, cmd):
    if cmd == "/start":
        nama = msg["from"].get("first_name") or "kamu"
        db.meta_set("nama", nama)
        tg.tg_send(uid, START_OWNER.format(nama=esc(nama)), buttons=MENU)
    elif cmd == "/catat":
        ask_jenis(uid)
    elif cmd == "/lihat":
        lihat(uid)
    elif cmd in ("/hari", "/minggu", "/bulan", "/tahun"):
        send_report(uid, cmd[1])
    elif cmd == "/backup":
        tg.tg_send_document(uid, report.backup(), "🗄️ Backup database Finn Finn — simpan baik-baik ya.")
    elif cmd == "/pengingat":
        tg.tg_send(uid, OWNER_REMIND)


def remind_toggle(uid, on):
    if uid in config.OWNER_IDS:
        return tg.tg_send(uid, OWNER_REMIND)
    db.guest_upsert(uid)  # a tap proves the chat is open
    db.guest_set_remind(uid, on)
    tg.tg_send(uid, "🔔 Siap! Tiap 23.00 WIB aku ingatkan untuk mencatat. Matikan kapan saja lewat /pengingat." if on
               else "🔕 Pengingat dimatikan.")


def on_guest(uid, msg):
    """Non-owner chat: never parsed, downloaded, logged or stored — only the guests row (tg_id, remind)."""
    known = db.guest_known(uid)
    db.guest_upsert(uid)
    cmd = command(msg)
    if cmd == "/start" or not known:
        return tg.tg_send(uid, START_GUEST.format(nama=esc(msg["from"].get("first_name") or "kamu")), buttons=GUEST_BUTTONS)
    if cmd == "/pengingat":
        on = uid in db.guests_to_remind()
        return tg.tg_send(uid, f"Pengingat malam (23.00 WIB) saat ini <b>{'aktif' if on else 'nonaktif'}</b>.",
                          buttons=[[REMIND_OFF if on else REMIND_ON]])
    if time.monotonic() - _guest_seen.get(uid, -60) < 60:
        return
    if len(_guest_seen) >= 10_000:
        _guest_seen.clear()
    _guest_seen[uid] = time.monotonic()
    tg.tg_send(uid, GUEST_REPLY, buttons=GUEST_BUTTONS)


def on_callback(cb):
    uid, data, cid = cb["from"]["id"], cb.get("data") or "", cb["id"]
    mid = (cb.get("message") or {}).get("message_id")
    if data in ("r:1", "r:0"):
        tg.tg_answer_cb(cid)
        return remind_toggle(uid, data == "r:1")
    if uid not in config.OWNER_IDS:
        return tg.tg_answer_cb(cid)
    key, _, arg = data.partition(":")
    if key == "d":
        tg.tg_answer_cb(cid)
        db.delete_tx(int(arg))
        return tg.tg_edit(uid, mid, "Dihapus 🗑 Catatan dibatalkan.")
    if key == "rep":
        tg.tg_answer_cb(cid)
        return send_report(uid, arg)
    d = draft(uid)
    if not d or d["msg_id"] != mid:
        tg.tg_answer_cb(cid, STALE)
        return tg.tg_edit(uid, mid, buttons=[]) if mid else None
    tg.tg_answer_cb(cid)
    if key == "x":
        drafts.pop(uid, None)
        tg.tg_edit(uid, mid, "Oke, dibatalkan. Kapan pun siap, ketik lagi ya 🙂")
    elif key == "j":
        d["jenis"] = "masuk" if arg == "m" else "keluar"
        show(uid, d, ASK_INPUT, f"Oke, <b>{'Pemasukan' if arg == 'm' else 'Pengeluaran'}</b>. Ketik nominal + keterangan "
                                "(contoh: <code>35000 nasi padang</code>) atau kirim foto struk 📸.", [])
    elif key == "a":
        d["jumlah"] = int(arg)
        after_amount(uid, d)
    elif key == "c" and arg.isdigit() and int(arg) < len(d["cats"]):
        d["kategori"], d["subkategori"] = d["cats"][int(arg)], None
        pick_sub(uid, d)
    elif key == "s" and arg.isdigit() and int(arg) < len(d["subs"]):
        d["subkategori"] = d["subs"][int(arg)]
        confirm(uid, d)
    elif key == "b":
        pick_kategori(uid, d)
    elif key == "e" and arg == "t":
        d["jenis"] = "masuk" if d["jenis"] == "keluar" else "keluar"
        d["kategori"] = d["subkategori"] = None
        d["guess"] = parse.guess_kategori(d["catatan"], d["jenis"])
        pick_kategori(uid, d)
    elif key == "e":
        show(uid, d, ASK_JUMLAH, head(d) + "\n\n✏️ Ketik nominal barunya ya (contoh: <code>35000</code>)", [[BATAL]])
    elif key == "ok" and d["step"] == CONFIRM:
        save(uid, d)
    elif key == "ok" and d["step"] == ASK_JUMLAH and d["jumlah"]:
        after_amount(uid, d)


def command(msg):
    t = msg.get("text") or ""
    return t.split()[0].split("@")[0].lower() if t.startswith("/") else None


def handle_update(update):
    """Route one Telegram update (message or callback_query)."""
    if "callback_query" in update:
        return on_callback(update["callback_query"])
    msg = update.get("message")
    if not msg or "from" not in msg:
        return
    if msg["chat"]["type"] != "private":
        if command(msg) == "/start":
            tg.tg_send(msg["chat"]["id"], "Aku hanya bekerja di chat pribadi 🙂")
        return
    uid = msg["from"]["id"]
    if uid not in config.OWNER_IDS:
        return on_guest(uid, msg)
    photo, doc = msg.get("photo"), msg.get("document") or {}
    if photo:
        return on_photo(uid, msg, max(photo, key=lambda p: p["width"] * p["height"]))
    if (doc.get("mime_type") or "").startswith("image/"):
        return on_photo(uid, msg, doc)
    text, cmd = (msg.get("text") or "").strip(), command(msg)
    if cmd:
        on_command(uid, msg, cmd)
    elif text == "📝 Catat Pengeluaran":
        ask_jenis(uid)
    elif text == "📊 Lihat Pengeluaran":
        lihat(uid)
    elif text:
        on_text(uid, text)


def setup():
    """Idempotent boot: the command list and (HTTPS only) the web_app menu button."""
    tg.tg_api("setMyCommands", {"commands": json.dumps([{"command": c, "description": d} for c, d in COMMANDS])})
    if report.WEB_APP:
        tg.tg_api("setChatMenuButton", {"menu_button": json.dumps({"type": "web_app", "text": "📊 Dashboard", **report.WEB_APP})})


def poll_forever(stop):
    """Long-poll getUpdates from offset 0 (the backlog is processed, never skipped) until stop is set."""
    global poll_status
    offset = 0
    try:
        setup()
    except Exception as e:
        log.warning("setup gagal: %s", e)
    log.info("polling started")
    while not stop.is_set():
        try:
            res = tg.tg_api("getUpdates", {"timeout": 50, "offset": offset,
                                           "allowed_updates": json.dumps(["message", "callback_query"])}, timeout=65)
            poll_status = "ok"
        except Exception as e:
            if "conflict" in str(e).lower():
                poll_status = "conflict"
            log.warning("getUpdates gagal: %s", e)
            stop.wait(3)
            continue
        for u in res.get("result", []):
            offset = u["update_id"] + 1
            try:
                handle_update(u)
            except Exception as e:
                log.exception("update %s gagal", u["update_id"])
                report.alert(f"⚠️ Finn Finn error: {type(e).__name__}: {str(e)[:120]}")
