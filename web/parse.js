// Twin of finnfinn/parse.py — same regexes, weights and outputs; tests/parse_parity.mjs keeps them aligned.
// Python's lookbehinds are written as a leading `(^|…)` group here: iOS/Safari < 16.4 has no lookbehind.

// ---------- text (chat) ----------

const AMOUNT_RE = new RegExp(String.raw`(\brp\.?\s*|\bidr\s*)?([+-]?)(\d{1,3}(?:[.,]\d{3})+|\d{1,3}(?:\s\d{3})+(?!\s*(?:rb|ribu|k|jt|juta|m)\b)|\d+)(?:[.,](\d{1,2}))?\s*(rb|ribu|k|jt|juta|m)?\b`, 'gi');
const MULT = { rb: 1000, ribu: 1000, k: 1000, jt: 1000000, juta: 1000000, m: 1000000 };
const DATE_RE = new RegExp(String.raw`(^|[^\d/.\-])(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?(?![\d/.\-])`, 'g');
const TYPE_RE = /\b(pemasukan|pengeluaran|masuk|keluar)\b/gi;
const MASUK_RE = /\b(gaji|gajian|bonus|thr|masuk|pemasukan|terima|dapat|dividen|bunga|cashback|refund|jual|untung|honor|fee|komisi|hadiah)\b/i;

const KELUAR_MAP = [
  ['kopi|makan|nasi|warung|warteg|resto|gofood|grabfood|shopeefood|mie|bakso|sate|ayam|snack|jajan|cafe|kfc|mcd|'
   + 'starbucks|kopi kenangan|janji jiwa|mixue|hokben', 'Makanan & Minuman', 'Makan di luar'],
  ['indomaret|alfamart|alfamidi|supermarket|superindo|hypermart|transmart|sayur|buah|beras|telur|belanja bulanan|pasar',
   'Makanan & Minuman', 'Groceries'],
  ['bensin|bbm|pertalite|pertamax|solar|shell|pertamina|spbu', 'Transportasi', 'BBM'],
  ['gojek|grab|ojek|taxi|taksi|bluebird|maxim|angkot|busway|krl|mrt|kereta|bus|tol', 'Transportasi', 'Ojek-Taxi'],
  ['parkir', 'Transportasi', 'Parkir'],
  ['listrik|pln|token', 'Tagihan', 'Listrik'],
  ['wifi|internet|indihome|biznet|first media|myrepublic', 'Tagihan', 'Internet'],
  [String.raw`pulsa|kuota|paket data|telkomsel|xl|indosat|tri|by\.u`, 'Tagihan', 'Pulsa'],
  ['baju|celana|sepatu|kaos|jaket|tas|uniqlo|h&m', 'Belanja', 'Pakaian'],
  ['hp|laptop|charger|headset|elektronik|kabel|mouse', 'Belanja', 'Elektronik'],
  ['dokter|obat|apotek|klinik|rumah sakit|rs|vitamin|bpjs|kimia farma|guardian', 'Kesehatan', 'Umum'],
  ['nonton|bioskop|netflix|spotify|game|steam|konser|wisata|tiket|hiburan', 'Hiburan', 'Umum'],
  ['sekolah|kursus|buku|kuliah|spp|les|udemy|gramedia', 'Pendidikan', 'Umum'],
  ['sabun|deterjen|gas|lpg|galon|tisu|perabot|pdam|kebersihan', 'Rumah Tangga', 'Umum'],
].map(([p, k, s]) => [new RegExp(String.raw`\b(?:${p})`, 'i'), k, s]);
const MASUK_MAP = [
  ['gaji|gajian|honor|fee|komisi', 'Gaji'],
  ['bonus|thr|hadiah', 'Bonus'],
  ['dividen|bunga|saham|reksadana|crypto', 'Investasi'],
].map(([p, k]) => [new RegExp(String.raw`\b(?:${p})`, 'i'), k, 'Umum']);

