import json
import unittest
from datetime import date
from pathlib import Path

from finnfinn.parse import guess_jenis, guess_kategori, parse_amount, parse_receipt, parse_text

TODAY = date(2026, 9, 6)
FIX = Path(__file__).parent / "fixtures" / "receipts"

# text → (jumlah, ambiguous, error)
AMOUNTS = [
    ("50000 kopi", 50000, False, None),
    ("gaji 7.500.000", 7500000, False, None),
    ("bensin 100rb", 100000, False, None),
    ("7,5jt bonus", 7500000, False, None),
    ("Rp 12,500 parkir", 12500, False, None),
    ("12.500,00", 12500, False, None),
    ("+200k refund", 200000, False, None),
    ("kemarin 35000 nasi padang", 35000, False, None),
    ("3/9 pulsa 50k", 50000, False, None),
    ("beli 2 kopi 30rb", 30000, False, None),
    ("50 kopi", 50, True, None),
    ("5 kopi", 5, False, "range"),
    ("1.5m saham", 1500000, False, None),
    ("2jt", 2000000, False, None),
    ("Rp12.500", 12500, False, None),
    ("rp. 25.000 makan siang", 25000, False, None),
    ("IDR 150000", 150000, False, None),
    ("50 000 bensin", 50000, False, None),
    ("1 juta", 1000000, False, None),
    ("250 ribu belanja", 250000, False, None),
    ("100k", 100000, False, None),
    ("10.000.000 thr", 10000000, False, None),
    ("12,5rb", 12500, False, None),
    ("kopi 20.000", 20000, False, None),
    ("999", 999, True, None),
    ("1000", 1000, False, None),
    ("Rp 500 parkir", 500, False, None),
    ("150000000000", 150000000000, False, "range"),
    ("1.234.567", 1234567, False, None),
    ("2 x kopi 15rb", 15000, False, None),
    ("makan 1.500", 1500, False, None),
    ("Rp 50 kopi", 50, False, "range"),
    ("beli 3 100rb", 100000, False, None),
    ("bayar 2 150rb", 150000, False, None),
]


class AmountTest(unittest.TestCase):
    def test_amounts(self):
        for text, jumlah, ambiguous, error in AMOUNTS:
            with self.subTest(text=text):
                r = parse_amount(text)
                self.assertEqual((r["jumlah"], r["ambiguous"], r["error"]), (jumlah, ambiguous, error))

    def test_no_amount(self):
        self.assertIsNone(parse_amount("halo"))
        self.assertIsNone(parse_amount("kopi"))
        self.assertIsNone(parse_amount(""))

    def test_multiple(self):
        r = parse_amount("20000 kopi 15000 roti")
        self.assertEqual((r["jumlah"], r["multiple"]), (20000, True))
        self.assertFalse(parse_amount("beli 2 kopi 30rb")["multiple"])


