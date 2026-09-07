import re
from datetime import date, timedelta

# ---------- text (chat) ----------

AMOUNT_RE = re.compile(  # a space-grouped number followed by a suffix is "count price" ("beli 3 100rb"), not one number
    r"(\brp\.?\s*|\bidr\s*)?([+-]?)(\d{1,3}(?:[.,]\d{3})+|\d{1,3}(?:\s\d{3})+(?!\s*(?:rb|ribu|k|jt|juta|m)\b)|\d+)"
    r"(?:[.,](\d{1,2}))?\s*(rb|ribu|k|jt|juta|m)?\b", re.I)
MULT = {"rb": 1000, "ribu": 1000, "k": 1000, "jt": 1_000_000, "juta": 1_000_000, "m": 1_000_000}
DATE_RE = re.compile(r"(?<![\d/.\-])(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?![\d/.\-])")
TYPE_RE = re.compile(r"\b(pemasukan|pengeluaran|masuk|keluar)\b", re.I)
MASUK_RE = re.compile(
    r"\b(gaji|gajian|bonus|thr|masuk|pemasukan|terima|dapat|dividen|bunga|cashback|refund|jual|untung|honor|fee|komisi|hadiah)\b", re.I)

# prefix match only: "kopinya"/"bensinnya" still classify, "botol"/"kertas" do not hit tol/tas
KELUAR_MAP = [(re.compile(r"\b(?:%s)" % p, re.I), k, s) for p, k, s in (
    (r"kopi|makan|nasi|warung|warteg|resto|gofood|grabfood|shopeefood|mie|bakso|sate|ayam|snack|jajan|cafe|kfc|mcd|"
     r"starbucks|kopi kenangan|janji jiwa|mixue|hokben", "Makanan & Minuman", "Makan di luar"),
    (r"indomaret|alfamart|alfamidi|supermarket|superindo|hypermart|transmart|sayur|buah|beras|telur|belanja bulanan|pasar",
     "Makanan & Minuman", "Groceries"),
    (r"bensin|bbm|pertalite|pertamax|solar|shell|pertamina|spbu", "Transportasi", "BBM"),
    (r"gojek|grab|ojek|taxi|taksi|bluebird|maxim|angkot|busway|krl|mrt|kereta|bus|tol", "Transportasi", "Ojek-Taxi"),
    (r"parkir", "Transportasi", "Parkir"),
    (r"listrik|pln|token", "Tagihan", "Listrik"),
    (r"wifi|internet|indihome|biznet|first media|myrepublic", "Tagihan", "Internet"),
    (r"pulsa|kuota|paket data|telkomsel|xl|indosat|tri|by\.u", "Tagihan", "Pulsa"),
    (r"baju|celana|sepatu|kaos|jaket|tas|uniqlo|h&m", "Belanja", "Pakaian"),
    (r"hp|laptop|charger|headset|elektronik|kabel|mouse", "Belanja", "Elektronik"),
    (r"dokter|obat|apotek|klinik|rumah sakit|rs|vitamin|bpjs|kimia farma|guardian", "Kesehatan", "Umum"),
    (r"nonton|bioskop|netflix|spotify|game|steam|konser|wisata|tiket|hiburan", "Hiburan", "Umum"),
    (r"sekolah|kursus|buku|kuliah|spp|les|udemy|gramedia", "Pendidikan", "Umum"),
    (r"sabun|deterjen|gas|lpg|galon|tisu|perabot|pdam|kebersihan", "Rumah Tangga", "Umum"),
)]
MASUK_MAP = [(re.compile(r"\b(?:%s)" % p, re.I), k, "Umum") for p, k in (
    (r"gaji|gajian|honor|fee|komisi", "Gaji"),
    (r"bonus|thr|hadiah", "Bonus"),
    (r"dividen|bunga|saham|reksadana|crypto", "Investasi"),
)]


def _value(num, dec, suf):
    n = int(re.sub(r"\D", "", num))
    mult = MULT.get((suf or "").lower(), 1)
    if dec and mult > 1:
        return n * mult + int(dec) * mult // 10 ** len(dec)
    return n * mult


def parse_amount(text):
    """First amount token → {jumlah, ambiguous, multiple, error, span}; None when no number at all.

    A bare number < 1000 (no rp/suffix/separator) only counts when nothing stronger exists → ambiguous.
    """
    strong, bare = [], []
    for m in AMOUNT_RE.finditer(text):
        rp, _sign, num, dec, suf = m.groups()
        val = _value(num, dec, suf)
        (strong if rp or suf or not num.isdigit() or val >= 1000 else bare).append((val, m.span()))
    if strong:
        val, span = strong[0]
        return {"jumlah": val, "ambiguous": False, "multiple": len(strong) > 1,
                "error": None if 100 <= val <= 100_000_000_000 else "range", "span": span}
    if bare:
        val, span = bare[0]
        return {"jumlah": val, "ambiguous": val >= 10, "multiple": False, "error": None if val >= 10 else "range", "span": span}
    return None