const DAY = 86400000;
const utc = (y, m, d) => new Date(Date.UTC(y, m - 1, d));
const iso = (dt) => dt.toISOString().slice(0, 10);
const fromIso = (s) => utc(+s.slice(0, 4), +s.slice(5, 7), +s.slice(8, 10));
const mkDate = (y, m, d) => { // null when the calendar date does not exist (Python's ValueError)
  const dt = utc(y, m, d);
  return y >= 1 && dt.getUTCFullYear() === y && dt.getUTCMonth() === m - 1 && dt.getUTCDate() === d ? dt : null;
};

function value(num, dec, suf) {
  const n = parseInt(num.replace(/\D/g, ''), 10);
  const mult = MULT[(suf || '').toLowerCase()] || 1;
  if (dec && mult > 1) return n * mult + Math.floor(parseInt(dec, 10) * mult / 10 ** dec.length);
  return n * mult;
}

export function parseAmount(text) {
  const strong = [], bare = [];
  for (const m of text.matchAll(AMOUNT_RE)) {
    const [, rp, , num, dec, suf] = m;
    const val = value(num, dec, suf);
    (rp || suf || !/^\d+$/.test(num) || val >= 1000 ? strong : bare).push([val, [m.index, m.index + m[0].length]]);
  }
  if (strong.length) {
    const [val, span] = strong[0];
    return { jumlah: val, ambiguous: false, multiple: strong.length > 1,
      error: val >= 100 && val <= 100000000000 ? null : 'range', span };
  }
  if (bare.length) {
    const [val, span] = bare[0];
    return { jumlah: val, ambiguous: val >= 10, multiple: false, error: val >= 10 ? null : 'range', span };
  }
  return null;
}

export function guessJenis(text) {
  return /^\s*\+\s*\d/.test(text) || MASUK_RE.test(text) ? 'masuk' : 'keluar';
}

export function guessKategori(text, jenis = 'keluar') {
  for (const [rx, k, s] of jenis === 'masuk' ? MASUK_MAP : KELUAR_MAP) if (rx.test(text)) return [k, s];
  return jenis === 'masuk' ? ['Lainnya', 'Umum'] : [null, null];
}

function blank(s, spans) {
  for (const [a, b] of spans) s = s.slice(0, a) + ' '.repeat(b - a) + s.slice(b);
  return s;
}

function mkDateHint(d, m, y, today) {
  y = y == null ? today.getUTCFullYear() : y < 100 ? 2000 + y : y;
  const dt = mkDate(y, m, d);
  if (!dt) return null;
  return dt.getTime() <= today.getTime() + DAY ? dt : today;
}

export function parseText(text, todayIso) {
  const today = fromIso(todayIso);
  const s = text.trim().split(/\s+/).join(' ');
  const cuts = [];
  let tanggal = today;
  const km = /\bkemarin\b/i.exec(s);
  if (km) {
    tanggal = new Date(today.getTime() - DAY);
    cuts.push([km.index, km.index + km[0].length]);
  }
  for (const m of s.matchAll(DATE_RE)) {
    const d = mkDateHint(+m[2], +m[3], m[4] ? +m[4] : null, today);
    if (d) {
      tanggal = d;
      cuts.push([m.index + m[1].length, m.index + m[0].length]);
      break;
    }
  }
  let rest = blank(s, cuts);
  const amt = parseAmount(rest) || { jumlah: null, ambiguous: false, multiple: false, error: 'kosong', span: null };
  if (amt.span) cuts.push(amt.span);
  const jenis = guessJenis(rest);
  for (const m of rest.matchAll(TYPE_RE)) cuts.push([m.index, m.index + m[0].length]);
  rest = blank(s, cuts);
  const [kategori, sub] = guessKategori(rest, jenis);
  const trimRx = /^[ +\-–—,.:;|]+|[ +\-–—,.:;|]+$/g;
  const catatan = rest.trim().split(/\s+/).join(' ').replace(trimRx, '').slice(0, 80).replace(/\s+$/, '');
  return { jumlah: amt.jumlah, ambiguous: amt.ambiguous, multiple: amt.multiple, error: amt.error,
    catatan: catatan.slice(0, 1).toUpperCase() + catatan.slice(1), jenis, tanggal: iso(tanggal),
    kategori, subkategori: sub };
}

// ---------- receipt (OCR lines) ----------

