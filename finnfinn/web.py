import hashlib
import hmac
import json
import logging
import mimetypes
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import bot, config, db, report

log = logging.getLogger("finnfinn.web")
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
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
            self._send(200, f.read(), TYPES.get(ext) or mimetypes.guess_type(path)[0] or "application/octet-stream", cache)

    def _healthz(self):
        try:
            db.connect().execute("SELECT 1")
        except Exception as e:
            log.error("healthz db: %s", e)
            return self._json(500, {"ok": False, "db": "error"})
        self._json(200, {"ok": True, "db": "ok", "last_tick": db.meta_get("last_tick"),
                         "ticker": "ok" if time.monotonic() - report.last_tick < 300 else "stale", "poll": bot.poll_status})

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/healthz":
            self._healthz()
        elif path.startswith("/api/"):
            self._json(501, {"error": "belum tersedia"})
        elif path == "/":
            self._static("index.html")
        elif path.startswith("/static/"):
            self._static(path[8:])
        else:
            self._json(404, {"error": "tidak ditemukan"})

    def do_POST(self):
        if self.path.startswith("/api/"):
            self._json(501, {"error": "belum tersedia"})
        else:
            self._json(404, {"error": "tidak ditemukan"})

    do_PUT = do_DELETE = do_POST


def serve(stop):
    """Blocking HTTP server on config.PORT until stop is set."""
    srv = ThreadingHTTPServer(("0.0.0.0", config.PORT), Handler)
    srv.daemon_threads = True
    threading.Thread(target=lambda: (stop.wait(), srv.shutdown()), daemon=True).start()
    log.info("http on :%d", config.PORT)
    srv.serve_forever()
