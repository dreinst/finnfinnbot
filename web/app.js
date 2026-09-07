import { api, CloudStore, ServerStore } from './store.js';
import { parseAmount } from './parse.js';
import { scanReceipt, stopOcr } from './ocr.js';

const tg = window.Telegram && window.Telegram.WebApp;
const $ = (id) => document.getElementById(id);
const safe = (f) => { try { return f(); } catch { return undefined; } };
const VIEWS = ['beranda', 'arus-kas', 'dompet', 'laporan'];
const DAYS = ['Min', 'Sen', 'Sel', 'Rab', 'Kam', 'Jum', 'Sab'];
const DAYS_FULL = ['Minggu', 'Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu'];
const MONTHS = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember'];
const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des'];
const DONUT = ['#00694d', '#ff6569', '#316bf3', '#d97706', '#61dcae', '#ffb3b1', '#b4c5ff', '#6d7a73'];
const TIPS = [
  'Menabung sedikit setiap hari membawa rasa tenang di hari tua. Kamu hebat!',
  'Catat pengeluaran kecil juga ya — jajan Rp 10.000 sehari itu Rp 300.000 sebulan ☕',
  'Coba aturan 50/30/20: 50% kebutuhan, 30% keinginan, 20% tabungan 💡',
  'Sebelum belanja, tunggu 24 jam. Kalau masih ingin, baru beli 😉',
  'Dana darurat idealnya 3–6 kali pengeluaran bulanan. Mulai dari yang kecil dulu 🌱',
  'Bandingkan harga sebelum membeli — dua menit bisa hemat puluhan ribu 🔍',
  'Bawa bekal 2 hari seminggu bisa menghemat ratusan ribu sebulan 🍱',
  'Bayar tagihan tepat waktu supaya bebas denda dan hati tenang ✨',
  'Pemasukan tambahan? Sisihkan dulu sebagian sebelum dipakai 💚',
  'Cek laporan mingguanmu tiap Minggu malam — lima menit saja cukup 📊',
];

let store, cats = [], me = { mode: 'guest', nama: '' }, view = 'beranda', txIndex = {};
const ak = { mode: 'harian', anchor: '' };
const lp = { mode: 'bulan', y: 0, m: 0 };
const S = { tx: null, jenis: 'keluar', kat: null, sub: null, sumber: 'app' };

// ---------- helpers ----------
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const fmt = (n) => String(Math.round(Math.abs(n))).replace(/\B(?=(\d{3})+(?!\d))/g, '.');
const rp = (n) => 'Rp ' + fmt(n);
const pad = (n) => String(n).padStart(2, '0');
const WIB = { timeZone: 'Asia/Jakarta' };
const todayIso = () => new Date().toLocaleDateString('en-CA', WIB);
const nowHM = () => new Date().toLocaleTimeString('en-GB', { ...WIB, hour: '2-digit', minute: '2-digit' });
const toDate = (iso) => new Date(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10));
const toIso = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const addDays = (iso, n) => { const d = toDate(iso); d.setDate(d.getDate() + n); return toIso(d); };
const monthRange = (y, m) => [`${y}-${pad(m)}-01`, `${y}-${pad(m)}-${pad(new Date(y, m, 0).getDate())}`];
const monday = (iso) => addDays(iso, -((toDate(iso).getDay() + 6) % 7));
const dayOfYear = (iso) => Math.round((toDate(iso) - new Date(toDate(iso).getFullYear(), 0, 1)) / 864e5);
const sums = (txs) => txs.reduce((a, t) => { a[t.jenis] += t.jumlah; return a; }, { masuk: 0, keluar: 0 });
function byKey(txs, jenis, key) { // → [[key, total]] desc
  const m = new Map();
  for (const t of txs) if (t.jenis === jenis) m.set(t[key], (m.get(t[key]) || 0) + t.jumlah);
  return [...m].sort((a, b) => b[1] - a[1]);
}
const iconOf = (jenis, kategori, sub) => (cats.find((c) => c.jenis === jenis && c.kategori === kategori && (!sub || c.subkategori === sub))
  || cats.find((c) => c.jenis === jenis && c.kategori === kategori) || {}).ikon || 'category';
function dateLabel(iso, long) {
  const t = todayIso();
  if (iso === t) return 'Hari ini';
  if (iso === addDays(t, -1)) return 'Kemarin';
  const d = toDate(iso);
  return `${long ? DAYS[d.getDay()] + ', ' : ''}${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}${d.getFullYear() !== toDate(t).getFullYear() || long ? ' ' + d.getFullYear() : ''}`;
}
const metaLine = (t) => dateLabel(t.tanggal) + (t.waktu ? ', ' + t.waktu : '');
const index = (txs) => Object.fromEntries(txs.map((t) => [t.id, t]));

let toastTimer;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 2400);
}
function screen(msg, btn, fn) {
  $('screen-msg').textContent = msg;
  const b = $('screen-btn');
  b.hidden = !btn;
  b.textContent = btn || '';
  b.onclick = fn || null;
  $('screen').hidden = false;
}
function fail(e) {
  if (e.status === 401) screen(e.message, 'Muat ulang', () => location.reload());
  else toast(e.message || 'Terjadi kesalahan');
}