const REPAIR = { O: '0', o: '0', l: '1', I: '1', '|': '1', S: '5', B: '8', Z: '2' };
const MONEY = new RegExp(String.raw`(^|[^\d/.])(?:rp\.?\s*)?(?!0)(\d{1,3}(?:[.,]\d{3})+|\d{4,})(?:[.,]\d{2})?(?:,-)?(?!\d)`, 'gi');
const IGNORE = new RegExp(String.raw`qty|pcs|[x×]\s?\d|\d\s?[x×](?!\w)|@|no\.|telp|tel\b|npwp|kasir|trx|ref|struk|nota|layanan|\d{2}:\d{2}`, 'i'); // OCR reads "2 x" as "2 ×"
const HI = new RegExp(String.raw`grand\s*total|total\s*(bayar|pembayaran|belanja|tagihan|akhir|pesanan|harga)|jumlah\s*(bayar|tagihan)|amount\s*due|net\s*total`, 'i');
const TOTAL = /\btotal\b|\bjumlah\b/i;
const SUB = new RegExp(String.raw`sub\s*total|subtotal|total\s*(item|qty|disc|diskon|promo|hemat)`, 'i');
const KEMBALI = /kembali|kembalian|change/i;
const BAYAR = /tunai|cash|debit|kredit|kartu|qris|dibayar/i;
const PAJAK = /ppn|pajak|tax|dpp|disc|diskon|potongan|voucher|poin/i;
const FALLBACK_SKIP = /kembali|change|tunai|cash/i;
const R_DATE = new RegExp(String.raw`(^|\D)(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})(?!\d)`);
const R_DATE_NAME = new RegExp(String.raw`(^|\D)(\d{1,2})\s*(jan|feb|mar|apr|mei|may|jun|jul|agu|aug|sep|okt|oct|nov|des|dec)[a-z]*\.?\s*(\d{2,4})(?!\d)`, 'i');
const R_ISO = new RegExp(String.raw`(^|\D)(\d{4})-(\d{2})-(\d{2})(?!\d)`);
const R_TIME = new RegExp(String.raw`(^|\D)(\d{1,2})([:.])(\d{2})(?!\d)`);
const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, mei: 5, may: 5, jun: 6, jul: 7, agu: 8, aug: 8,
  sep: 9, okt: 10, oct: 10, nov: 11, des: 12, dec: 12 };
const BRANDS = [
  ['indomaret', 'Indomaret'], ['alfamart', 'Alfamart'], ['alfamidi', 'Alfamidi'], ['superindo', 'Superindo'],
  ['hypermart', 'Hypermart'], ['transmart', 'Transmart'], [String.raw`kfc\b`, 'KFC'], [String.raw`mcd\b|mcdonald`, 'McD'],
  ['starbucks', 'Starbucks'], ['kopi kenangan', 'Kopi Kenangan'], ['janji jiwa', 'Janji Jiwa'], ['mixue', 'Mixue'],
  ['hokben', 'HokBen'], ['gofood|gojek', 'GoFood'], ['grabfood', 'GrabFood'], [String.raw`grab\b`, 'Grab'], ['shopee', 'Shopee'],
  ['tokopedia', 'Tokopedia'], ['pertamina', 'Pertamina'], [String.raw`shell\b`, 'Shell'], [String.raw`pln\b`, 'PLN'],
  ['indihome', 'IndiHome'], ['apotek', 'Apotek'], ['kimia farma', 'Kimia Farma'], ['guardian', 'Guardian'],
  ['gramedia', 'Gramedia'],
].map(([p, n]) => [new RegExp(String.raw`\b(?:${p})`, 'i'), n]);
const NOT_MERCHANT = new RegExp(String.raw`jl\.|jalan|telp|tel\.|npwp|no\.|struk|receipt|nota|faktur|kasir|tanggal|date`, 'i');

const title = (s) => s.toLowerCase().replace(/(^|\P{L})(\p{L})/gu, (_, p, c) => p + c.toUpperCase());