def guess_jenis(text):
    return "masuk" if re.search(r"^\s*\+\s*\d", text) or MASUK_RE.search(text) else "keluar"


def guess_kategori(text, jenis="keluar"):
    """→ (kategori, subkategori); keluar without a hit → (None, None), masuk → Lainnya."""
    for rx, k, s in (MASUK_MAP if jenis == "masuk" else KELUAR_MAP):
        if rx.search(text):
            return k, s
    return ("Lainnya", "Umum") if jenis == "masuk" else (None, None)


def _blank(s, spans):
    for a, b in spans:
        s = s[:a] + " " * (b - a) + s[b:]
    return s


def _mk_date(d, m, y, today):
    y = today.year if y is None else (2000 + y if y < 100 else y)
    try:
        dt = date(y, m, d)
    except ValueError:
        return None
    return dt if dt <= today + timedelta(1) else today


def parse_text(text, today):
    """Chat line → {jumlah, ambiguous, multiple, error ('kosong'|'range'|None), catatan, jenis, tanggal, kategori, subkategori}."""
    s = " ".join(text.split())
    cuts, tanggal = [], today
    m = re.search(r"\bkemarin\b", s, re.I)
    if m:
        tanggal = today - timedelta(1)
        cuts.append(m.span())
    for m in DATE_RE.finditer(s):
        d = _mk_date(int(m[1]), int(m[2]), int(m[3]) if m[3] else None, today)
        if d:
            tanggal = d
            cuts.append(m.span())
            break
    rest = _blank(s, cuts)
    amt = parse_amount(rest) or {"jumlah": None, "ambiguous": False, "multiple": False, "error": "kosong", "span": None}
    if amt["span"]:
        cuts.append(amt["span"])
    jenis = guess_jenis(rest)
    cuts += [m.span() for m in TYPE_RE.finditer(rest)]
    rest = _blank(s, cuts)
    kategori, sub = guess_kategori(rest, jenis)
    catatan = " ".join(rest.split()).strip(" +-–—,.:;|")[:80].rstrip()
    return {"jumlah": amt["jumlah"], "ambiguous": amt["ambiguous"], "multiple": amt["multiple"], "error": amt["error"],
            "catatan": catatan[:1].upper() + catatan[1:], "jenis": jenis, "tanggal": tanggal.isoformat(),
            "kategori": kategori, "subkategori": sub}


# ---------- receipt (OCR lines) ----------

REPAIR = str.maketrans("OolI|SBZ", "00111582")
MONEY = re.compile(r"(?<![\d/.])(?:rp\.?\s*)?(?!0)(\d{1,3}(?:[.,]\d{3})+|\d{4,})(?:[.,]\d{2})?(?:,-)?(?!\d)", re.I)
IGNORE = re.compile(r"qty|pcs|[x×]\s?\d|\d\s?[x×](?!\w)|@|no\.|telp|tel\b|npwp|kasir|trx|ref|struk|nota|layanan|\d{2}:\d{2}", re.I)  # OCR reads "2 x" as "2 ×"
HI = re.compile(r"grand\s*total|total\s*(bayar|pembayaran|belanja|tagihan|akhir|pesanan|harga)|jumlah\s*(bayar|tagihan)|amount\s*due|net\s*total", re.I)
TOTAL = re.compile(r"\btotal\b|\bjumlah\b", re.I)
SUB = re.compile(r"sub\s*total|subtotal|total\s*(item|qty|disc|diskon|promo|hemat)", re.I)
KEMBALI = re.compile(r"kembali|kembalian|change", re.I)
BAYAR = re.compile(r"tunai|cash|debit|kredit|kartu|qris|dibayar", re.I)
PAJAK = re.compile(r"ppn|pajak|tax|dpp|disc|diskon|potongan|voucher|poin", re.I)
FALLBACK_SKIP = re.compile(r"kembali|change|tunai|cash", re.I)
R_DATE = re.compile(r"(?<!\d)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})(?!\d)")
R_DATE_NAME = re.compile(r"(?<!\d)(\d{1,2})\s*(jan|feb|mar|apr|mei|may|jun|jul|agu|aug|sep|okt|oct|nov|des|dec)[a-z]*\.?\s*(\d{2,4})(?!\d)", re.I)
R_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
R_TIME = re.compile(r"(?<!\d)(\d{1,2})[:.](\d{2})(?!\d)")
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "mei": 5, "may": 5, "jun": 6, "jul": 7, "agu": 8, "aug": 8,
          "sep": 9, "okt": 10, "oct": 10, "nov": 11, "des": 12, "dec": 12}