// ---------- shared renderers ----------
function rowHtml(t) {
  const masuk = t.jenis === 'masuk';
  return `<button type="button" data-id="${esc(t.id)}" class="w-full min-h-[72px] bg-surface-container-lowest rounded-DEFAULT p-space-md shadow-sm flex items-center justify-between gap-space-sm transition-all hover:shadow-md active:scale-[.99] text-left">
<div class="flex items-center gap-space-sm min-w-0">
<div class="w-12 h-12 rounded-full ${masuk ? 'bg-primary-fixed text-on-primary-fixed' : 'bg-secondary-fixed text-on-secondary-fixed'} flex items-center justify-center flex-shrink-0"><span class="material-symbols-outlined text-[26px]">${esc(iconOf(t.jenis, t.kategori, t.subkategori))}</span></div>
<div class="flex flex-col min-w-0"><span class="font-body-bold text-body-bold text-on-surface truncate">${esc(t.catatan || t.subkategori)}</span>
<div class="flex flex-wrap items-center gap-space-xxs text-on-surface-variant font-label-sm text-label-sm"><span class="px-2 py-0.5 rounded-full ${masuk ? 'bg-surface-container text-primary' : 'bg-secondary-fixed-dim/30 text-secondary'} font-bold truncate">${esc(t.kategori)}</span><span class="whitespace-nowrap">• ${esc(metaLine(t))}</span></div></div></div>
<div class="flex flex-col items-end flex-shrink-0"><span class="font-body-bold text-body-bold ${masuk ? 'text-primary' : 'text-on-surface'} font-bold tnum">${masuk ? '+' : '-'}${rp(t.jumlah)}</span><span class="font-label-sm text-label-sm ${masuk ? 'text-primary' : 'text-on-surface-variant'}">${t.sumber === 'struk' ? 'Dari struk 🧾' : esc(t.subkategori)}</span></div></button>`;
}
function bindRows(el) {
  el.onclick = (e) => { const b = e.target.closest('[data-id]'); if (b && txIndex[b.dataset.id]) openSheet(txIndex[b.dataset.id]); };
}
function barsHtml(cols) { // cols: [{label, full, masuk, keluar, hot}]; 12 columns → thinner bars, smaller labels
  const max = Math.max(1, ...cols.flatMap((c) => [c.masuk, c.keluar]));
  const h = (v) => `height:max(${(v / max * 100).toFixed(1)}%,3px)`;
  const [w, lbl] = cols.length > 7 ? ['w-2', 'text-[10px]'] : ['w-3', 'font-label-md text-label-md'];
  return `<div class="w-full flex items-end justify-between pt-space-md pb-space-xs px-space-xs h-48 bg-surface-container-low rounded-DEFAULT">${cols.map((c, i) => `<button type="button" data-i="${i}" class="flex flex-col items-center gap-space-xs flex-1 active:opacity-70 min-w-0"><div class="flex items-end gap-1 h-32 w-full justify-center"><div class="${w} bg-primary rounded-full transition-all" style="${h(c.masuk)}"></div><div class="${w} bg-secondary-container rounded-full transition-all" style="${h(c.keluar)}"></div></div><span class="${lbl} font-bold ${c.hot ? 'text-primary' : 'text-on-surface'} truncate">${esc(c.label)}</span></button>`).join('')}</div>`;
}
function bindBars(wrap, label, cols) {
  wrap.onclick = (e) => {
    const b = e.target.closest('[data-i]');
    if (!b) return;
    const c = cols[+b.dataset.i];
    label.textContent = `${c.full || c.label}: masuk ${rp(c.masuk)} · keluar ${rp(c.keluar)}`;
    label.hidden = false;
  };
}
function dayCols(txs, from, n) { // n day columns starting at `from`
  const today = todayIso();
  return Array.from({ length: n }, (_, i) => {
    const iso = addDays(from, i), d = toDate(iso), s = sums(txs.filter((t) => t.tanggal === iso));
    return { label: DAYS[d.getDay()], full: `${DAYS_FULL[d.getDay()]}, ${d.getDate()} ${MONTHS_SHORT[d.getMonth()]}`, ...s, hot: iso === today };
  });
}
function vsHtml(cur, prev) {
  if (!prev) return 'Belum ada pembanding periode sebelumnya';
  const pct = Math.round((cur - prev) / prev * 100);
  return `<span class="${pct > 0 ? 'text-secondary' : 'text-primary'} font-bold">${pct > 0 ? '▲' : '▼'} ${Math.abs(pct)}%</span> vs periode sebelumnya`;
}
const segmented = (items, active, attr) => `<div class="flex gap-space-xxs bg-surface-container rounded-full p-1">${items.map(([k, label]) => `<button type="button" ${attr}="${k}" class="flex-1 h-10 rounded-full font-label-md text-label-md transition-all ${k === active ? 'bg-surface-container-lowest text-primary shadow-sm font-bold' : 'text-on-surface-variant'}">${label}</button>`).join('')}</div>`;
const stepper = (label, id, nextDisabled) => `<div class="flex items-center justify-between"><button type="button" id="${id}-prev" class="w-12 h-12 rounded-full bg-surface-container-lowest shadow-sm flex items-center justify-center active:scale-95"><span class="material-symbols-outlined">chevron_left</span></button><span class="font-headline-sm text-headline-sm text-on-surface">${esc(label)}</span><button type="button" id="${id}-next" ${nextDisabled ? 'disabled' : ''} class="w-12 h-12 rounded-full bg-surface-container-lowest shadow-sm flex items-center justify-center active:scale-95 disabled:opacity-30"><span class="material-symbols-outlined">chevron_right</span></button></div>`;
const summaryCard = ({ masuk, keluar }) => `<div class="bg-surface-container-lowest rounded-lg p-space-lg shadow-md grid grid-cols-3 gap-space-xs text-center">
<div class="flex flex-col"><span class="font-label-sm text-label-sm text-on-surface-variant">Masuk</span><span class="font-label-lg text-label-lg text-primary tnum">+${rp(masuk)}</span></div>
<div class="flex flex-col"><span class="font-label-sm text-label-sm text-on-surface-variant">Keluar</span><span class="font-label-lg text-label-lg text-secondary tnum">-${rp(keluar)}</span></div>
<div class="flex flex-col"><span class="font-label-sm text-label-sm text-on-surface-variant">Selisih</span><span class="font-label-lg text-label-lg ${masuk - keluar < 0 ? 'text-secondary' : 'text-on-surface'} tnum">${masuk - keluar < 0 ? '-' : '+'}${rp(masuk - keluar)}</span></div></div>`;
const legend = '<div class="flex items-center gap-space-xs"><div class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-primary"></span><span class="font-label-sm text-label-sm text-on-surface">Masuk</span></div><div class="flex items-center gap-1"><span class="w-3 h-3 rounded-full bg-secondary-container"></span><span class="font-label-sm text-label-sm text-on-surface">Keluar</span></div></div>';