function repair(line) {
  line = line.replace(/[0-9OolI|SBZ.,]{3,}/g, (t) =>
    /\d/.test(t) && /[OolI|SBZ]/.test(t) ? t.replace(/[OolI|SBZ]/g, (c) => REPAIR[c]) : t);
  line = line.replace(/(\d)\s*([.,])\s*(\d{3})(?!\d)/g, '$1$2$3');
  return line.replace(/\b[Rr][Pp]\.?\s*/g, 'Rp ');
}

function amounts(line) {
  if (IGNORE.test(line) && !(HI.test(line) || TOTAL.test(line))) return [];
  const vals = [...line.matchAll(MONEY)].map((m) => parseInt(m[2].replace(/\D/g, ''), 10));
  return vals.filter((v) => v >= 100 && v <= 1000000000);
}

function score(line) {
  return 3 * HI.test(line) + 2 * TOTAL.test(line) - 3 * SUB.test(line)
    - 5 * KEMBALI.test(line) - 3 * BAYAR.test(line) - 3 * PAJAK.test(line);
}

function findDate(lines, today) {
  const lo = today.getTime() - 400 * DAY, hi = today.getTime() + DAY;
  for (let i = 0; i < lines.length; i++) {
    for (const rx of [R_DATE, R_DATE_NAME, R_ISO]) {
      const m = rx.exec(lines[i]);
      if (!m) continue;
      let [, , a, b, c] = m, d, mo, y;
      if (rx === R_ISO) [y, mo, d] = [+a, +b, +c];
      else if (rx === R_DATE_NAME) [d, mo, y] = [+a, MONTHS[b.toLowerCase().slice(0, 3)], +c];
      else {
        [d, mo, y] = [+a, +b, +c];
        if (mo > 12 && d <= 12) [d, mo] = [mo, d];
      }
      y = y < 100 ? 2000 + y : y;
      const dt = mkDate(y, mo, d);
      if (!dt) continue;
      if (dt.getTime() < lo || dt.getTime() > hi) continue;
      for (const j of [i, i + 1, i - 1]) {
        if (j >= 0 && j < lines.length) {
          const t = R_TIME.exec(j === i ? blank(lines[j], [[m.index + m[1].length, m.index + m[0].length]]) : lines[j]);
          if (t && (j === i || t[3] === ':') && +t[2] < 24 && +t[4] < 60) { // "12.50" off the date line is a price
            return [dt, `${String(+t[2]).padStart(2, '0')}:${t[4]}`];
          }
        }
      }
      return [dt, ''];
    }
  }
  return [today, ''];
}

function merchant(lines) {
  for (const line of lines) for (const [rx, name] of BRANDS) if (rx.test(line)) return name;
  for (const line of lines.slice(0, 4)) {
    if ((line.match(/[A-Za-z]/g) || []).length >= 3 && !NOT_MERCHANT.test(line)) return title(line).slice(0, 40);
  }
  return 'Struk';
}

export function parseReceipt(rawLines, todayIso) {
  const today = fromIso(todayIso);
  const lines = rawLines.filter((l) => l.trim()).map((l) => repair(l.trim()));
  const amts = lines.map(amounts);
  let best = null;
  for (let i = 0; i < lines.length; i++) {
    const sc = score(lines[i]);
    let val;
    if (amts[i].length) val = amts[i][amts[i].length - 1];
    else if (sc > 0 && i + 1 < lines.length && amts[i + 1].length) val = amts[i + 1][0];
    else continue;
    if (best === null || sc >= best[0]) best = [sc, val];
  }
  let jumlah, confidence;
  if (best && best[0] > 0) [jumlah, confidence] = [best[1], 'high'];
  else {
    const cands = [];
    for (let i = Math.floor(lines.length * 0.4); i < lines.length; i++) {
      if (!FALLBACK_SKIP.test(lines[i])) cands.push(...amts[i]);
    }
    [jumlah, confidence] = cands.length ? [Math.max(...cands), 'low'] : [null, 'low'];
  }
  const [tanggal, waktu] = findDate(lines, today);
  const name = merchant(lines);
  let [kategori, sub] = guessKategori(name);
  if (!kategori) [kategori, sub] = guessKategori(lines.join(' '));
  return { jumlah, confidence, tanggal: iso(tanggal), waktu, catatan: name, kategori, subkategori: sub };
}