class TextTest(unittest.TestCase):
    def p(self, text):
        return parse_text(text, TODAY)

    def test_basic(self):
        r = self.p("50000 kopi")
        self.assertEqual((r["jumlah"], r["catatan"], r["jenis"], r["tanggal"], r["kategori"], r["subkategori"], r["error"]),
                         (50000, "Kopi", "keluar", "2026-09-06", "Makanan & Minuman", "Makan di luar", None))

    def test_no_amount(self):
        r = self.p("halo")
        self.assertEqual((r["jumlah"], r["error"], r["catatan"]), (None, "kosong", "Halo"))

    def test_range(self):
        self.assertEqual(self.p("5 kopi")["error"], "range")
        self.assertEqual(self.p("5 kopi")["jumlah"], 5)

    def test_ambiguous(self):
        r = self.p("50 kopi")
        self.assertEqual((r["jumlah"], r["ambiguous"], r["catatan"]), (50, True, "Kopi"))

    def test_jenis_and_masuk_categories(self):
        r = self.p("gaji 7.500.000")
        self.assertEqual((r["jenis"], r["kategori"], r["catatan"]), ("masuk", "Gaji", "Gaji"))
        r = self.p("7,5jt bonus")
        self.assertEqual((r["jenis"], r["kategori"], r["subkategori"]), ("masuk", "Bonus", "Umum"))
        r = self.p("+200k refund")
        self.assertEqual((r["jenis"], r["kategori"], r["catatan"]), ("masuk", "Lainnya", "Refund"))
        r = self.p("dividen 250rb")
        self.assertEqual((r["jenis"], r["kategori"]), ("masuk", "Investasi"))
        r = self.p("masuk 1jt")
        self.assertEqual((r["jenis"], r["kategori"], r["catatan"]), ("masuk", "Lainnya", ""))
        r = self.p("pemasukan 1jt")
        self.assertEqual((r["jenis"], r["kategori"], r["catatan"]), ("masuk", "Lainnya", ""))
        self.assertEqual(self.p("31/12/2025 thr 5jt")["kategori"], "Bonus")
        self.assertEqual(self.p("kopi +20rb")["jenis"], "keluar")

    def test_dates(self):
        r = self.p("kemarin 35000 nasi padang")
        self.assertEqual((r["tanggal"], r["catatan"], r["subkategori"]), ("2026-09-05", "Nasi padang", "Makan di luar"))
        r = self.p("3/9 pulsa 50k")
        self.assertEqual((r["tanggal"], r["catatan"], r["subkategori"]), ("2026-09-03", "Pulsa", "Pulsa"))
        self.assertEqual(self.p("31/12/2025 thr 5jt")["tanggal"], "2025-12-31")
        self.assertEqual(self.p("31-12-25 thr 5jt")["tanggal"], "2025-12-31")
        self.assertEqual(self.p("7/9 kopi 20rb")["tanggal"], "2026-09-07")  # today+1 accepted
        self.assertEqual(self.p("10/9 kopi 20rb")["tanggal"], "2026-09-06")  # future → today
        self.assertEqual(self.p("kopi 20rb")["tanggal"], "2026-09-06")

    def test_catatan(self):
        self.assertEqual(self.p("beli 2 kopi 30rb")["catatan"], "Beli 2 kopi")
        self.assertEqual(self.p("beli 3 100rb")["catatan"], "Beli 3")
        self.assertEqual(self.p("12.500,00")["catatan"], "")
        self.assertEqual(self.p("Rp 12,500 parkir")["catatan"], "Parkir")
        self.assertEqual(self.p("gojek ke kantor 25rb")["catatan"], "Gojek ke kantor")
        self.assertEqual(self.p("kopi - 20rb")["catatan"], "Kopi")
        self.assertEqual(self.p("   makan   siang   25rb  ")["catatan"], "Makan siang")
        self.assertEqual(len(self.p("x" * 100 + " 20rb")["catatan"]), 80)

    def test_keluar_categories(self):
        cases = [("bensin 100rb", "Transportasi", "BBM"), ("Rp 12,500 parkir", "Transportasi", "Parkir"),
                 ("indomaret 87500", "Makanan & Minuman", "Groceries"), ("gojek ke kantor 25rb", "Transportasi", "Ojek-Taxi"),
                 ("token listrik 100rb", "Tagihan", "Listrik"), ("wifi 300rb", "Tagihan", "Internet"),
                 ("netflix 54000", "Hiburan", "Umum"), ("obat apotek 45rb", "Kesehatan", "Umum"),
                 ("beli baju 150rb", "Belanja", "Pakaian"), ("charger hp 80rb", "Belanja", "Elektronik"),
                 ("galon 20rb", "Rumah Tangga", "Umum"), ("bayar spp 500rb", "Pendidikan", "Umum"),
                 ("nasi padang 35000", "Makanan & Minuman", "Makan di luar"), ("botol 50rb", None, None),
                 ("transfer 50rb", None, None), ("kertas 10rb", None, None),
                 ("kopinya 20rb", "Makanan & Minuman", "Makan di luar"), ("bensinnya 100rb", "Transportasi", "BBM"),
                 ("beli makanan 50rb", "Makanan & Minuman", "Makan di luar"), ("pulsanya 50rb", "Tagihan", "Pulsa"),
                 ("parkirnya 5rb", "Transportasi", "Parkir"), ("obatnya 30rb", "Kesehatan", "Umum"),
                 ("gojekku 20rb", "Transportasi", "Ojek-Taxi")]
        for text, k, s in cases:
            with self.subTest(text=text):
                r = self.p(text)
                self.assertEqual((r["kategori"], r["subkategori"]), (k, s))

    def test_guess_helpers(self):
        self.assertEqual(guess_jenis("+ 200rb"), "masuk")
        self.assertEqual(guess_jenis("kopi 20rb"), "keluar")
        self.assertEqual(guess_kategori("kfc"), ("Makanan & Minuman", "Makan di luar"))
        self.assertEqual(guess_kategori("apa saja", "masuk"), ("Lainnya", "Umum"))


