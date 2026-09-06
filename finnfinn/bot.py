import json
import logging

from . import tg

log = logging.getLogger("finnfinn.bot")
drafts = {}  # uid → {step, jenis, jumlah, catatan, tanggal, waktu, sumber, kategori, cats, subs, msg_id, ts}
poll_status = "ok"  # "ok" | "conflict" (409 seen on the last getUpdates)


def handle_update(update):
    """Route one Telegram update (Phase 0: /start echo in private chats, everything else ignored)."""
    msg = update.get("message") or {}
    if msg.get("chat", {}).get("type") != "private":
        return
    if (msg.get("text") or "").startswith("/start"):
        tg.tg_send(msg["chat"]["id"], "Finn Finn siap 🙂")


def poll_forever(stop):
    """Long-poll getUpdates from offset 0 (the backlog is processed, never skipped) until stop is set."""
    global poll_status
    offset = 0
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
            except Exception:
                log.exception("update %s gagal", u["update_id"])