// ---------- Beranda ----------
async function renderBeranda() {
  const today = todayIso(), d = toDate(today), y = d.getFullYear(), m = d.getMonth() + 1;
  const [ms, mEnd] = monthRange(y, m);
  const all = await store.list([ms, addDays(today, -45)].sort()[0], mEnd);
  txIndex = index(all);
  const month = all.filter((t) => t.tanggal >= ms);
  const { masuk, keluar } = sums(month);
  const pct = masuk ? Math.round(keluar / masuk * 100) : 0;
  let mood;
  if (!masuk && !keluar) mood = ['eco', 'Mulai catat yuk', '🌱', 'Catat transaksi pertamamu hari ini!', 'Baru', false];
  else if (!masuk || keluar / masuk > 0.9) mood = ['sentiment_worried', 'Hati-hati, Pengeluaran Tinggi', '👀', masuk ? `Pengeluaran sudah ${pct}% dari pemasukan bulan ini` : 'Belum ada pemasukan bulan ini', 'Waspada', true];
  else if (keluar / masuk < 0.5) mood = ['sentiment_very_satisfied', 'Kondisi Keuangan Sehat!', '✨', `Hebat! Pengeluaran terkontrol ${pct}% bulan ini!`, 'Stabil', false];
  else mood = ['sentiment_satisfied', 'Cukup Terkendali', '👍', `Pengeluaran ${pct}% dari pemasukan. Tetap jaga ya!`, 'Aman', false];
  const [icon, title, emoji, sub, pill, coral] = mood;
  $('mood-icon').textContent = icon;
  $('mood-title').textContent = title;
  $('mood-emoji').textContent = emoji;
  $('mood-sub').textContent = sub;
  $('mood-pill-text').textContent = pill;
  $('mood-pill').className = `px-space-sm py-1 rounded-full font-label-sm text-label-sm font-bold shadow-sm whitespace-nowrap flex items-center gap-1 ${coral ? 'bg-secondary-fixed/40 text-secondary' : 'bg-surface-container-lowest text-primary'}`;
  $('mood-dot').className = `w-2 h-2 rounded-full animate-pulse ${coral ? 'bg-secondary' : 'bg-primary'}`;

  const sisa = masuk - keluar;
  $('balanceText').textContent = (sisa < 0 ? '-' : '') + fmt(sisa);
  $('balance-sub').textContent = `Update otomatis • Hari ini, ${nowHM()} WIB`;

  $('month-chip').textContent = `${MONTHS_SHORT[m - 1]} ${y}`;
  $('masuk-total').textContent = '+' + rp(masuk);
  $('keluar-total').textContent = '-' + rp(keluar);
  const cap = (jenis) => byKey(month, jenis, 'kategori').slice(0, 2).map(([k]) => k).join(' & ') || 'Belum ada';
  $('masuk-cap').textContent = cap('masuk');
  $('keluar-cap').textContent = cap('keluar');
  const kPct = masuk ? Math.min(100, pct) : keluar ? 100 : 0, sPct = masuk ? 100 - kPct : 0;
  $('ratio-badge').textContent = `${sPct}% Tersisa`;
  $('ratio-badge').className = `px-2 py-0.5 rounded-full font-label-sm text-label-sm font-bold whitespace-nowrap ${masuk ? 'bg-primary-fixed text-on-primary-fixed' : 'bg-secondary-fixed text-on-secondary-fixed'}`;
  $('ratio-right').textContent = !masuk ? 'Belum ada pemasukan bulan ini' : sisa >= 0 ? `+${rp(sisa)} (Surplus 🟢)` : `-${rp(sisa)} (Defisit 🔴)`;
  $('ratio-right').className = `font-label-md text-label-md font-bold tnum ${masuk && sisa >= 0 ? 'text-primary' : 'text-secondary'}`;
  $('bar-sisa').style.width = sPct + '%';
  $('bar-keluar').style.width = kPct + '%';
  $('bar-l').textContent = `Pengeluaran (${kPct}%)`;
  $('bar-r').textContent = `Simpanan Surplus (${sPct}%)`;

  const cols = dayCols(all, addDays(today, -6), 7);
  $('chart7').innerHTML = barsHtml(cols);
  $('chart7-label').hidden = true;
  bindBars($('chart7'), $('chart7-label'), cols);
  const top = cols.reduce((a, c) => (c.keluar > a.keluar ? c : a), { keluar: 0 });
  $('insight').innerHTML = top.keluar
    ? `Pengeluaran terbesar minggu ini di hari <strong>${esc(top.full.split(',')[0])}</strong> (${rp(top.keluar)}). Yuk, cek apa yang bisa dihemat 💪`
    : 'Belum ada pengeluaran 7 hari ini. Keren, terus pertahankan! 🌟';

  $('recent-count').textContent = `${all.filter((t) => t.tanggal === today).length} Baru`;
  const recent = all.slice(0, 4);
  $('recent-list').innerHTML = recent.length ? recent.map(rowHtml).join('')
    : '<div class="text-center text-on-surface-variant font-label-md text-label-md py-space-md">Belum ada transaksi. Yuk catat yang pertama! ✍️</div>';
  bindRows($('recent-list'));
  $('tip').textContent = TIPS[dayOfYear(today) % TIPS.length];
}

