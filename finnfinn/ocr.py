"""Owner receipt OCR in a spawn child; rapidocr/onnxruntime may be imported only inside _child."""


def run(img_bytes):
    """Image bytes → ordered text lines via a child process (join(30) + kill deadline, one at a time)."""
    raise NotImplementedError


def _child(conn, img_bytes):
    """Child entry: EXIF rotate → ≤1600 px → RapidOCR(use_cls=False) → send the lines over `conn`."""
    raise NotImplementedError
