"""Finn Finn tools for Hermes — owner-only (locked in gatekeeper by Telegram id, not role).

Reads/writes the same SQLite file the Finn Finn bot uses. Kept intentionally
separate from the finnfinn/ package (different Python version, different
process) — plain sqlite3, mirroring its schema rather than importing it.
"""
import datetime as dt
import json
import os
import sqlite3
import zoneinfo

DB = os.environ.get("FINNFINN_DB", "/var/lib/docker/volumes/ovs1vlewapmz89nwkxiaismb-finnfinn-data/_data/finnfinn.db")
WIB = zoneinfo.ZoneInfo("Asia/Jakarta")
PERIODE = ("hari_ini", "kemarin", "minggu_ini", "bulan_ini", "bulan_lalu", "tahun_ini")


def _connect():
    con = sqlite3.connect(DB, timeout=5, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000")
    return con


def _range(periode):
    t = dt.datetime.now(WIB).date()
    if periode == "hari_ini":
        return t, t
    if periode == "kemarin":
        y = t - dt.timedelta(1)
        return y, y
    if periode == "minggu_ini":
        return t - dt.timedelta(t.weekday()), t
    if periode == "bulan_ini":
        return t.replace(day=1), t
    if periode == "bulan_lalu":
        akhir_lalu = t.replace(day=1) - dt.timedelta(1)
        return akhir_lalu.replace(day=1), akhir_lalu
    return t.replace(month=1, day=1), t  # tahun_ini (default)


def finnfinn_ringkasan(args, **_):
    a, b = _range(args.get("periode", "minggu_ini"))
    kat = (args.get("kategori") or "").strip()
    con = _connect()
    try:
        q = "SELECT jenis,kategori,subkategori,SUM(jumlah) jumlah,COUNT(*) n FROM transactions WHERE tanggal BETWEEN ? AND ?"
        p = [a.isoformat(), b.isoformat()]
        if kat:
            q += " AND kategori LIKE ?"
            p.append(f"%{kat}%")
        rows = [dict(r) for r in con.execute(q + " GROUP BY 1,2,3 ORDER BY jumlah DESC", p)]
        tx = []
        if args.get("detail"):
            tq = ("SELECT id,tanggal,waktu,jenis,jumlah,kategori,subkategori,catatan FROM transactions "
                  "WHERE tanggal BETWEEN ? AND ?")
            tp = [a.isoformat(), b.isoformat()]
            if kat:
                tq += " AND kategori LIKE ?"
                tp.append(f"%{kat}%")
            tx = [dict(r) for r in con.execute(tq + " ORDER BY tanggal DESC, waktu DESC, id DESC LIMIT 50", tp)]
    finally:
        con.close()
    masuk = sum(r["jumlah"] for r in rows if r["jenis"] == "masuk")
    keluar = sum(r["jumlah"] for r in rows if r["jenis"] == "keluar")
    out = {"periode": [a.isoformat(), b.isoformat()], "masuk": masuk, "keluar": keluar, "sisa": masuk - keluar, "rincian": rows}
    if tx:
        out["transaksi"] = tx
    return json.dumps(out, ensure_ascii=False)


def finnfinn_daftar_transaksi(args, **_):
    kat = (args.get("kategori") or "").strip()
    jenis = args.get("jenis")
    periode = args.get("periode")
    limit = max(1, min(int(args.get("limit") or 20), 200))
    q = "SELECT id,tanggal,waktu,jenis,jumlah,kategori,subkategori,catatan,sumber FROM transactions WHERE 1=1"
    p = []
    if periode in PERIODE:
        a, b = _range(periode)
        q += " AND tanggal BETWEEN ? AND ?"
        p += [a.isoformat(), b.isoformat()]
    if kat:
        q += " AND kategori LIKE ?"
        p.append(f"%{kat}%")
    if jenis in ("masuk", "keluar"):
        q += " AND jenis = ?"
        p.append(jenis)
    con = _connect()
    try:
        rows = [dict(r) for r in con.execute(q + " ORDER BY tanggal DESC, waktu DESC, id DESC LIMIT ?", p + [limit])]
    finally:
        con.close()
    return json.dumps({"n": len(rows), "transaksi": rows}, ensure_ascii=False)


def finnfinn_ubah_kategori(args, **_):
    tx_id = args.get("transaksi_id")
    kategori, sub = (args.get("kategori") or "").strip(), (args.get("subkategori") or "").strip()
    if not isinstance(tx_id, int) or not kategori or not sub:
        return json.dumps({"ok": False, "error": "transaksi_id, kategori, subkategori wajib diisi"})
    con = _connect()
    try:
        tx = con.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        if not tx:
            return json.dumps({"ok": False, "error": "transaksi tidak ditemukan"})
        leaf = con.execute("SELECT 1 FROM categories WHERE jenis=? AND kategori=? AND subkategori=?",
                           (tx["jenis"], kategori, sub)).fetchone()
        if not leaf:
            return json.dumps({"ok": False, "error": f"kategori '{kategori} › {sub}' tidak ada untuk jenis {tx['jenis']}"})
        con.execute("UPDATE transactions SET kategori=?, subkategori=?, updated_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id=?",
                   (kategori, sub, tx_id))
        row = dict(con.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone())
    finally:
        con.close()
    return json.dumps({"ok": True, "transaksi": row}, ensure_ascii=False)


def finnfinn_hapus_transaksi(args, **_):
    tx_id = args.get("transaksi_id")
    if not isinstance(tx_id, int):
        return json.dumps({"ok": False, "error": "transaksi_id wajib diisi"})
    con = _connect()
    try:
        tx = con.execute("SELECT * FROM transactions WHERE id=?", (tx_id,)).fetchone()
        if not tx:
            return json.dumps({"ok": False, "error": "transaksi tidak ditemukan"})
        deleted = dict(tx)
        con.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    finally:
        con.close()
    return json.dumps({"ok": True, "dihapus": deleted}, ensure_ascii=False)


_PERIODE_PROP = {"type": "string", "enum": list(PERIODE)}

RINGKASAN_SCHEMA = {
    "name": "finnfinn_ringkasan",
    "description": ("Ringkasan pemasukan/pengeluaran pribadi Owner dari Finn Finn (rupiah), opsional difilter per "
                     "kategori. Untuk pertanyaan seperti 'berapa pengeluaran minggu ini' atau 'pengeluaran kategori "
                     "makanan bulan ini'. Hanya membaca."),
    "parameters": {"type": "object", "properties": {
        "periode": _PERIODE_PROP,
        "kategori": {"type": "string", "description": "filter nama kategori (opsional, partial match)"},
        "detail": {"type": "boolean", "description": "sertakan sampai 50 transaksi terakhir yang cocok"}}, "required": []}}

DAFTAR_SCHEMA = {
    "name": "finnfinn_daftar_transaksi",
    "description": ("Daftar/index transaksi Finn Finn, bisa difilter kategori/jenis/periode. Untuk 'tampilkan "
                     "transaksi kategori X', 'cari transaksi Y minggu ini'. Hanya membaca."),
    "parameters": {"type": "object", "properties": {
        "kategori": {"type": "string", "description": "filter nama kategori (partial match, opsional)"},
        "jenis": {"type": "string", "enum": ["masuk", "keluar"]},
        "periode": {**_PERIODE_PROP, "description": "opsional, kosongkan untuk semua waktu"},
        "limit": {"type": "integer", "description": "maks jumlah baris, default 20, maks 200"}}, "required": []}}

UBAH_SCHEMA = {
    "name": "finnfinn_ubah_kategori",
    "description": ("Ubah kategori/subkategori satu transaksi Finn Finn yang salah catat. Perlu transaksi_id "
                     "(dari finnfinn_daftar_transaksi atau finnfinn_ringkasan dengan detail=true)."),
    "parameters": {"type": "object", "properties": {
        "transaksi_id": {"type": "integer"},
        "kategori": {"type": "string"},
        "subkategori": {"type": "string"}}, "required": ["transaksi_id", "kategori", "subkategori"]}}

HAPUS_SCHEMA = {
    "name": "finnfinn_hapus_transaksi",
    "description": "Hapus satu transaksi Finn Finn yang salah catat/duplikat. Perlu transaksi_id.",
    "parameters": {"type": "object", "properties": {"transaksi_id": {"type": "integer"}}, "required": ["transaksi_id"]}}

_TOOLS = (
    ("finnfinn_ringkasan", RINGKASAN_SCHEMA, finnfinn_ringkasan, "💸"),
    ("finnfinn_daftar_transaksi", DAFTAR_SCHEMA, finnfinn_daftar_transaksi, "📋"),
    ("finnfinn_ubah_kategori", UBAH_SCHEMA, finnfinn_ubah_kategori, "✏️"),
    ("finnfinn_hapus_transaksi", HAPUS_SCHEMA, finnfinn_hapus_transaksi, "🗑️"),
)


def register(ctx):
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(name=name, toolset="finnfinn", schema=schema, handler=handler,
                          check_fn=lambda: os.path.exists(DB), description=schema["description"], emoji=emoji)
