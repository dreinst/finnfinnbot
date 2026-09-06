import os
import sqlite3
import tempfile
import unittest

from finnfinn import db

TX = {"jenis": "keluar", "jumlah": 35000, "kategori": "Makanan & Minuman", "subkategori": "Makan di luar",
      "catatan": "Nasi padang", "tanggal": "2026-09-06", "waktu": "14:03"}


class DbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db.init(os.path.join(self.tmp.name, "t.db"))

    def tearDown(self):
        db.close()
        self.tmp.cleanup()

    def test_seed_counts(self):
        cats = db.categories()
        self.assertEqual(sum(c["jenis"] == "masuk" for c in cats), 4)
        self.assertEqual(sum(c["jenis"] == "keluar" for c in cats), 15)
        self.assertEqual(db.meta_get("schema_version"), "1")
        db.init(db._path)  # idempotent: no double seed
        db.seed()
        self.assertEqual(len(db.categories()), 19)

    def test_wal(self):
        self.assertEqual(db.connect().execute("PRAGMA journal_mode").fetchone()[0], "wal")

    def test_crud(self):
        tx = db.add_tx(TX)
        self.assertEqual(tx["sumber"], "teks")
        self.assertEqual(db.get_tx(tx["id"])["jumlah"], 35000)
        upd = db.update_tx(tx["id"], {"jumlah": 40000, "bogus": 1})
        self.assertEqual(upd["jumlah"], 40000)
        self.assertIsNotNone(upd["updated_at"])
        self.assertTrue(db.delete_tx(tx["id"]))
        self.assertFalse(db.delete_tx(tx["id"]))
        self.assertIsNone(db.get_tx(tx["id"]))

    def test_list_range(self):
        for d in ("2026-09-01", "2026-09-05", "2026-09-06", "2026-10-01"):
            db.add_tx({**TX, "tanggal": d})
        rows = db.list_tx("2026-09-01", "2026-09-30")
        self.assertEqual([r["tanggal"] for r in rows], ["2026-09-06", "2026-09-05", "2026-09-01"])

    def test_summary(self):
        db.add_tx(TX)
        db.add_tx({**TX, "jumlah": 15000})
        db.add_tx({**TX, "jenis": "masuk", "jumlah": 7500000, "kategori": "Gaji", "subkategori": "Umum", "tanggal": "2026-09-01"})
        by_cat, by_day = db.summary("2026-09-01", "2026-09-30")
        self.assertEqual([(r["jenis"], r["total"], r["n"]) for r in by_cat], [("masuk", 7500000, 1), ("keluar", 50000, 2)])
        self.assertEqual([(r["tanggal"], r["jenis"], r["total"]) for r in by_day],
                         [("2026-09-01", "masuk", 7500000), ("2026-09-06", "keluar", 50000)])

    def test_rename_cascade(self):
        tx = db.add_tx(TX)
        cats = db.categories()
        for c in cats:
            if c["subkategori"] == "Makan di luar":
                c["subkategori"] = "Resto"
        db.save_categories(cats)
        self.assertEqual(db.get_tx(tx["id"])["subkategori"], "Resto")
        self.assertEqual(len(db.categories()), 19)
        with self.assertRaises(sqlite3.IntegrityError):
            db.save_categories(cats + [{"jenis": "keluar", "kategori": "Makanan & Minuman", "subkategori": "Resto"}])
        with self.assertRaises(ValueError):
            db.save_categories([])
        self.assertEqual(len(db.categories()), 19)

    def test_claim(self):
        self.assertTrue(db.claim("harian", "2026-09-06"))
        self.assertFalse(db.claim("harian", "2026-09-06"))
        db.unclaim("harian", "2026-09-06")
        self.assertTrue(db.claim("harian", "2026-09-06"))

    def test_guests(self):
        self.assertEqual(db.guest_set_remind(42, True), 0)
        self.assertEqual(db.guests_to_remind(), [])
        db.guest_upsert(42)
        db.guest_upsert(42)
        self.assertEqual(db.guest_set_remind(42, True), 1)
        self.assertEqual(db.guests_to_remind(), [42])
        db.guest_delete(42)
        db.guest_delete(42)
        self.assertEqual(db.guests_to_remind(), [])

    def test_meta(self):
        db.meta_set("last_tick", "x")
        db.meta_set("last_tick", "y")
        self.assertEqual(db.meta_get("last_tick"), "y")
        self.assertEqual(db.meta_get("nope", 0), 0)

    def test_snapshot(self):
        db.add_tx(TX)
        dest = db.snapshot(os.path.join(self.tmp.name, "backups", "snap.db"))
        self.assertTrue(os.path.isfile(dest))
        con = sqlite3.connect(dest)
        self.assertEqual(con.execute("PRAGMA quick_check").fetchone()[0], "ok")
        self.assertEqual(con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)
        con.close()
        db.snapshot(dest)  # overwrite is fine


if __name__ == "__main__":
    unittest.main()
