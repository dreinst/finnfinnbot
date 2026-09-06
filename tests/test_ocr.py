"""ocr.py without rapidocr: line grouping, Busy, deadline and child-failure paths (fake spawn children).

FINNFINN_REAL_OCR=1 (inside the Docker image) also runs a real RapidOCR pass on a rendered receipt.
"""
import io
import multiprocessing
import os
import sys
import time
import unittest

from finnfinn import ocr


def _sleep_child(conn, img_bytes):
    time.sleep(60)


def _error_child(conn, img_bytes):
    conn.send(RuntimeError("boom"))


def _value_child(conn, img_bytes):
    conn.send(ValueError("bukan gambar"))


def _crash_child(conn, img_bytes):
    os._exit(3)


def _box(x0, y0, w, h, tilt=0.0):
    return [[x0, y0], [x0 + w, y0 + tilt], [x0 + w, y0 + h + tilt], [x0, y0 + h]]


class LinesTest(unittest.TestCase):
    def test_order_and_grouping(self):
        boxes = [_box(500, 42, 100, 20), _box(0, 0, 100, 20), _box(500, 6, 100, 20), _box(0, 40, 100, 20)]
        self.assertEqual(ocr._lines(boxes, ["100.000", "TOTAL", "87.500", "TUNAI"]), ["TOTAL 87.500", "TUNAI 100.000"])

    def test_tilted_columns_stay_on_one_line(self):
        t = 3.5  # ≈2°: the right column sits 17.5 px lower, more than half a 20 px token
        boxes = [_box(0, 0, 100, 20, t), _box(500, 17.5, 100, 20, t), _box(0, 40, 100, 20, t), _box(500, 57.5, 100, 20, t)]
        self.assertEqual(ocr._lines(boxes, ["TOTAL", "87.500", "TUNAI", "100.000"]), ["TOTAL 87.500", "TUNAI 100.000"])

    def test_empty(self):
        self.assertEqual(ocr._lines([], []), [])


class RunTest(unittest.TestCase):
    def setUp(self):
        self.child, self.deadline = ocr._child, ocr.DEADLINE

    def tearDown(self):
        ocr._child, ocr.DEADLINE = self.child, self.deadline
        self.assertFalse(ocr.LOCK.locked())
        self.assertEqual(multiprocessing.active_children(), [])

    def test_busy(self):
        ocr.LOCK.acquire()
        try:
            with self.assertRaises(ocr.Busy):
                ocr.run(b"x")
        finally:
            ocr.LOCK.release()

    def test_deadline_kills_child(self):
        ocr._child, ocr.DEADLINE = _sleep_child, 1
        t0 = time.monotonic()
        with self.assertRaises(TimeoutError):
            ocr.run(b"x")
        self.assertLess(time.monotonic() - t0, 5)

    def test_child_errors_propagate(self):
        ocr._child = _error_child
        with self.assertRaisesRegex(RuntimeError, "boom"):
            ocr.run(b"x")
        ocr._child = _value_child
        with self.assertRaisesRegex(ValueError, "bukan gambar"):
            ocr.run(b"x")
        ocr._child = _crash_child
        with self.assertRaisesRegex(RuntimeError, "kode 3"):
            ocr.run(b"x")


@unittest.skipUnless(os.environ.get("FINNFINN_REAL_OCR") == "1", "set FINNFINN_REAL_OCR=1 inside the Docker image")
class RealOcrTest(unittest.TestCase):
    def test_receipt(self):
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (600, 200), "white")
        d, f = ImageDraw.Draw(img), ImageFont.load_default(size=36)
        d.text((30, 30), "TOKO MAJU", font=f, fill="black")
        d.text((30, 110), "TOTAL", font=f, fill="black")
        d.text((380, 110), "45.000", font=f, fill="black")
        buf = io.BytesIO()
        img.save(buf, "JPEG")
        lines = ocr.run(buf.getvalue())
        self.assertEqual(lines, ["TOKO MAJU", "TOTAL 45.000"])
        self.assertFalse({"rapidocr", "onnxruntime", "cv2"} & {m.split(".")[0] for m in sys.modules})

    def test_rejects(self):
        from PIL import Image
        with self.assertRaisesRegex(ValueError, "bukan gambar"):
            ocr.run(b"not an image")
        buf = io.BytesIO()
        Image.new("L", (5100, 5100)).save(buf, "JPEG")
        with self.assertRaisesRegex(ValueError, "terlalu besar"):
            ocr.run(buf.getvalue())


if __name__ == "__main__":
    unittest.main()