BRANDS = [(re.compile(r"\b(?:%s)" % p, re.I), n) for p, n in (
    ("indomaret", "Indomaret"), ("alfamart", "Alfamart"), ("alfamidi", "Alfamidi"), ("superindo", "Superindo"),
    ("hypermart", "Hypermart"), ("transmart", "Transmart"), (r"kfc\b", "KFC"), (r"mcd\b|mcdonald", "McD"),
    ("starbucks", "Starbucks"), ("kopi kenangan", "Kopi Kenangan"), ("janji jiwa", "Janji Jiwa"), ("mixue", "Mixue"),
    ("hokben", "HokBen"), ("gofood|gojek", "GoFood"), ("grabfood", "GrabFood"), (r"grab\b", "Grab"), ("shopee", "Shopee"),
    ("tokopedia", "Tokopedia"), ("pertamina", "Pertamina"), (r"shell\b", "Shell"), (r"pln\b", "PLN"),
    ("indihome", "IndiHome"), ("apotek", "Apotek"), ("kimia farma", "Kimia Farma"), ("guardian", "Guardian"),
    ("gramedia", "Gramedia"))]
NOT_MERCHANT = re.compile(r"jl\.|jalan|telp|tel\.|npwp|no\.|struk|receipt|nota|faktur|kasir|tanggal|date", re.I)


def _repair(line):
    def fix(m):
        t = m.group(0)
        return t.translate(REPAIR) if re.search(r"\d", t) and re.search(r"[OolI|SBZ]", t) else t
    line = re.sub(r"[0-9OolI|SBZ.,]{3,}", fix, line)
    line = re.sub(r"(\d)\s*([.,])\s*(\d{3})(?!\d)", r"\1\2\3", line)
    return re.sub(r"\b[Rr][Pp]\.?\s*", "Rp ", line)


def _amounts(line):
    if IGNORE.search(line) and not (HI.search(line) or TOTAL.search(line)):
        return []
    vals = [int(re.sub(r"\D", "", m.group(1))) for m in MONEY.finditer(line)]
    return [v for v in vals if 100 <= v <= 1_000_000_000]


def _score(line):
    return (3 * bool(HI.search(line)) + 2 * bool(TOTAL.search(line)) - 3 * bool(SUB.search(line))
            - 5 * bool(KEMBALI.search(line)) - 3 * bool(BAYAR.search(line)) - 3 * bool(PAJAK.search(line)))


def _find_date(lines, today):
    lo, hi = today - timedelta(400), today + timedelta(1)
    for i, line in enumerate(lines):
        for rx in (R_DATE, R_DATE_NAME, R_ISO):
            m = rx.search(line)
            if not m:
                continue
            a, b, c = m.groups()
            if rx is R_ISO:
                y, mo, d = int(a), int(b), int(c)
            elif rx is R_DATE_NAME:
                d, mo, y = int(a), MONTHS[b.lower()[:3]], int(c)
            else:
                d, mo, y = int(a), int(b), int(c)
                if mo > 12 and d <= 12:
                    d, mo = mo, d
            y = 2000 + y if y < 100 else y
            try:
                dt = date(y, mo, d)
            except ValueError:
                continue
            if not lo <= dt <= hi:
                continue
            for j in (i, i + 1, i - 1):
                if 0 <= j < len(lines):
                    t = R_TIME.search(_blank(lines[j], [m.span()]) if j == i else lines[j])
                    if t and (j == i or ":" in t[0]) and int(t[1]) < 24 and int(t[2]) < 60:  # "12.50" off the date line is a price
                        return dt, f"{int(t[1]):02d}:{t[2]}"
            return dt, ""
    return today, ""


def _merchant(lines):
    for line in lines:
        for rx, name in BRANDS:
            if rx.search(line):
                return name
    for line in lines[:4]:
        if len(re.findall(r"[A-Za-z]", line)) >= 3 and not NOT_MERCHANT.search(line):
            return line.title()[:40]
    return "Struk"


def parse_receipt(lines, today):
    """OCR lines top→bottom → {jumlah, confidence ('high'|'low'), tanggal, waktu, catatan, kategori, subkategori}."""
    lines = [_repair(l.strip()) for l in lines if l.strip()]
    amounts = [_amounts(l) for l in lines]
    best = None
    for i, line in enumerate(lines):
        sc = _score(line)
        if amounts[i]:
            val = amounts[i][-1]
        elif sc > 0 and i + 1 < len(lines) and amounts[i + 1]:
            val = amounts[i + 1][0]
        else:
            continue
        if best is None or sc >= best[0]:
            best = (sc, val)
    if best and best[0] > 0:
        jumlah, confidence = best[1], "high"
    else:
        cands = [v for i in range(int(len(lines) * 0.4), len(lines)) if not FALLBACK_SKIP.search(lines[i]) for v in amounts[i]]
        jumlah, confidence = (max(cands), "low") if cands else (None, "low")
    tanggal, waktu = _find_date(lines, today)
    merchant = _merchant(lines)
    kategori, sub = guess_kategori(merchant)
    if not kategori:
        kategori, sub = guess_kategori(" ".join(lines))
    return {"jumlah": jumlah, "confidence": confidence, "tanggal": tanggal.isoformat(), "waktu": waktu,
            "catatan": merchant, "kategori": kategori, "subkategori": sub}
