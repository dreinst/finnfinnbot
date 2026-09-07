import hashlib
import hmac
import json
import time
import unittest
from urllib.parse import urlencode

from finnfinn.web import dev_bypass_allowed, validate_init_data

TOKEN = "123456:FAKE-token-for-tests"
OWNERS = {705153966}


def build(user, auth_date=None, token=TOKEN, tamper=False, drop_hash=False):
    pairs = {"auth_date": str(int(auth_date or time.time())), "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
             "user": json.dumps(user, separators=(",", ":"))}
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    h = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    if tamper:
        pairs["user"] = json.dumps({**user, "id": 705153966}, separators=(",", ":"))
    if not drop_hash:
        pairs["hash"] = h
    return urlencode(pairs)


class InitDataTest(unittest.TestCase):
    def test_owner(self):
        u = validate_init_data(build({"id": 705153966, "first_name": "Donny"}), TOKEN)
        self.assertEqual(u["first_name"], "Donny")
        self.assertIn(u["id"], OWNERS)

    def test_guest(self):
        u = validate_init_data(build({"id": 1769749405, "first_name": "Andrew"}), TOKEN)
        self.assertNotIn(u["id"], OWNERS)

    def test_tampered_user(self):
        self.assertIsNone(validate_init_data(build({"id": 1769749405, "first_name": "Andrew"}, tamper=True), TOKEN))

    def test_wrong_token(self):
        self.assertIsNone(validate_init_data(build({"id": 705153966}), "999:other"))

    def test_stale(self):
        self.assertIsNone(validate_init_data(build({"id": 705153966}, auth_date=time.time() - 25 * 3600), TOKEN))
        self.assertIsNotNone(validate_init_data(build({"id": 705153966}, auth_date=time.time() - 23 * 3600), TOKEN))
        self.assertIsNone(validate_init_data(build({"id": 705153966}, auth_date=time.time() + 3600), TOKEN))

    def test_missing(self):
        self.assertIsNone(validate_init_data(build({"id": 705153966}, drop_hash=True), TOKEN))
        self.assertIsNone(validate_init_data("", TOKEN))
        self.assertIsNone(validate_init_data("hash=abc&auth_date=1", TOKEN))

    def test_hostile(self):
        self.assertIsNone(validate_init_data("user=%7B%7D&auth_date=1&hash=%C3%A9", TOKEN))
        self.assertIsNone(validate_init_data(build({"id": 705153966}, auth_date="9" * 400), TOKEN))
        self.assertIsNone(validate_init_data(build(1), TOKEN))
        self.assertIsNone(validate_init_data(build([]), TOKEN))
        self.assertIsNone(validate_init_data(build({"id": "705153966"}), TOKEN))


class DevBypassTest(unittest.TestCase):
    def test_local_peer_and_localhost_host(self):
        for peer in ("127.0.0.1", "172.17.0.1", "192.168.65.1", "10.0.0.7", "::1"):
            for host in ("localhost", "localhost:8080", "127.0.0.1", "127.0.0.1:8080", "LOCALHOST:8080"):
                with self.subTest(peer=peer, host=host):
                    self.assertTrue(dev_bypass_allowed(peer, host))

    def test_refused(self):
        self.assertFalse(dev_bypass_allowed("8.8.8.8", "localhost"))
        self.assertFalse(dev_bypass_allowed("172.17.0.1", "finnfinn.example"))
        self.assertFalse(dev_bypass_allowed("127.0.0.1", "finnfinn.187.53.129.205.sslip.io"))
        self.assertFalse(dev_bypass_allowed("127.0.0.1", "localhost.evil.com"))
        self.assertFalse(dev_bypass_allowed("127.0.0.1", "127.0.0.1.evil.com"))
        self.assertFalse(dev_bypass_allowed("127.0.0.1", ""))
        self.assertFalse(dev_bypass_allowed("garbage", "localhost"))


if __name__ == "__main__":
    unittest.main()