class ReceiptTest(unittest.TestCase):
    def test_fixtures(self):
        files = sorted(FIX.glob("*.json"))
        self.assertGreaterEqual(len(files), 6)
        for j in files:
            exp = json.loads(j.read_text(encoding="utf-8"))
            lines = j.with_suffix(".txt").read_text(encoding="utf-8").splitlines()
            got = parse_receipt(lines, date.fromisoformat(exp.pop("today")))
            with self.subTest(fixture=j.stem):
                for k, v in exp.items():
                    self.assertEqual(got["catatan" if k == "merchant" else k], v, k)

    def test_fallback_skips_hotline_and_receipt_number(self):
        lines = (FIX / "02.txt").read_text(encoding="utf-8").splitlines()
        lines = ["T0TAL 82.300" if l == "TOTAL 82.300" else l for l in lines]
        self.assertIn("Layanan Konsumen 1500959", lines)
        r = parse_receipt(lines, TODAY)
        self.assertEqual((r["jumlah"], r["confidence"]), (82300, "low"))
        lines = (FIX / "01.txt").read_text(encoding="utf-8").splitlines()
        lines = ["T0TAL : 87.500" if l == "TOTAL : 87.500" else l for l in lines]
        self.assertNotEqual(parse_receipt(lines, TODAY)["jumlah"], 1234567)

    def test_empty(self):
        r = parse_receipt(["", "   "], TODAY)
        self.assertEqual((r["jumlah"], r["confidence"], r["tanggal"], r["catatan"]), (None, "low", "2026-09-06", "Struk"))

    def test_split_column(self):
        r = parse_receipt(["TOKO MAJU", "TOTAL", "45.000", "TUNAI", "50.000"], TODAY)
        self.assertEqual((r["jumlah"], r["confidence"]), (45000, "high"))

    def test_no_space_after_colon(self):
        r = parse_receipt(["TOKO MAJU", "ITEM A 10.000", "TOTAL:87.500", "TUNAI:100.000"], TODAY)
        self.assertEqual((r["jumlah"], r["confidence"]), (87500, "high"))

    def test_old_date_ignored(self):
        r = parse_receipt(["TOKO MAJU", "01/01/2020", "TOTAL 45.000"], TODAY)
        self.assertEqual((r["tanggal"], r["waktu"]), ("2026-09-06", ""))

    def test_time(self):
        self.assertEqual(parse_receipt(["06/09/2026 19.42", "TOTAL 45.000"], TODAY)["waktu"], "19:42")
        self.assertEqual(parse_receipt(["06/09/2026", "19:42", "TOTAL 45.000"], TODAY)["waktu"], "19:42")
        self.assertEqual(parse_receipt(["06/09/2026", "TOTAL 12.50"], TODAY)["waktu"], "")


if __name__ == "__main__":
    unittest.main()