// ---------- Arus Kas ----------
function akRange() {
  const a = ak.anchor;
  if (ak.mode === 'harian') return [a, a];
  if (ak.mode === 'mingguan') { const mo = monday(a); return [mo, addDays(mo, 6)]; }
  return monthRange(+a.slice(0, 4), +a.slice(5, 7));
}
function akLabel([from, to]) {
  if (ak.mode === 'harian') return dateLabel(from, true);
  if (ak.mode === 'mingguan') {
    const a = toDate(from), b = toDate(to);
    return `${a.getDate()}${a.getMonth() !== b.getMonth() ? ' ' + MONTHS_SHORT[a.getMonth()] : ''} – ${b.getDate()} ${MONTHS_SHORT[b.getMonth()]} ${b.getFullYear()}`;
  }
  return `${MONTHS[+from.slice(5, 7) - 1]} ${from.slice(0, 4)}`;
}
function akStep(n) {
  if (ak.mode === 'harian') ak.anchor = addDays(ak.anchor, n);
  else if (ak.mode === 'mingguan') ak.anchor = addDays(ak.anchor, 7 * n);
  else { const d = toDate(ak.anchor); d.setDate(1); d.setMonth(d.getMonth() + n); ak.anchor = toIso(d); }
  if (ak.anchor > todayIso()) ak.anchor = todayIso();
  render();
}
async function renderArusKas() {
  const today = todayIso();
  const [from, to] = akRange();
  const all = await store.list(ak.mode === 'harian' ? addDays(from, -6) : from, to);
  txIndex = index(all);
  const txs = all.filter((t) => t.tanggal >= from);
  let cols;
  if (ak.mode === 'harian') cols = dayCols(all, addDays(from, -6), 7);
  else if (ak.mode === 'mingguan') cols = dayCols(all, from, 7);
  else {
    const last = +to.slice(8, 10);
    cols = Array.from({ length: Math.ceil(last / 7) }, (_, w) => {
      const a = addDays(from, 7 * w), b = addDays(from, Math.min(7 * w + 6, last - 1));
      return { label: `W${w + 1}`, full: `Minggu ${w + 1} (${+a.slice(8, 10)}–${+b.slice(8, 10)})`, ...sums(txs.filter((t) => t.tanggal >= a && t.tanggal <= b)), hot: today >= a && today <= b };
    });
  }
  const groups = [];
  for (const t of txs) {
    let g = groups[groups.length - 1];
    if (!g || g.date !== t.tanggal) groups.push((g = { date: t.tanggal, txs: [], masuk: 0, keluar: 0 }));
    g.txs.push(t);
    g[t.jenis] += t.jumlah;
  }
  const el = $('view-arus-kas');
  el.innerHTML = `${segmented([['harian', 'Harian'], ['mingguan', 'Mingguan'], ['bulanan', 'Bulanan']], ak.mode, 'data-mode')}
${stepper(akLabel([from, to]), 'ak', to >= today)}
${summaryCard(sums(txs))}
<div class="bg-surface-container-lowest rounded-lg p-space-lg shadow-md flex flex-col gap-space-sm">
<div class="flex items-center justify-between"><h2 class="font-headline-sm text-headline-sm text-on-surface">${ak.mode === 'harian' ? '7 hari sampai tanggal ini' : ak.mode === 'mingguan' ? 'Senin – Minggu' : 'Per minggu'}</h2>${legend}</div>
<div id="ak-bars">${barsHtml(cols)}</div><span id="ak-bar-label" class="font-label-sm text-label-sm text-on-surface-variant text-center tnum" hidden></span></div>
<div id="ak-list" class="flex flex-col gap-space-xs">${groups.length ? groups.map((g) => `<div class="sticky top-20 z-10 bg-surface/95 backdrop-blur py-space-xs flex items-center justify-between"><span class="font-label-lg text-label-lg text-on-surface">${esc(dateLabel(g.date, true))}</span><span class="font-label-sm text-label-sm text-on-surface-variant tnum">${g.masuk ? `<span class="text-primary">+${rp(g.masuk)}</span> ` : ''}${g.keluar ? `-${rp(g.keluar)}` : ''}</span></div>${g.txs.map(rowHtml).join('')}`).join('')
    : '<div class="text-center text-on-surface-variant font-body-md text-body-md py-space-xl">Belum ada catatan di periode ini 🙂</div>'}</div>`;
  el.querySelectorAll('[data-mode]').forEach((b) => { b.onclick = () => { ak.mode = b.dataset.mode; render(); }; });
  $('ak-prev').onclick = () => akStep(-1);
  $('ak-next').onclick = () => akStep(1);
  bindBars($('ak-bars'), $('ak-bar-label'), cols);
  bindRows($('ak-list'));
}

