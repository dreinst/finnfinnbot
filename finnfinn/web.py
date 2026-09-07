import hashlib
import hmac
import ipaddress
import json
import logging
import mimetypes
import os
import re
import sqlite3
import threading
import time
import urllib.parse
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import bot, config, db, report, tg

log = logging.getLogger("finnfinn.web")
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
BOOT = str(int(time.time()))
HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' https://telegram.org https://cdn.tailwindcss.com https://cdn.jsdelivr.net "
        "'unsafe-inline' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data: blob: https://t.me https://*.telegram.org "
        "https://*.telegram-cdn.org; worker-src 'self' blob:; connect-src 'self' https://cdn.jsdelivr.net; "
        "frame-ancestors https://web.telegram.org https://*.telegram.org"),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}
TYPES = {".html": "text/html; charset=utf-8", ".js": "application/javascript; charset=utf-8", ".gz": "application/gzip"}
BODY_MAX = 65536
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
TIME_RE = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
HOST_RE = re.compile(r"(localhost|127\.0\.0\.1)(:\d+)?")

_buckets = {}  # key → (tokens, last monotonic)
_lock = threading.Lock()


def validate_init_data(init_data, bot_token):
    """Telegram Mini App initData HMAC check → the user dict, or None (bad hash, stale auth_date, no user)."""
    pairs = dict(urllib.parse.parse_qsl(init_data or "", keep_blank_values=True))
    given = pairs.pop("hash", None)
    if not given or "user" not in pairs:
        return None
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest(), given):
            return None
        auth = int(pairs.get("auth_date", 0))
        if time.time() - auth > 86400 or auth - time.time() > 300:
            return None
        u = json.loads(pairs["user"])
    except (ValueError, TypeError, OverflowError):
        return None
    return u if isinstance(u, dict) and isinstance(u.get("id"), int) else None


def dev_bypass_allowed(peer, host):
    """DEV_NO_AUTH applies only to loopback/RFC1918 peers that addressed localhost or 127.0.0.1 (Traefik carries the FQDN)."""
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return (ip.is_loopback or ip.is_private) and HOST_RE.fullmatch(host.strip().lower()) is not None


def _allow(key, per_min):
    """Token bucket (per_min tokens, refilled over 60 s) → False when the bucket is empty."""
    now = time.monotonic()
    with _lock:
        if len(_buckets) > 10000:
            for k in [k for k, (_, last) in _buckets.items() if now - last > 60]:
                del _buckets[k]
        tokens, last = _buckets.get(key, (per_min, now))
        tokens = min(per_min, tokens + (now - last) * per_min / 60)
        _buckets[key] = (max(tokens - 1, 0), now)
        return tokens >= 1


def _tx_error(tx, leaves):
    """→ Indonesian message for the first invalid field of a full Tx dict, else None."""
    if tx.get("jenis") not in ("masuk", "keluar"):
        return "jenis harus masuk atau keluar"
    if type(tx.get("jumlah")) is not int or not 1 <= tx["jumlah"] <= 100_000_000_000:
        return "jumlah harus 1 – 100.000.000.000"
    if not isinstance(tx.get("catatan", ""), str) or len(tx.get("catatan", "")) > 80:
        return "catatan maks 80 karakter"
    try:
        if not isinstance(tx.get("tanggal"), str) or not DATE_RE.fullmatch(tx["tanggal"]):
            raise ValueError
        date.fromisoformat(tx["tanggal"])
    except ValueError:
        return "tanggal harus YYYY-MM-DD"
    w = tx.get("waktu", "")
    if not isinstance(w, str) or (w and not TIME_RE.fullmatch(w)):
        return "waktu harus HH:MM"
    if (tx["jenis"], tx.get("kategori"), tx.get("subkategori")) not in leaves:
        return "kategori tidak dikenal"
    return None


