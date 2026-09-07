// Store interface: init / list(from,to) / add / update / remove / categories / saveCategories / mode
// Tx = {id, jenis:'masuk'|'keluar', jumlah, kategori, subkategori, catatan, tanggal:'YYYY-MM-DD', waktu:'HH:MM', sumber}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

export async function api(method, path, body) {
  const tg = window.Telegram && window.Telegram.WebApp;
  const headers = {};
  if (tg && tg.initData) headers.Authorization = 'tma ' + tg.initData;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, 'Tidak ada koneksi — coba lagi sebentar.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new ApiError(res.status, res.status === 401 ? 'Sesi Telegram kedaluwarsa. Tutup lalu buka lagi Finn Finn ya.'
      : data.error || `Server error ${res.status}`);
  }
  return data;
}

export class ServerStore {
  get mode() { return 'server'; }
  async init() {}
  list(from, to) { return api('GET', `/api/tx?from=${from}&to=${to}`); }
  add(tx) { return api('POST', '/api/tx', tx); }
  update(id, patch) { return api('PUT', '/api/tx/' + id, patch); }
  remove(id) { return api('DELETE', '/api/tx/' + id); }
  categories() { return api('GET', '/api/categories'); }
  saveCategories(list) { return api('PUT', '/api/categories', list); }
}

// Same seed as db.SEED — a guest never asks the server for categories.
const SEED = [
  ['masuk', 'Gaji', 'Umum', 'payments'], ['masuk', 'Bonus', 'Umum', 'redeem'], ['masuk', 'Investasi', 'Umum', 'trending_up'],
  ['masuk', 'Lainnya', 'Umum', 'add_circle'],
  ['keluar', 'Makanan & Minuman', 'Makan di luar', 'restaurant'], ['keluar', 'Makanan & Minuman', 'Groceries', 'shopping_cart'],
  ['keluar', 'Transportasi', 'BBM', 'local_gas_station'], ['keluar', 'Transportasi', 'Ojek-Taxi', 'two_wheeler'],
  ['keluar', 'Transportasi', 'Parkir', 'local_parking'], ['keluar', 'Tagihan', 'Listrik', 'bolt'],
  ['keluar', 'Tagihan', 'Internet', 'wifi'], ['keluar', 'Tagihan', 'Pulsa', 'smartphone'],
  ['keluar', 'Belanja', 'Pakaian', 'checkroom'], ['keluar', 'Belanja', 'Elektronik', 'devices'],
  ['keluar', 'Kesehatan', 'Umum', 'medical_services'], ['keluar', 'Hiburan', 'Umum', 'movie'],
  ['keluar', 'Pendidikan', 'Umum', 'school'], ['keluar', 'Rumah Tangga', 'Umum', 'home'], ['keluar', 'Lainnya', 'Umum', 'more_horiz'],
].map(([j, k, s, i]) => [j, k, s, i, 1]);
const SEAL_BYTES = 3900;
const enc = new TextEncoder();
const mirror = {
  get: (k) => { try { return localStorage.getItem('ff_' + k); } catch { return null; } },
  set: (k, v) => { try { localStorage.setItem('ff_' + k, v); } catch {} },
  del: (k) => { try { localStorage.removeItem('ff_' + k); } catch {} },
  keys: () => { try { return Object.keys(localStorage).filter((k) => k.startsWith('ff_tx_') || k === 'ff_cat').map((k) => k.slice(3)); } catch { return []; } },
};

export class CloudStore {
  constructor(cloud, onWarn) {
    this.cloud = cloud;
    this.onWarn = onWarn || (() => {});
    this.keys = null;
    this.cat = null;
    this.where = {}; // id → chunk key, filled by every read
  }

  get mode() { return 'cloud'; }

  call(fn, ...args) {
    return new Promise((res, rej) => this.cloud[fn](...args, (err, val) => (err ? rej(new Error(String(err))) : res(val))));
  }

  async init() {
    try {
      this.keys = new Set(await this.call('getKeys'));
    } catch {
      this.keys = new Set(mirror.keys()); // offline: the mirror is all we have
    }
    if (this.keys.size >= 900) this.onWarn('Penyimpanan Telegram Cloud hampir penuh');
    if (!this.keys.has('cat')) {
      await this.set('cat', JSON.stringify(SEED));
      await this.set('v', '1');
    }
  }

  async read(keys) {
    if (!keys.length) return {};
    let items;
    try {
      items = await this.call('getItems', keys);
      for (const k of keys) items[k] ? mirror.set(k, items[k]) : mirror.del(k);
    } catch {
      items = Object.fromEntries(keys.map((k) => [k, mirror.get(k)]));
    }
    return items;
  }

  async set(key, value) {
    await this.call('setItem', key, value);
    this.keys.add(key);
    mirror.set(key, value);
  }

  async del(key) {
    await this.call('removeItem', key);
    this.keys.delete(key);
    mirror.del(key);
  }

  async categories() {
    if (!this.cat) this.cat = JSON.parse((await this.read(['cat'])).cat || JSON.stringify(SEED));
    return this.cat.map(([jenis, kategori, subkategori, ikon, aktif], i) => ({ id: i, jenis, kategori, subkategori, ikon, urutan: i, aktif }));
  }

