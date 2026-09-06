import os
import sqlite3
import threading

_local = threading.local()
_path = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
  id          INTEGER PRIMARY KEY,
  jenis       TEXT NOT NULL CHECK (jenis IN ('masuk','keluar')),
  kategori    TEXT NOT NULL,
  subkategori TEXT NOT NULL,
  ikon        TEXT NOT NULL DEFAULT 'category',
  urutan      INTEGER NOT NULL DEFAULT 0,
  aktif       INTEGER NOT NULL DEFAULT 1,
  UNIQUE (jenis, kategori, subkategori)
);
CREATE TABLE IF NOT EXISTS transactions (
  id          INTEGER PRIMARY KEY,
  jenis       TEXT NOT NULL CHECK (jenis IN ('masuk','keluar')),
  jumlah      INTEGER NOT NULL CHECK (jumlah > 0),
  kategori    TEXT NOT NULL,
  subkategori TEXT NOT NULL,
  catatan     TEXT NOT NULL DEFAULT '',
  tanggal     TEXT NOT NULL,
  waktu       TEXT NOT NULL DEFAULT '',
  sumber      TEXT NOT NULL DEFAULT 'teks' CHECK (sumber IN ('teks','struk','app')),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  updated_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_tx_tanggal       ON transactions (tanggal, waktu);
CREATE INDEX IF NOT EXISTS idx_tx_jenis_tanggal ON transactions (jenis, tanggal);
CREATE TABLE IF NOT EXISTS guests (
  tg_id       INTEGER PRIMARY KEY,
  remind      INTEGER NOT NULL DEFAULT 0,
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE TABLE IF NOT EXISTS sent_reports (
  kind        TEXT NOT NULL,
  period_key  TEXT NOT NULL,
  sent_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  PRIMARY KEY (kind, period_key)
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""

SEED = [
    ("masuk", "Gaji", "Umum", "payments"),
    ("masuk", "Bonus", "Umum", "redeem"),
    ("masuk", "Investasi", "Umum", "trending_up"),
    ("masuk", "Lainnya", "Umum", "add_circle"),
    ("keluar", "Makanan & Minuman", "Makan di luar", "restaurant"),
    ("keluar", "Makanan & Minuman", "Groceries", "shopping_cart"),
    ("keluar", "Transportasi", "BBM", "local_gas_station"),
    ("keluar", "Transportasi", "Ojek-Taxi", "two_wheeler"),
    ("keluar", "Transportasi", "Parkir", "local_parking"),
    ("keluar", "Tagihan", "Listrik", "bolt"),
    ("keluar", "Tagihan", "Internet", "wifi"),
    ("keluar", "Tagihan", "Pulsa", "smartphone"),
    ("keluar", "Belanja", "Pakaian", "checkroom"),
    ("keluar", "Belanja", "Elektronik", "devices"),
    ("keluar", "Kesehatan", "Umum", "medical_services"),
    ("keluar", "Hiburan", "Umum", "movie"),
    ("keluar", "Pendidikan", "Umum", "school"),
    ("keluar", "Rumah Tangga", "Umum", "home"),
    ("keluar", "Lainnya", "Umum", "more_horiz"),
]

TX_COLS = ("jenis", "jumlah", "kategori", "subkategori", "catatan", "tanggal", "waktu", "sumber")


def connect():
    """Per-thread autocommit connection with the WAL pragmas applied."""
    con = getattr(_local, "con", None)
    if con is None:
        con = sqlite3.connect(_path, timeout=5, isolation_level=None)
        con.row_factory = sqlite3.Row
        for p in ("journal_mode=WAL", "busy_timeout=5000", "synchronous=NORMAL", "foreign_keys=ON"):
            con.execute("PRAGMA " + p)
        _local.con = con
    return con


def close():
    con = getattr(_local, "con", None)
    if con:
        con.close()
        _local.con = None


def init(path):
    global _path
    close()
    _path = path
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    con = connect()
    con.executescript(SCHEMA)
    seed()
    con.execute("INSERT OR IGNORE INTO meta VALUES ('schema_version', '1')")


def seed():
    """Insert the default categories; no-op when the table already has rows."""
    con = connect()
    if con.execute("SELECT 1 FROM categories LIMIT 1").fetchone():
        return
    con.executemany("INSERT INTO categories (jenis, kategori, subkategori, ikon, urutan) VALUES (?,?,?,?,?)",
                    [(j, k, s, i, n) for n, (j, k, s, i) in enumerate(SEED)])


def add_tx(tx):
    cur = connect().execute(
        "INSERT INTO transactions (jenis,jumlah,kategori,subkategori,catatan,tanggal,waktu,sumber) VALUES (?,?,?,?,?,?,?,?)",
        (tx["jenis"], tx["jumlah"], tx["kategori"], tx["subkategori"], tx.get("catatan", ""),
         tx["tanggal"], tx.get("waktu", ""), tx.get("sumber", "teks")))
    return get_tx(cur.lastrowid)


def get_tx(tx_id):
    row = connect().execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
    return dict(row) if row else None


def update_tx(tx_id, patch):
    cols = [c for c in TX_COLS if c in patch]
    if cols:
        sets = ", ".join(c + "=?" for c in cols)
        connect().execute(
            f"UPDATE transactions SET {sets}, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
            [patch[c] for c in cols] + [tx_id])
    return get_tx(tx_id)


def delete_tx(tx_id):
    return connect().execute("DELETE FROM transactions WHERE id=?", (tx_id,)).rowcount == 1


def list_tx(frm, to):
    rows = connect().execute(
        "SELECT * FROM transactions WHERE tanggal BETWEEN ? AND ? ORDER BY tanggal DESC, waktu DESC, id DESC", (frm, to))
    return [dict(r) for r in rows]


def summary(frm, to):
    """→ (per (jenis,kategori,subkategori) rows, per (tanggal,jenis) rows) for the inclusive date range."""
    con = connect()
    by_cat = con.execute(
        "SELECT jenis, kategori, subkategori, SUM(jumlah) AS total, COUNT(*) AS n FROM transactions "
        "WHERE tanggal BETWEEN ? AND ? GROUP BY 1,2,3 ORDER BY total DESC", (frm, to))
    by_day = con.execute(
        "SELECT tanggal, jenis, SUM(jumlah) AS total FROM transactions "
        "WHERE tanggal BETWEEN ? AND ? GROUP BY 1,2 ORDER BY 1", (frm, to))
    return [dict(r) for r in by_cat], [dict(r) for r in by_day]


def categories():
    return [dict(r) for r in connect().execute("SELECT * FROM categories ORDER BY aktif DESC, jenis, urutan, id")]


def save_categories(items):
    """Full replace; a renamed leaf cascades to its transactions. Raises IntegrityError on duplicates, ValueError when empty."""
    if not items:
        raise ValueError("kategori kosong")
    con = connect()
    old = {c["id"]: c for c in categories()}
    con.execute("BEGIN")
    try:
        keep = []
        for n, c in enumerate(items):
            vals = (c["kategori"], c["subkategori"], c.get("ikon", "category"), c.get("urutan", n), int(c.get("aktif", 1)))
            o = old.get(c.get("id"))
            if o:
                if (o["kategori"], o["subkategori"]) != vals[:2]:
                    con.execute("UPDATE transactions SET kategori=?, subkategori=? WHERE jenis=? AND kategori=? AND subkategori=?",
                                vals[:2] + (o["jenis"], o["kategori"], o["subkategori"]))
                con.execute("UPDATE categories SET kategori=?, subkategori=?, ikon=?, urutan=?, aktif=? WHERE id=?", vals + (o["id"],))
                keep.append(o["id"])
            else:
                keep.append(con.execute("INSERT INTO categories (jenis,kategori,subkategori,ikon,urutan,aktif) VALUES (?,?,?,?,?,?)",
                                        (c["jenis"],) + vals).lastrowid)
        con.execute(f"DELETE FROM categories WHERE id NOT IN ({','.join('?' * len(keep))})", keep)
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise


def guest_upsert(tg_id):
    connect().execute("INSERT OR IGNORE INTO guests (tg_id) VALUES (?)", (tg_id,))


def guest_set_remind(tg_id, on):
    """→ rowcount (0 when the guest never opened the chat); never inserts."""
    return connect().execute("UPDATE guests SET remind=? WHERE tg_id=?", (1 if on else 0, tg_id)).rowcount


def guest_delete(tg_id):
    connect().execute("DELETE FROM guests WHERE tg_id=?", (tg_id,))


def guests_to_remind():
    return [r[0] for r in connect().execute("SELECT tg_id FROM guests WHERE remind=1 ORDER BY tg_id")]


def claim(kind, key):
    return connect().execute("INSERT OR IGNORE INTO sent_reports (kind, period_key) VALUES (?,?)", (kind, key)).rowcount == 1


def unclaim(kind, key):
    connect().execute("DELETE FROM sent_reports WHERE kind=? AND period_key=?", (kind, key))


def meta_get(k, default=None):
    row = connect().execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
    return row[0] if row else default


def meta_set(k, v):
    connect().execute("INSERT OR REPLACE INTO meta (k, v) VALUES (?,?)", (k, v))


def snapshot(dest):
    """VACUUM INTO dest, then quick_check the copy (deleted + RuntimeError on failure)."""
    if os.path.dirname(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.exists(dest):
        os.remove(dest)
    connect().execute("VACUUM INTO ?", (dest,))
    chk = sqlite3.connect(dest)
    try:
        ok = chk.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    finally:
        chk.close()
    if not ok:
        os.remove(dest)
        raise RuntimeError("quick_check gagal: " + dest)
    return dest