// ---------- Laporan ----------
function breakdownHtml(txs, jenis, total, withSub) {
  return byKey(txs, jenis, 'kategori').map(([k, v], i) => `<button type="button" data-kat="${esc(k)}" class="w-full min-h-[48px] flex items-center gap-space-xs px-space-xs rounded-DEFAULT active:bg-surface-container-low text-left"><span class="material-symbols-outlined text-[24px] flex-shrink-0" style="color:${jenis === 'keluar' ? DONUT[i % DONUT.length] : '#00694d'}">${esc(iconOf(jenis, k))}</span><span class="flex-1 min-w-0 font-label-lg text-label-lg text-on-surface leading-tight">${esc(k)}</span><span class="font-label-lg text-label-lg text-on-surface tnum whitespace-nowrap">${rp(v)}</span><span class="w-10 text-right font-label-sm text-label-sm text-on-surface-variant tnum">${Math.round(v / total * 100)}%</span></button>${withSub ? `<div class="pl-space-2xl pr-space-xs flex flex-col gap-space-xxs" hidden>${byKey(txs.filter((t) => t.kategori === k), jenis, 'subkategori').map(([s, sv]) => `<div class="flex justify-between font-label-md text-label-md text-on-surface-variant"><span>${esc(s)}</span><span class="tnum">${rp(sv)}</span></div>`).join('')}</div>` : ''}`).join('');
}
async function renderLaporan() {
  const today = todayIso();
  let range, prevRange, label;
  if (lp.mode === 'bulan') {
    range = monthRange(lp.y, lp.m);
    prevRange = lp.m === 1 ? monthRange(lp.y - 1, 12) : monthRange(lp.y, lp.m - 1);
    label = `${MONTHS[lp.m - 1]} ${lp.y}`;
  } else {
    range = [`${lp.y}-01-01`, `${lp.y}-12-31`];
    prevRange = [`${lp.y - 1}-01-01`, `${lp.y - 1}-12-31`];
    label = String(lp.y);
  }
  const [txs, prev] = await Promise.all([store.list(...range), store.list(...prevRange)]);
  const cur = sums(txs), pv = sums(prev);
  let body;
  if (lp.mode === 'bulan') {
    const kats = byKey(txs, 'keluar', 'kategori');
    let acc = 0;
    const segs = kats.map(([, v], i) => { const a = acc; acc += v / cur.keluar * 100; return `${DONUT[i % DONUT.length]} ${a.toFixed(2)}% ${acc.toFixed(2)}%`; });
    body = `<div class="bg-surface-container-lowest rounded-lg p-space-lg shadow-md flex flex-col items-center gap-space-md">
<h2 class="self-start font-headline-sm text-headline-sm text-on-surface">Pengeluaran per Kategori</h2>
<div class="relative w-44 h-44 rounded-full" style="background:${cur.keluar ? `conic-gradient(${segs.join(',')})` : '#e7eeff'}"><div class="absolute inset-4 rounded-full bg-surface-container-lowest flex flex-col items-center justify-center"><span class="font-label-sm text-label-sm text-on-surface-variant">Total Keluar</span><span class="font-body-bold text-body-bold text-on-surface tnum">${rp(cur.keluar)}</span></div></div>
${cur.keluar ? `<div class="w-full flex flex-col gap-space-xxs" id="lp-rows">${breakdownHtml(txs, 'keluar', cur.keluar, true)}</div>` : '<p class="font-body-md text-body-md text-on-surface-variant">Belum ada pengeluaran di periode ini 🙂</p>'}
<span class="font-label-md text-label-md text-on-surface-variant">${vsHtml(cur.keluar, pv.keluar)}</span></div>
<div class="bg-surface-container-lowest rounded-lg p-space-lg shadow-md flex flex-col gap-space-sm">
<h2 class="font-headline-sm text-headline-sm text-on-surface">Pemasukan</h2>
${cur.masuk ? `<div class="flex flex-col gap-space-xxs">${breakdownHtml(txs, 'masuk', cur.masuk, false)}</div>` : '<p class="font-body-md text-body-md text-on-surface-variant">Belum ada pemasukan di periode ini 🙂</p>'}</div>`;
  } else {
    const cols = MONTHS_SHORT.map((mn, i) => ({ label: mn, full: MONTHS[i], ...sums(txs.filter((t) => +t.tanggal.slice(5, 7) === i + 1)), hot: today.slice(0, 7) === `${lp.y}-${pad(i + 1)}` }));
    const withData = cols.filter((c) => c.keluar > 0);
    const hemat = withData.length ? withData.reduce((a, c) => (c.keluar < a.keluar ? c : a)) : null;
    const boros = withData.length ? withData.reduce((a, c) => (c.keluar > a.keluar ? c : a)) : null;
    body = `<div class="bg-surface-container-lowest rounded-lg p-space-lg shadow-md flex flex-col gap-space-sm">
<div class="flex items-center justify-between"><h2 class="font-headline-sm text-headline-sm text-on-surface">Per bulan</h2>${legend}</div>
<div id="lp-bars">${barsHtml(cols)}</div><span id="lp-bar-label" class="font-label-sm text-label-sm text-on-surface-variant text-center tnum" hidden></span></div>
${summaryCard(cur)}
<div class="bg-surface-container-lowest rounded-lg p-space-lg shadow-md flex flex-col gap-space-xs">
<p class="font-label-lg text-label-lg text-on-surface">🌿 Bulan paling hemat: <span class="text-primary">${hemat ? `${hemat.full} (${rp(hemat.keluar)})` : '—'}</span></p>
<p class="font-label-lg text-label-lg text-on-surface">🔥 Bulan paling boros: <span class="text-secondary">${boros ? `${boros.full} (${rp(boros.keluar)})` : '—'}</span></p>
<span class="font-label-md text-label-md text-on-surface-variant">${vsHtml(cur.keluar, pv.keluar)}</span></div>`;
  }
  const el = $('view-laporan');
  el.innerHTML = `${segmented([['bulan', 'Bulan'], ['tahun', 'Tahun']], lp.mode, 'data-mode')}${stepper(label, 'lp', range[1] >= today)}${body}`;
  el.querySelectorAll('[data-mode]').forEach((b) => { b.onclick = () => { lp.mode = b.dataset.mode; render(); }; });
  const step = (n) => {
    if (lp.mode === 'bulan') { lp.m += n; if (lp.m > 12) { lp.m = 1; lp.y++; } if (lp.m < 1) { lp.m = 12; lp.y--; } } else lp.y += n;
    render();
  };
  $('lp-prev').onclick = () => step(-1);
  $('lp-next').onclick = () => step(1);
  const rows = $('lp-rows');
  if (rows) rows.onclick = (e) => { const b = e.target.closest('[data-kat]'); if (b && b.nextElementSibling) b.nextElementSibling.hidden = !b.nextElementSibling.hidden; };
  const bars = $('lp-bars');
  if (bars) bindBars(bars, $('lp-bar-label'), MONTHS_SHORT.map((mn, i) => ({ label: mn, full: MONTHS[i], ...sums(txs.filter((t) => +t.tanggal.slice(5, 7) === i + 1)) })));
}

