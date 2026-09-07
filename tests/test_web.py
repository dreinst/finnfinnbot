import http.client
import json
import os
import socket
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer

from finnfinn import config, db, web

from .test_initdata import TOKEN, build

OWNER, GUEST = 705153966, 1769749405
TX = {"jenis": "keluar", "jumlah": 35000, "kategori": "Makanan & Minuman", "subkategori": "Makan di luar",
      "catatan": "Nasi padang", "tanggal": "2026-09-06", "waktu": "14:03"}


class WebTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        db.init(os.path.join(cls.tmp.name, "t.db"))
        cls.saved = {k: getattr(config, k) for k in ("BOT_TOKEN", "OWNER_IDS", "FIRST_OWNER", "DEV_NO_AUTH")}
        config.BOT_TOKEN, config.OWNER_IDS, config.FIRST_OWNER, config.DEV_NO_AUTH = TOKEN, {OWNER}, OWNER, False
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
        cls.srv.daemon_threads = True
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.port = cls.srv.server_address[1]
        cls.owner = "tma " + build({"id": OWNER, "first_name": "Donny"})
        cls.guest = "tma " + build({"id": GUEST, "first_name": "Andrew"})

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        for k, v in cls.saved.items():
            setattr(config, k, v)
        db.close()
        cls.tmp.cleanup()

    def setUp(self):
        web._buckets.clear()
        for t in ("transactions", "guests", "categories"):
            db.connect().execute("DELETE FROM " + t)
        db.seed()

    def req(self, method, path, body=None, auth=None, host=None, raw=None, xff=None):
        con = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        headers = {}
        if auth:
            headers["Authorization"] = auth
        if host is not None:
            headers["Host"] = host
        if xff:
            headers["X-Forwarded-For"] = xff
        data = raw
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        con.request(method, path, body=data, headers=headers)
        r = con.getresponse()
        raw = r.read()
        con.close()
        ct = r.getheader("Content-Type", "")
        return r.status, (json.loads(raw) if ct.startswith("application/json") else raw), r.headers

    def test_me(self):
        self.assertEqual(self.req("GET", "/api/me", auth=self.owner)[1], {"mode": "owner", "nama": "Donny", "tg_id": OWNER})
        self.assertEqual(self.req("GET", "/api/me", auth=self.guest)[1], {"mode": "guest", "nama": "Andrew", "tg_id": GUEST})

    def test_auth_errors(self):
        self.assertEqual(self.req("GET", "/api/me")[:2], (401, {"error": "initData tidak valid"}))
        self.assertEqual(self.req("GET", "/api/me", auth="tma ")[0], 401)
        self.assertEqual(self.req("GET", "/api/me", auth="Bearer x")[0], 401)
        tampered = "tma " + build({"id": GUEST, "first_name": "Andrew"}, tamper=True)
        self.assertEqual(self.req("GET", "/api/me", auth=tampered)[0], 401)
        self.assertEqual(self.req("GET", "/api/tx?from=2026-09-01&to=2026-09-30", auth=tampered)[0], 401)

    def test_failed_auth_limit(self):
        for _ in range(20):
            self.assertEqual(self.req("GET", "/api/me", auth="tma nope")[0], 401)
        self.assertEqual(self.req("GET", "/api/me", auth="tma nope")[:2], (429, {"error": "terlalu banyak permintaan"}))
        self.assertEqual(self.req("GET", "/api/me", auth=self.owner)[0], 200)  # valid initData is not blocked

    def test_failed_auth_limit_xff_last_hop(self):
        for i in range(20):  # a spoofed first hop does not open a new bucket
            self.assertEqual(self.req("GET", "/api/me", auth="tma nope", xff=f"1.2.3.{i}, 9.9.9.9")[0], 401)
        self.assertEqual(self.req("GET", "/api/me", auth="tma nope", xff="1.2.3.99, 9.9.9.9")[0], 429)
        self.assertEqual(self.req("GET", "/api/me", auth="tma nope", xff="9.9.9.9, 5.5.5.5")[0], 401)

    def test_uid_bucket(self):
        for _ in range(120):
            self.assertTrue(web._allow(("uid", 1), 120))
        self.assertFalse(web._allow(("uid", 1), 120))
        self.assertTrue(web._allow(("uid", 2), 120))

    def test_guest_forbidden(self):
        for method, path in (("GET", "/api/tx?from=2026-09-01&to=2026-09-30"), ("POST", "/api/tx"), ("PUT", "/api/tx/1"),
                             ("DELETE", "/api/tx/1"), ("GET", "/api/categories"), ("PUT", "/api/categories")):
            with self.subTest(path=path):
                self.assertEqual(self.req(method, path, body={} if method != "GET" else None, auth=self.guest)[:2],
                                 (403, {"error": "khusus owner"}))

    def test_tx_crud(self):
        st, tx, _ = self.req("POST", "/api/tx", body=TX, auth=self.owner)
        self.assertEqual(st, 201)
        self.assertEqual((tx["jumlah"], tx["sumber"], tx["catatan"]), (35000, "app", "Nasi padang"))
        st, rows, _ = self.req("GET", "/api/tx?from=2026-09-01&to=2026-09-30", auth=self.owner)
        self.assertEqual((st, [r["id"] for r in rows]), (200, [tx["id"]]))
        st, upd, _ = self.req("PUT", f"/api/tx/{tx['id']}", body={"jumlah": 40000, "waktu": ""}, auth=self.owner)
        self.assertEqual((st, upd["jumlah"], upd["waktu"]), (200, 40000, ""))
        self.assertEqual(self.req("PUT", f"/api/tx/{tx['id']}", body={"subkategori": "Groceries"}, auth=self.owner)[1]["subkategori"],
                         "Groceries")
        self.assertEqual(self.req("PUT", f"/api/tx/{tx['id']}", body={"subkategori": "BBM"}, auth=self.owner)[0], 400)
        self.assertEqual(self.req("PUT", "/api/tx/999", body={"jumlah": 1}, auth=self.owner)[0], 404)
        self.assertEqual(self.req("PUT", "/api/tx/abc", body={"jumlah": 1}, auth=self.owner)[0], 404)
        self.assertEqual(self.req("DELETE", f"/api/tx/{tx['id']}", auth=self.owner)[:2], (200, {"ok": True}))
        self.assertEqual(self.req("DELETE", f"/api/tx/{tx['id']}", auth=self.owner)[0], 404)
        self.assertEqual(self.req("GET", "/api/tx?from=2026-09-01&to=2026-09-30", auth=self.owner)[1], [])

    def test_tx_validation(self):
        bad = [{**TX, "jumlah": 0}, {**TX, "jumlah": 10 ** 12}, {**TX, "jumlah": "35000"}, {**TX, "jumlah": True},
               {**TX, "subkategori": "Tidak Ada"}, {**TX, "jenis": "masuk"}, {**TX, "tanggal": "06/09/2026"},
               {**TX, "tanggal": "2026-02-30"}, {**TX, "waktu": "25:00"}, {**TX, "catatan": "x" * 81}, {**TX, "jenis": "x"}, []]
        for body in bad:
            with self.subTest(body=body):
                st, err, _ = self.req("POST", "/api/tx", body=body, auth=self.owner)
                self.assertEqual(st, 400)
                self.assertIn("error", err)
        st, tx, _ = self.req("POST", "/api/tx", body={**TX, "sumber": "struk", "catatan": ""}, auth=self.owner)
        self.assertEqual((st, tx["sumber"]), (201, "struk"))
        self.assertEqual(self.req("GET", "/api/tx?from=2025-01-01&to=2026-09-30", auth=self.owner)[0], 400)
        self.assertEqual(self.req("GET", "/api/tx?from=2026-09-30&to=2026-09-01", auth=self.owner)[0], 400)
        self.assertEqual(self.req("GET", "/api/tx?from=x&to=2026-09-01", auth=self.owner)[0], 400)
        self.assertEqual(self.req("GET", "/api/tx", auth=self.owner)[0], 400)

    def test_categories(self):
        st, cats, _ = self.req("GET", "/api/categories", auth=self.owner)
        self.assertEqual((st, len(cats)), (200, 19))
        self.assertEqual(self.req("PUT", "/api/categories", body=[], auth=self.owner)[0], 400)
        dup = {k: v for k, v in cats[0].items() if k != "id"}
        st, err, _ = self.req("PUT", "/api/categories", body=cats + [dup], auth=self.owner)
        self.assertEqual((st, err["error"][:14]), (400, "kategori ganda"))
        self.assertEqual(self.req("PUT", "/api/categories", body=[{"jenis": "keluar", "kategori": "", "subkategori": "x"}],
                                  auth=self.owner)[0], 400)
        for bad in ({"aktif": "x"}, {"ikon": {"a": 1}}, {"urutan": "1"}):
            with self.subTest(bad=bad):
                self.assertEqual(self.req("PUT", "/api/categories", body=[{**dup, **bad}], auth=self.owner)[:2],
                                 (400, {"error": "kategori tidak valid"}))
        tx = self.req("POST", "/api/tx", body=TX, auth=self.owner)[1]
        leaf = next(c for c in cats if c["subkategori"] == "Makan di luar")
        leaf["subkategori"] = "Jajan"
        st, new, _ = self.req("PUT", "/api/categories", body=cats, auth=self.owner)
        self.assertEqual((st, len(new)), (200, 19))
        self.assertEqual(db.get_tx(tx["id"])["subkategori"], "Jajan")

    def test_remind(self):
        self.assertEqual(self.req("POST", "/api/remind", body={"on": True}, auth=self.guest)[1], {"ok": False, "reason": "start"})
        self.assertEqual(self.req("POST", "/api/remind", body={"on": False}, auth=self.guest)[1], {"ok": True})
        self.assertEqual(db.guests_to_remind(), [])
        db.guest_upsert(GUEST)
        self.assertEqual(self.req("POST", "/api/remind", body={"on": True}, auth=self.guest)[1], {"ok": True})
        self.assertEqual(db.guests_to_remind(), [GUEST])
        self.assertEqual(self.req("POST", "/api/remind", body={"on": False}, auth=self.guest)[1], {"ok": True})
        self.assertEqual(db.guests_to_remind(), [])
        self.assertEqual(self.req("POST", "/api/remind", body={"on": True}, auth=self.owner)[1], {"ok": True})
        self.assertEqual(self.req("POST", "/api/remind", body="x", auth=self.guest)[1], {"ok": True})

    def test_body_too_large(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        s.sendall(f"POST /api/tx HTTP/1.1\r\nHost: x\r\nAuthorization: {self.owner}\r\nContent-Length: 70000\r\n\r\n".encode())
        self.assertTrue(s.recv(4096).startswith(b"HTTP/1.0 413"))
        s.close()

    def test_bad_or_empty_body(self):
        self.assertEqual(self.req("POST", "/api/tx", raw=b"{nope", auth=self.owner)[0], 400)
        for raw in (b"", b"null"):
            with self.subTest(raw=raw):
                self.assertEqual(self.req("POST", "/api/tx", raw=raw, auth=self.owner)[0], 400)
                self.assertEqual(self.req("PUT", "/api/categories", raw=raw, auth=self.owner)[0], 400)
                self.assertEqual(self.req("POST", "/api/remind", raw=raw, auth=self.guest)[:2], (200, {"ok": True}))

    def test_dev_no_auth(self):
        config.DEV_NO_AUTH = True
        try:
            self.assertEqual(self.req("GET", "/api/me", host="localhost:8080")[1], {"mode": "owner", "nama": "Dev", "tg_id": OWNER})
            self.assertEqual(self.req("GET", "/api/me", host="finnfinn.example")[0], 401)
            self.assertEqual(self.req("GET", "/api/me", auth="tma tampered", host="localhost")[0], 401)
            config.OWNER_IDS, config.FIRST_OWNER = set(), None
            self.assertEqual(self.req("GET", "/api/me", host="localhost:8080")[1], {"mode": "guest", "nama": "Dev", "tg_id": 0})
            self.assertEqual(self.req("GET", "/api/categories", host="localhost:8080")[0], 403)
        finally:
            config.DEV_NO_AUTH, config.OWNER_IDS, config.FIRST_OWNER = False, {OWNER}, OWNER
        self.assertEqual(self.req("GET", "/api/me", host="localhost:8080")[0], 401)

    def test_index_and_static(self):
        st, body, h = self.req("GET", "/")
        self.assertEqual((st, h["Content-Type"], h["Cache-Control"]), (200, "text/html; charset=utf-8", "no-cache"))
        self.assertIn("frame-ancestors https://web.telegram.org", h["Content-Security-Policy"])
        self.assertEqual((h["X-Content-Type-Options"], h["Referrer-Policy"]), ("nosniff", "no-referrer"))
        self.assertIn(("?v=" + web.BOOT).encode(), body)
        self.assertNotIn(b"__V__", body)
        st, _, h = self.req("GET", "/static/app.js")
        self.assertEqual((st, h["Content-Type"], h["Cache-Control"]), (200, "application/javascript; charset=utf-8", "no-cache"))
        st, _, h = self.req("GET", "/static/tessdata/ind.traineddata.gz")
        self.assertEqual((st, h["Content-Type"], h["Cache-Control"]), (200, "application/gzip", "public,max-age=31536000,immutable"))
        for path in ("/static/../finnfinn/config.py", "/static/%2e%2e/finnfinn/config.py", "/static/../../etc/passwd",
                     "/static/nope.js", "/static/", "/index.html", "/api/nope"):
            with self.subTest(path=path):
                self.assertEqual(self.req("GET", path, auth=self.owner)[0], 404)
        self.assertEqual(self.req("POST", "/")[0], 404)

    def test_healthz(self):
        st, body, _ = self.req("GET", "/healthz")
        self.assertEqual((st, body["ok"], body["db"]), (200, True, "ok"))


if __name__ == "__main__":
    unittest.main()