def _cat_error(items):
    if not isinstance(items, list) or not items:
        return "kategori kosong"
    seen = set()
    for c in items:
        if not isinstance(c, dict) or c.get("jenis") not in ("masuk", "keluar"):
            return "jenis harus masuk atau keluar"
        if not all(isinstance(c.get(k), str) and c[k].strip() for k in ("kategori", "subkategori")):
            return "kategori dan subkategori wajib diisi"
        if "id" in c and type(c["id"]) is not int:
            return "id harus angka"
        if c.get("aktif", 1) not in (0, 1) or not isinstance(c.get("ikon", ""), str) or type(c.get("urutan", 0)) is not int:
            return "kategori tidak valid"
        key = (c["jenis"], c["kategori"], c["subkategori"])
        if key in seen:
            return "kategori ganda: " + " / ".join(key)
        seen.add(key)
    return None


class Handler(BaseHTTPRequestHandler):
    timeout = 30

    def log_request(self, *_):
        pass

    def finish(self):
        super().finish()
        db.close()  # one thread per request: don't leave the connection to GC

    def _send(self, code, body, ctype, cache=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        for k, v in HEADERS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _static(self, rel):
        path = os.path.normpath(os.path.join(WEB_DIR, urllib.parse.unquote(rel)))
        if not path.startswith(WEB_DIR + os.sep) or not os.path.isfile(path):
            return self._json(404, {"error": "tidak ditemukan"})
        ext = os.path.splitext(path)[1].lower()
        cache = "public,max-age=31536000,immutable" if ext == ".gz" else "no-cache" if ext in (".html", ".js") else None
        with open(path, "rb") as f:
            body = f.read()
        if rel == "index.html":
            body = body.replace(b"__V__", BOOT.encode())
        self._send(200, body, TYPES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream", cache)

    def _healthz(self):
        try:
            db.connect().execute("SELECT 1")
        except Exception as e:
            log.error("healthz db: %s", e)
            return self._json(500, {"ok": False, "db": "error"})
        self._json(200, {"ok": True, "db": "ok", "last_tick": db.meta_get("last_tick"),
                         "ticker": "ok" if time.monotonic() - report.last_tick < 300 else "stale", "poll": bot.poll_status})

    def _avatar(self, user_id):
        """Proxy the user's real Telegram profile photo (never the bot token) so <img> can show it without initData headers."""
        try:
            file_id = tg.tg_user_photo(user_id)
            data = tg.tg_get_file(file_id, 512 * 1024) if file_id else None
        except Exception as e:
            log.warning("ambil foto profil gagal: %s", e)
            data = None
        if not data:
            return self._json(404, {"error": "tidak ada foto"})
        self._send(200, data, "image/jpeg", "private, max-age=3600")

    def _user(self):
        """Authenticated Telegram user dict, or None after the 401/429 response was sent."""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("tma ") and auth[4:].strip():
            u = validate_init_data(auth[4:].strip(), config.BOT_TOKEN)
        elif config.DEV_NO_AUTH and dev_bypass_allowed(self.client_address[0], self.headers.get("Host", "")):
            u = {"id": config.FIRST_OWNER or 0, "first_name": "Dev"}
        else:
            u = None
        if u is None:
            ip = (self.headers.get("X-Forwarded-For") or self.client_address[0]).split(",")[-1].strip()  # last hop: the one the proxy appended
            if _allow(("ip", ip), 20):
                self._json(401, {"error": "initData tidak valid"})
            else:
                self._json(429, {"error": "terlalu banyak permintaan"})
            return None
        if not _allow(("uid", u["id"]), 120):
            self._json(429, {"error": "terlalu banyak permintaan"})
            return None
        return u

    def _body(self):
        """Parsed JSON body ({} when empty or null), or None after a 413/400 response was sent."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0 or n > BODY_MAX:
            self._json(413, {"error": "terlalu besar"})
            return None
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            self._json(400, {"error": "JSON tidak valid"})
            return None
        return {} if body is None else body

    def _api(self, method, path, query):
        u = self._user()
        if u is None:
            return
        owner = u["id"] in config.OWNER_IDS
        if path == "/api/me" and method == "GET":
            return self._json(200, {"mode": "owner" if owner else "guest", "nama": u.get("first_name", ""), "tg_id": u["id"]})
        if path == "/api/remind" and method == "POST":
            body = self._body()
            if body is None:
                return
            on = isinstance(body, dict) and body.get("on") is True
            if owner or not on:
                if not owner:
                    db.guest_set_remind(u["id"], False)
                return self._json(200, {"ok": True})
            return self._json(200, {"ok": True} if db.guest_set_remind(u["id"], True) else {"ok": False, "reason": "start"})
        if path == "/api/avatar" and method == "GET":
            return self._avatar(u["id"])
        if not owner:
            return self._json(403, {"error": "khusus owner"})
        if path == "/api/tx" and method == "GET":
            frm, to = query.get("from", [""])[0], query.get("to", [""])[0]
            try:
                span = (date.fromisoformat(to) - date.fromisoformat(frm)).days
            except ValueError:
                return self._json(400, {"error": "from/to harus YYYY-MM-DD"})
            if not 0 <= span <= 400:
                return self._json(400, {"error": "rentang maks 400 hari"})
            return self._json(200, db.list_tx(frm, to))
        if path == "/api/tx" and method == "POST":
            body = self._body()
            if body is None:
                return
            if not isinstance(body, dict):
                return self._json(400, {"error": "JSON tidak valid"})
            leaves = {(c["jenis"], c["kategori"], c["subkategori"]) for c in db.categories()}
            err = _tx_error(body, leaves)
            if err:
                return self._json(400, {"error": err})
            body["sumber"] = "struk" if body.get("sumber") == "struk" else "app"
            return self._json(201, db.add_tx(body))
        if path.startswith("/api/tx/") and method in ("PUT", "DELETE"):
            try:
                tx_id = int(path[8:])
            except ValueError:
                return self._json(404, {"error": "tidak ditemukan"})
            if method == "DELETE":
                return self._json(200, {"ok": True}) if db.delete_tx(tx_id) else self._json(404, {"error": "tidak ditemukan"})
            body = self._body()
            if body is None:
                return
            cur = db.get_tx(tx_id)
            if cur is None:
                return self._json(404, {"error": "tidak ditemukan"})
            if not isinstance(body, dict):
                return self._json(400, {"error": "JSON tidak valid"})
            patch = {k: body[k] for k in db.TX_COLS if k in body and k != "sumber"}
            leaves = {(c["jenis"], c["kategori"], c["subkategori"]) for c in db.categories()}
            err = _tx_error({**cur, **patch}, leaves)
            if err:
                return self._json(400, {"error": err})
            return self._json(200, db.update_tx(tx_id, patch))
        if path == "/api/categories" and method == "GET":
            return self._json(200, db.categories())
        if path == "/api/categories" and method == "PUT":
            body = self._body()
            if body is None:
                return
            err = _cat_error(body)
            if err:
                return self._json(400, {"error": err})
            try:
                db.save_categories(body)
            except sqlite3.IntegrityError:
                return self._json(400, {"error": "kategori ganda"})
            return self._json(200, db.categories())
        self._json(404, {"error": "tidak ditemukan"})

    def _dispatch(self):
        parts = urllib.parse.urlsplit(self.path)
        path = parts.path
        if path.startswith("/api/"):
            self._api(self.command, path, urllib.parse.parse_qs(parts.query))
        elif self.command != "GET":
            self._json(404, {"error": "tidak ditemukan"})
        elif path == "/healthz":
            self._healthz()
        elif path == "/":
            self._static("index.html")
        elif path.startswith("/static/"):
            self._static(path[8:])
        else:
            self._json(404, {"error": "tidak ditemukan"})

    do_GET = do_POST = do_PUT = do_DELETE = _dispatch


def serve(stop):
    """Blocking HTTP server on config.PORT until stop is set."""
    srv = ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler)
    srv.daemon_threads = True
    threading.Thread(target=lambda: (stop.wait(), srv.shutdown()), daemon=True).start()
    log.info("http on :%d", config.PORT)
    srv.serve_forever()