// ---------- Catat sheet ----------
function openSheet(tx, jenis) {
  Object.assign(S, { tx: tx || null, jenis: tx ? tx.jenis : jenis || 'keluar', kat: tx ? tx.kategori : null, sub: tx ? tx.subkategori : null, sumber: tx ? tx.sumber : 'app' });
  $('sheet-title').textContent = tx ? 'Ubah Transaksi' : 'Catat Transaksi';
  $('nominal').value = tx ? rp(tx.jumlah) : '';
  $('catatan').value = tx ? tx.catatan : '';
  $('tanggal').value = tx ? tx.tanggal : todayIso();
  $('waktu').value = tx ? tx.waktu : nowHM();
  $('delete-btn').hidden = !tx;
  $('scan-hint').hidden = true;
  $('scan-progress').hidden = true;
  drawSheet();
  $('sheet').hidden = false;
  document.body.style.overflow = 'hidden';
  safe(() => tg.BackButton.show());
}
function drawSheet() {
  $('jenis-pills').querySelectorAll('[data-jenis]').forEach((b) => {
    const on = b.dataset.jenis === S.jenis;
    b.className = `chip justify-center ${on ? (S.jenis === 'masuk' ? 'bg-primary-fixed text-on-primary-fixed' : 'bg-secondary-fixed text-on-secondary-fixed') : 'bg-surface-container text-on-surface-variant'}`;
  });
  const active = cats.filter((c) => c.jenis === S.jenis && c.aktif !== 0);
  const kats = [...new Set(active.map((c) => c.kategori))];
  if (S.kat && !kats.includes(S.kat)) kats.push(S.kat); // a hidden leaf on an existing row stays selectable
  const chip = (attr, v, on) => `<button type="button" ${attr}="${esc(v)}" class="chip ${on ? 'bg-primary text-on-primary' : 'bg-surface-container text-on-surface'}">${esc(v)}</button>`;
  $('kat-chips').innerHTML = kats.map((k) => chip('data-kat', k, k === S.kat)).join('');
  const subs = active.filter((c) => c.kategori === S.kat).map((c) => c.subkategori);
  if (S.tx && S.kat === S.tx.kategori && !subs.includes(S.tx.subkategori)) subs.push(S.tx.subkategori);
  if (subs.length === 1) S.sub = subs[0];
  $('sub-wrap').hidden = !S.kat;
  $('sub-chips').innerHTML = subs.map((s) => chip('data-sub', s, s === S.sub)).join('');
  $('save-btn').disabled = !(S.kat && S.sub);
}
function closeSheets() {
  $('sheet').hidden = true;
  $('info-sheet').hidden = true;
  document.body.style.overflow = '';
  safe(() => tg.BackButton.hide());
  stopOcr();
}
function formatNominal(e) { // live "Rp 50.000"; letters (50rb) are left alone until blur
  const raw = e.target.value.replace(/^Rp\s*/i, '');
  if (/^[\d.,\s]*$/.test(raw)) {
    const digits = raw.replace(/\D/g, '');
    e.target.value = digits ? rp(+digits) : '';
  } else if (e.type === 'blur') {
    const r = parseAmount(raw);
    e.target.value = r && r.jumlah ? rp(r.jumlah) : '';
  }
}
async function save() {
  const r = parseAmount($('nominal').value);
  if (!r || !r.jumlah || r.jumlah < 1) return toast('Isi nominalnya dulu ya 🙂');
  const tx = { jenis: S.jenis, jumlah: r.jumlah, kategori: S.kat, subkategori: S.sub, catatan: $('catatan').value.trim().slice(0, 80),
    tanggal: $('tanggal').value || todayIso(), waktu: ($('waktu').value || '').slice(0, 5), sumber: S.sumber };
  const btn = $('save-btn');
  btn.disabled = true;
  try {
    if (S.tx) await store.update(S.tx.id, tx); else await store.add(tx);
    safe(() => tg.HapticFeedback.notificationOccurred('success'));
    toast('✅ Tersimpan');
    closeSheets();
    render();
  } catch (e) {
    fail(e);
  } finally {
    btn.disabled = false;
  }
}
function del() {
  const go = (ok) => { if (ok) store.remove(S.tx.id).then(() => { toast('🗑️ Dihapus'); closeSheets(); render(); }).catch(fail); };
  if (tg && tg.isVersionAtLeast('6.2')) tg.showConfirm('Hapus catatan ini?', go); else go(confirm('Hapus catatan ini?'));
}
async function scan(e) {
  const file = e.target.files[0];
  e.target.value = '';
  if (!file) return;
  const prog = $('scan-progress');
  prog.hidden = false;
  prog.textContent = 'Menyiapkan pembaca struk…';
  $('scan-hint').hidden = true;
  try {
    const r = await scanReceipt(file, todayIso(), (msg) => { prog.textContent = msg; });
    if (r.jumlah) $('nominal').value = rp(r.jumlah);
    $('catatan').value = r.catatan;
    $('tanggal').value = r.tanggal;
    if (r.waktu) $('waktu').value = r.waktu;
    S.jenis = 'keluar';
    S.sumber = 'struk';
    if (r.kategori) { S.kat = r.kategori; S.sub = r.subkategori; }
    drawSheet();
    prog.textContent = r.jumlah ? 'Struk terbaca ✅' : 'Totalnya belum ketemu, isi manual ya 🙏';
    $('scan-hint').hidden = r.confidence !== 'low';
  } catch (err) {
    prog.hidden = true;
    toast(err.message || 'Struk tidak terbaca');
  }
}

