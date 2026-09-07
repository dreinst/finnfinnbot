"""Owner receipt OCR in a spawn child; rapidocr/onnxruntime/PIL may be imported only inside _child."""
import math
import multiprocessing
import threading

LOCK = threading.Lock()  # one child at a time; bot may peek LOCK.locked() before spawning a worker
DEADLINE = 30
PARAMS = {"Det.limit_side_len": 1280, "Det.limit_type": "max", "Global.text_score": 0.5, "Global.log_level": "warning",
          "EngineConfig.onnxruntime.intra_op_num_threads": 1, "EngineConfig.onnxruntime.inter_op_num_threads": 1}


class Busy(Exception):
    """Another receipt is being read right now."""


def run(img_bytes):
    """Image bytes → OCR lines from a spawn child; raises Busy, TimeoutError (killed after DEADLINE s), ValueError (not an image / > 25 MP) or RuntimeError."""
    if not LOCK.acquire(blocking=False):
        raise Busy
    try:
        ctx = multiprocessing.get_context("spawn")
        r, w = ctx.Pipe(duplex=False)
        with r, w:  # both ends closed even when start() fails mid-way
            p = ctx.Process(target=_child, args=(w, img_bytes), daemon=True)
            p.start()
            w.close()  # right away, so a dead child shows as EOF instead of a 30 s wait
            res = None
            ok = r.poll(DEADLINE)  # read before join: a child blocked on a full pipe could never exit
            if ok:
                try:
                    res = r.recv()
                except EOFError:
                    pass
                p.join(5)
        if p.is_alive():
            p.kill()
            p.join()
        if not ok:
            raise TimeoutError("OCR lebih dari %d detik" % DEADLINE)
        if res is None:
            raise RuntimeError("proses OCR berhenti (kode %s)" % p.exitcode)
        if isinstance(res, Exception):
            raise res
        return res
    finally:
        LOCK.release()


def _lines(boxes, txts):
    """Token boxes (4 corners, top-left first) + texts → lines top→bottom, tokens left→right; the median tilt of the wide boxes is undone first, then a new line starts when y-centre drifts more than half a token height."""
    angles = sorted(math.atan2(b[1][1] - b[0][1], b[1][0] - b[0][0]) for b in boxes
                    if b[1][0] - b[0][0] > 2 * abs(b[3][1] - b[0][1]))
    a = angles[len(angles) // 2] if angles else 0.0
    cos, sin = math.cos(a), math.sin(a)
    toks = []
    for box, txt in zip(boxes, txts):
        xs = [float(p[0]) * cos + float(p[1]) * sin for p in box]
        ys = [float(p[1]) * cos - float(p[0]) * sin for p in box]
        toks.append(((min(ys) + max(ys)) / 2, min(xs), max(ys) - min(ys), txt))
    toks.sort()
    out, cur, y0 = [], [], 0.0
    for y, x, h, t in toks:
        if cur and y - y0 > h / 2:
            out.append(cur)
            cur = []
        if not cur:
            y0 = y
        cur.append((x, t))
    if cur:
        out.append(cur)
    return [" ".join(t for _, t in sorted(c)) for c in out]


def _child(conn, img_bytes):
    """Child entry: EXIF rotate → reject > 25 MP → ≤ 1600 px → RapidOCR(use_cls=False) → lines (or an exception) over `conn`."""
    try:
        from io import BytesIO
        from PIL import Image, ImageOps
        try:
            img = Image.open(BytesIO(img_bytes))
        except Exception:
            raise ValueError("bukan gambar")
        if img.width * img.height > 25_000_000:
            raise ValueError("gambar terlalu besar")
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((1600, 1600))
        from rapidocr import RapidOCR
        out = RapidOCR(params=PARAMS)(img, use_cls=False)
        conn.send(_lines(out.boxes, out.txts) if out.txts else [])
    except Exception as e:
        conn.send(e if isinstance(e, ValueError) else RuntimeError((str(e) or type(e).__name__)[:200]))
    finally:
        conn.close()