  async saveCategories(list) {
    // Indices are chunk references, so a leaf is never removed: unknown → append, missing → aktif 0.
    await this.categories();
    const cur = this.cat;
    const idx = (c) => cur.findIndex(([j, k, s]) => j === c.jenis && k === c.kategori && s === c.subkategori);
    const next = cur.map((c) => [...c.slice(0, 4), 0]);
    for (const c of list) {
      const i = idx(c);
      if (i >= 0) next[i] = [c.jenis, c.kategori, c.subkategori, c.ikon || next[i][3], c.aktif === 0 ? 0 : 1];
      else next.push([c.jenis, c.kategori, c.subkategori, c.ikon || 'category', c.aktif === 0 ? 0 : 1]);
    }
    this.cat = next;
    await this.set('cat', JSON.stringify(next));
    return this.categories();
  }

  chunkKeys(month) { // 'YYYYMM' → its chunk keys sorted by n
    return [...this.keys].filter((k) => k.startsWith('tx_' + month + '_')).sort((a, b) => +a.split('_')[2] - +b.split('_')[2]);
  }

  rowToTx([id, j, jumlah, ci, catatan, tanggal, waktu, s]) {
    const c = this.cat[ci] || ['keluar', 'Lainnya', 'Umum'];
    return { id, jenis: j === 'm' ? 'masuk' : 'keluar', jumlah, kategori: c[1], subkategori: c[2], catatan, tanggal, waktu,
      sumber: s === 's' ? 'struk' : 'app' };
  }

  txToRow(tx) {
    let ci = this.cat.findIndex(([j, k, s]) => j === tx.jenis && k === tx.kategori && s === tx.subkategori);
    if (ci < 0) ci = this.cat.findIndex(([j, k]) => j === tx.jenis && k === 'Lainnya');
    return [tx.id, tx.jenis === 'masuk' ? 'm' : 'k', tx.jumlah, ci, tx.catatan || '', tx.tanggal, tx.waktu || '', tx.sumber === 'struk' ? 's' : 'a'];
  }

  async list(from, to) {
    await this.categories();
    const keys = [];
    for (let m = from.slice(0, 7); m <= to.slice(0, 7);) {
      keys.push(...this.chunkKeys(m.replace('-', '')));
      const [y, mo] = m.split('-').map(Number);
      m = mo === 12 ? `${y + 1}-01` : `${y}-${String(mo + 1).padStart(2, '0')}`;
    }
    const items = await this.read(keys);
    const out = [];
    for (const k of keys) {
      for (const row of JSON.parse(items[k] || '[]')) {
        this.where[row[0]] = k;
        if (row[5] >= from && row[5] <= to) out.push(this.rowToTx(row));
      }
    }
    return out.sort((a, b) => (b.tanggal + b.waktu).localeCompare(a.tanggal + a.waktu) || (b.id > a.id ? 1 : -1));
  }

  add(tx) {
    return this.append({ ...tx, id: Date.now().toString(36) + Math.random().toString(36).slice(2, 5).padEnd(3, '0') });
  }

  async append(tx) { // write a row (id already set) into its month's open chunk
    await this.categories();
    const month = tx.tanggal.slice(0, 7).replace('-', '');
    const chunks = this.chunkKeys(month);
    let key = chunks[chunks.length - 1] || 'tx_' + month + '_1';
    let rows = chunks.length ? JSON.parse((await this.read([key]))[key] || '[]') : [];
    const row = this.txToRow(tx);
    if (rows.length && enc.encode(JSON.stringify([...rows, row])).length > SEAL_BYTES) {
      key = 'tx_' + month + '_' + (+key.split('_')[2] + 1);
      rows = [];
    }
    rows.push(row);
    await this.set(key, JSON.stringify(rows));
    this.where[tx.id] = key;
    if (this.keys.size >= 900) this.onWarn('Penyimpanan Telegram Cloud hampir penuh');
    return tx;
  }

  async locate(id) { // → [key, rows] holding the id, scanning every chunk when the read index has no entry
    const keys = this.where[id] ? [this.where[id]] : [...this.keys].filter((k) => k.startsWith('tx_'));
    const items = await this.read(keys);
    for (const k of keys) {
      const rows = JSON.parse(items[k] || '[]');
      if (rows.some((r) => r[0] === id)) return [k, rows];
    }
    throw new ApiError(404, 'Catatan tidak ditemukan');
  }

  async update(id, patch) {
    await this.categories();
    const [key, rows] = await this.locate(id);
    const i = rows.findIndex((r) => r[0] === id);
    const tx = { ...this.rowToTx(rows[i]), ...patch, id };
    if (tx.tanggal.slice(0, 7).replace('-', '') !== key.split('_')[1]) { // moved to another month → its chunk
      await this.writeRows(key, rows.filter((_, j) => j !== i));
      return this.append(tx);
    }
    rows[i] = this.txToRow(tx);
    await this.writeRows(key, rows);
    return tx;
  }

  async remove(id) {
    const [key, rows] = await this.locate(id);
    await this.writeRows(key, rows.filter((r) => r[0] !== id));
    delete this.where[id];
    return { ok: true };
  }

  writeRows(key, rows) {
    return rows.length ? this.set(key, JSON.stringify(rows)) : this.del(key);
  }
}
