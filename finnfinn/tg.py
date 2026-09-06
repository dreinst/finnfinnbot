import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

from . import config

log = logging.getLogger("finnfinn.tg")
API = "https://api.telegram.org"
_bad_token_logged = False


def tg_api(method, params=None, timeout=30, retries=3):
    """Call a Bot API method; 429 waits retry_after, 409 sleeps 5 s, 401/404 (bad token) sleep 30 s (all raise except 429)."""
    global _bad_token_logged
    data = urllib.parse.urlencode(params or {}).encode()
    for attempt in range(retries + 1):
        req = urllib.request.Request(f"{API}/bot{config.BOT_TOKEN}/{method}", data=data)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            try:
                body = json.loads(e.read().decode())
            except Exception:
                body = {}
            desc = body.get("description") or f"HTTP {e.code}"
            wait = (body.get("parameters") or {}).get("retry_after")
            if e.code == 429 and wait and attempt < retries:
                log.warning("429 pada %s, tunggu %ss", method, wait)
                time.sleep(int(wait) + 1)
                continue
            if e.code == 409:
                log.warning("409 pada %s: %s", method, desc)
                time.sleep(5)
            elif e.code in (401, 404):  # 404 = token shape Telegram cannot even route
                if not _bad_token_logged:
                    log.error("%d: BOT_TOKEN ditolak Telegram", e.code)
                    _bad_token_logged = True
                time.sleep(30)
            raise RuntimeError(desc)


def _markup(buttons):
    if buttons and buttons[0] and isinstance(buttons[0][0], str):
        return {"keyboard": [[{"text": b} for b in row] for row in buttons], "resize_keyboard": True, "is_persistent": True}
    return {"inline_keyboard": buttons or []}


def tg_send(chat_id, text, parse_mode="HTML", buttons=None):
    """sendMessage in ≤3900-char chunks; buttons = inline rows of dicts or reply rows of str."""
    r = None
    chunks = [text[i:i + 3900] for i in range(0, max(len(text), 1), 3900)]
    for n, chunk in enumerate(chunks):
        params = {"chat_id": chat_id, "text": chunk}
        if parse_mode:
            params["parse_mode"] = parse_mode
        if buttons is not None and n == len(chunks) - 1:
            params["reply_markup"] = json.dumps(_markup(buttons))
        r = tg_api("sendMessage", params)
    return r


def tg_edit(chat_id, msg_id, text=None, buttons=None, parse_mode="HTML"):
    """editMessageText, or only the inline keyboard when text is None ([] clears it); 'not modified' is ignored."""
    params = {"chat_id": chat_id, "message_id": msg_id, "reply_markup": json.dumps({"inline_keyboard": buttons or []})}
    if text is not None:
        params["text"] = text[:4000]
        if parse_mode:
            params["parse_mode"] = parse_mode
    try:
        return tg_api("editMessageText" if text is not None else "editMessageReplyMarkup", params)
    except RuntimeError as e:
        if "not modified" not in str(e).lower():
            raise
        return None


def tg_answer_cb(cb_id, text=None):
    """answerCallbackQuery; failures (e.g. 'query is too old') never break the flow."""
    params = {"callback_query_id": cb_id}
    if text:
        params["text"] = text[:200]
    try:
        tg_api("answerCallbackQuery", params, timeout=15)
    except Exception as e:
        log.log(logging.DEBUG if "too old" in str(e).lower() else logging.WARNING, "answerCallbackQuery: %s", e)


def tg_get_file(file_id, max_bytes):
    """Download a file into memory; ValueError when larger than max_bytes. The URL is never logged."""
    info = tg_api("getFile", {"file_id": file_id})["result"]
    if (info.get("file_size") or 0) > max_bytes:
        raise ValueError("file terlalu besar")
    with urllib.request.urlopen(f"{API}/file/bot{config.BOT_TOKEN}/{info['file_path']}", timeout=60) as r:
        data = r.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise ValueError("file terlalu besar")
    return data


def tg_send_document(chat_id, path, caption=""):
    boundary = "----finnfinn" + uuid.uuid4().hex
    fields = {"chat_id": str(chat_id)}
    if caption:
        fields["caption"] = caption[:1000]
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode() for k, v in fields.items()]
    with open(path, "rb") as f:
        content = f.read()
    fname = path.rsplit("/", 1)[-1]
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{fname}"\r\n'
                 f'Content-Type: application/octet-stream\r\n\r\n'.encode())
    parts += [content, f"\r\n--{boundary}--\r\n".encode()]
    req = urllib.request.Request(f"{API}/bot{config.BOT_TOKEN}/sendDocument", data=b"".join(parts),
                                 headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())