// ---------- guest info sheet ----------
function openInfo() {
  $('remind-toggle').checked = safe(() => localStorage.getItem('ff_remind')) === '1';
  $('info-sheet').hidden = false;
  safe(() => tg.BackButton.show());
}
async function setRemind(e) {
  const on = e.target.checked;
  try {
    const r = await api('POST', '/api/remind', { on });
    if (on && !r.ok) {
      e.target.checked = false;
      toast('Tekan Start di chat @finnfinnnn_bot dulu ya 🙂');
      return;
    }
    safe(() => localStorage.setItem('ff_remind', on ? '1' : '0'));
    toast(on ? '🔔 Pengingat aktif' : 'Pengingat dimatikan');
  } catch (err) {
    e.target.checked = !on;
    fail(err);
  }
}

// ---------- router / boot ----------
function route() {
  const h = (location.hash || '#beranda').slice(1).split(/[&?]/)[0]; // Telegram appends &tgWebAppData=… to the fragment
  const catat = h === 'catat'; // deep link: open the sheet on Beranda
  view = VIEWS.includes(h) ? h : 'beranda';
  for (const v of VIEWS) $('view-' + v).hidden = v !== view;
  const active = $('nav').dataset.activeClasses.split(' ');
  $('nav').querySelectorAll('[data-path]').forEach((a) => {
    const on = a.dataset.path === view;
    a.classList.remove(...active, 'text-on-surface-variant');
    a.classList.add(...(on ? active : ['text-on-surface-variant']));
    if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
  });
  $('fab').hidden = view !== 'arus-kas';
  closeSheets();
  window.scrollTo(0, 0);
  render();
  if (catat) { history.replaceState(null, '', '#beranda'); openSheet(null, 'keluar'); }
}
async function render() {
  try {
    if (view === 'beranda') await renderBeranda();
    else if (view === 'arus-kas') await renderArusKas();
    else if (view === 'laporan') await renderLaporan();
  } catch (e) {
    fail(e);
  }
}
function wire() {
  $('toggleBalanceBtn').onclick = () => {
    const hide = $('balanceHidden').classList.contains('hidden');
    $('balanceText').classList.toggle('hidden', hide);
    $('balanceHidden').classList.toggle('hidden', !hide);
    $('eyeIcon').textContent = hide ? 'visibility_off' : 'visibility';
    safe(() => localStorage.setItem('ff_hide', hide ? '1' : '0'));
  };
  if (safe(() => localStorage.getItem('ff_hide')) === '1') $('toggleBalanceBtn').onclick();
  $('btn-catat').onclick = () => openSheet(null, 'keluar');
  $('fab').onclick = () => openSheet(null, 'keluar');
  $('btn-history').onclick = $('see-all').onclick = () => { location.hash = '#arus-kas'; };
  $('quick').onclick = (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    if (b.dataset.act === 'segera') toast('Segera hadir di versi berikutnya ✨'); else openSheet(null, b.dataset.act);
  };
  document.querySelectorAll('[data-close]').forEach((el) => { el.onclick = closeSheets; });
  $('jenis-pills').onclick = (e) => { const b = e.target.closest('[data-jenis]'); if (b) { S.jenis = b.dataset.jenis; S.kat = S.sub = null; drawSheet(); } };
  $('kat-chips').onclick = (e) => { const b = e.target.closest('[data-kat]'); if (b) { S.kat = b.dataset.kat; S.sub = null; drawSheet(); } };
  $('sub-chips').onclick = (e) => { const b = e.target.closest('[data-sub]'); if (b) { S.sub = b.dataset.sub; drawSheet(); } };
  $('nominal').addEventListener('input', formatNominal);
  $('nominal').addEventListener('blur', formatNominal);
  $('save-btn').onclick = save;
  $('delete-btn').onclick = del;
  $('scan-btn').onclick = () => $('scan-file').click();
  $('scan-file').onchange = scan;
  $('guest-banner').onclick = openInfo;
  $('remind-toggle').onchange = setRemind;
  document.addEventListener('visibilitychange', () => { if (document.hidden) stopOcr(); });
  window.addEventListener('hashchange', route);
  if (tg) tg.BackButton.onClick(closeSheets);
}
async function boot() {
  if (tg) safe(() => { tg.ready(); tg.expand(); tg.setHeaderColor('#f9f9ff'); tg.setBackgroundColor('#f9f9ff'); if (tg.isVersionAtLeast('7.7')) tg.disableVerticalSwipes(); });
  const inTelegram = !!(tg && tg.initData);
  const tgUser = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
  let fromServer = true;
  try {
    me = await api('GET', '/api/me');
  } catch (e) {
    fromServer = false;
    if (e.status === 401) return screen(inTelegram ? e.message : 'Buka lewat Telegram ya 🙂');
    if (e.status >= 400 && e.status < 500) return screen(e.message);
    if (safe(() => localStorage.getItem('ff_mode')) === 'guest' && inTelegram) me = { mode: 'guest', nama: tgUser.first_name || '' };
    else return screen('Server tidak terjangkau — coba lagi 🙏', 'Coba lagi', () => location.reload());
  }
  if (fromServer) safe(() => localStorage.setItem('ff_mode', me.mode));
  if (me.mode === 'owner') store = new ServerStore();
  else {
    if (!inTelegram) return screen('Buka lewat Telegram ya 🙂');
    if (!tg.isVersionAtLeast('6.9')) return screen('Perbarui aplikasi Telegram-mu untuk memakai Finn Finn 🙏');
    store = new CloudStore(tg.CloudStorage, toast);
    $('guest-banner').hidden = false;
  }
  const name = me.nama || tgUser.first_name || 'Kamu';
  $('greet').textContent = `Halo, ${name}! 👋`;
  if (tgUser.photo_url) { $('avatar').src = tgUser.photo_url; $('avatar').hidden = false; $('avatar-initials').hidden = true; }
  else $('avatar-initials').textContent = (name[0] + (tgUser.last_name || '')[0]).toUpperCase().replace('UNDEFINED', '');
  try {
    await store.init();
    cats = await store.categories();
  } catch (e) {
    return e.status === 401 ? fail(e) : screen(e.message || 'Terjadi kesalahan', 'Coba lagi', () => location.reload());
  }
  const today = todayIso();
  ak.anchor = today;
  lp.y = +today.slice(0, 4);
  lp.m = +today.slice(5, 7);
  wire();
  route();
}
boot();
