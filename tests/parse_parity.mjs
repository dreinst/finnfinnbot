// Parity check for web/parse.js against the Python expectations in tests/test_parse.py + the receipt fixtures.
// Run: node tests/parse_parity.mjs  (exit code 1 on any mismatch)
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { guessJenis, guessJenisStruk, guessKategori, parseAmount, parseReceipt, parseText } from '../web/parse.js';

const TODAY = '2026-09-06';
const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const FIX = join(ROOT, 'tests', 'fixtures', 'receipts');
let failed = 0;

function check(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g !== w) {
    failed++;
    console.log(`FAIL ${label}\n  got  ${g}\n  want ${w}`);
  }
}
const pick = (obj, keys) => Object.fromEntries(keys.map((k) => [k, obj[k]]));

// text → [jumlah, ambiguous, error]  (tests/test_parse.py AMOUNTS)
const AMOUNTS = [
  ['50000 kopi', 50000, false, null], ['gaji 7.500.000', 7500000, false, null], ['bensin 100rb', 100000, false, null],
  ['7,5jt bonus', 7500000, false, null], ['Rp 12,500 parkir', 12500, false, null], ['12.500,00', 12500, false, null],
  ['+200k refund', 200000, false, null], ['kemarin 35000 nasi padang', 35000, false, null], ['3/9 pulsa 50k', 50000, false, null],
  ['beli 2 kopi 30rb', 30000, false, null], ['50 kopi', 50, true, null], ['5 kopi', 5, false, 'range'],
  ['1.5m saham', 1500000, false, null], ['2jt', 2000000, false, null], ['Rp12.500', 12500, false, null],
  ['rp. 25.000 makan siang', 25000, false, null], ['IDR 150000', 150000, false, null], ['50 000 bensin', 50000, false, null],
  ['1 juta', 1000000, false, null], ['250 ribu belanja', 250000, false, null], ['100k', 100000, false, null],
  ['10.000.000 thr', 10000000, false, null], ['12,5rb', 12500, false, null], ['kopi 20.000', 20000, false, null],
  ['999', 999, true, null], ['1000', 1000, false, null], ['Rp 500 parkir', 500, false, null],
  ['150000000000', 150000000000, false, 'range'], ['1.234.567', 1234567, false, null], ['2 x kopi 15rb', 15000, false, null],
  ['makan 1.500', 1500, false, null], ['Rp 50 kopi', 50, false, 'range'], ['beli 3 100rb', 100000, false, null],
  ['bayar 2 150rb', 150000, false, null],
];
for (const [text, jumlah, ambiguous, error] of AMOUNTS) {
  const r = parseAmount(text);
  check(`amount ${JSON.stringify(text)}`, [r.jumlah, r.ambiguous, r.error], [jumlah, ambiguous, error]);
}
for (const text of ['halo', 'kopi', '']) check(`no amount ${JSON.stringify(text)}`, parseAmount(text), null);
{
  const r = parseAmount('20000 kopi 15000 roti');
  check('multiple', [r.jumlah, r.multiple], [20000, true]);
  check('multiple count-price', parseAmount('beli 2 kopi 30rb').multiple, false);
}

// text → expected subset of parseText()  (tests/test_parse.py TextTest)
const TEXT = [
  ['50000 kopi', { jumlah: 50000, catatan: 'Kopi', jenis: 'keluar', tanggal: '2026-09-06', kategori: 'Makanan & Minuman',
    subkategori: 'Makan di luar', error: null }],
  ['halo', { jumlah: null, error: 'kosong', catatan: 'Halo' }],
  ['5 kopi', { jumlah: 5, error: 'range' }],
  ['50 kopi', { jumlah: 50, ambiguous: true, catatan: 'Kopi' }],
  ['gaji 7.500.000', { jenis: 'masuk', kategori: 'Gaji', catatan: 'Gaji' }],
  ['7,5jt bonus', { jenis: 'masuk', kategori: 'Bonus', subkategori: 'Umum' }],
  ['+200k refund', { jenis: 'masuk', kategori: 'Lainnya', catatan: 'Refund' }],
  ['dividen 250rb', { jenis: 'masuk', kategori: 'Investasi' }],
  ['masuk 1jt', { jenis: 'masuk', kategori: 'Lainnya', catatan: '' }],
  ['pemasukan 1jt', { jenis: 'masuk', kategori: 'Lainnya', catatan: '' }],
  ['31/12/2025 thr 5jt', { kategori: 'Bonus', tanggal: '2025-12-31' }],
  ['kopi +20rb', { jenis: 'keluar' }],
  ['kemarin 35000 nasi padang', { tanggal: '2026-09-05', catatan: 'Nasi padang', subkategori: 'Makan di luar' }],
  ['3/9 pulsa 50k', { tanggal: '2026-09-03', catatan: 'Pulsa', subkategori: 'Pulsa' }],
  ['31-12-25 thr 5jt', { tanggal: '2025-12-31' }],
  ['7/9 kopi 20rb', { tanggal: '2026-09-07' }],
  ['10/9 kopi 20rb', { tanggal: '2026-09-06' }],
  ['kopi 20rb', { tanggal: '2026-09-06' }],
  ['beli 2 kopi 30rb', { catatan: 'Beli 2 kopi' }],
  ['beli 3 100rb', { catatan: 'Beli 3' }],
  ['12.500,00', { catatan: '' }],
  ['Rp 12,500 parkir', { catatan: 'Parkir' }],
  ['gojek ke kantor 25rb', { catatan: 'Gojek ke kantor', kategori: 'Transportasi', subkategori: 'Ojek-Taxi' }],
  ['kopi - 20rb', { catatan: 'Kopi' }],
  ['   makan   siang   25rb  ', { catatan: 'Makan siang' }],
  ['bensin 100rb', { kategori: 'Transportasi', subkategori: 'BBM' }],
  ['indomaret 87500', { kategori: 'Makanan & Minuman', subkategori: 'Groceries' }],
  ['token listrik 100rb', { kategori: 'Tagihan', subkategori: 'Listrik' }],
  ['wifi 300rb', { kategori: 'Tagihan', subkategori: 'Internet' }],
  ['netflix 54000', { kategori: 'Hiburan', subkategori: 'Umum' }],
  ['obat apotek 45rb', { kategori: 'Kesehatan', subkategori: 'Umum' }],
  ['beli baju 150rb', { kategori: 'Belanja', subkategori: 'Pakaian' }],
  ['charger hp 80rb', { kategori: 'Belanja', subkategori: 'Elektronik' }],
  ['galon 20rb', { kategori: 'Rumah Tangga', subkategori: 'Umum' }],
  ['bayar spp 500rb', { kategori: 'Pendidikan', subkategori: 'Umum' }],
  ['nasi padang 35000', { kategori: 'Makanan & Minuman', subkategori: 'Makan di luar' }],
  ['botol 50rb', { kategori: null, subkategori: null }],
  ['transfer 50rb', { kategori: null, subkategori: null }],
  ['kertas 10rb', { kategori: null, subkategori: null }],
  ['kopinya 20rb', { subkategori: 'Makan di luar' }],
  ['bensinnya 100rb', { subkategori: 'BBM' }],
  ['beli makanan 50rb', { subkategori: 'Makan di luar' }],
  ['pulsanya 50rb', { subkategori: 'Pulsa' }],
  ['parkirnya 5rb', { subkategori: 'Parkir' }],
  ['obatnya 30rb', { kategori: 'Kesehatan' }],
  ['gojekku 20rb', { subkategori: 'Ojek-Taxi' }],
];
for (const [text, want] of TEXT) check(`text ${JSON.stringify(text)}`, pick(parseText(text, TODAY), Object.keys(want)), want);
check('catatan max 80', parseText('x'.repeat(100) + ' 20rb', TODAY).catatan.length, 80);
check('guessJenis +', guessJenis('+ 200rb'), 'masuk');
check('guessJenis kopi', guessJenis('kopi 20rb'), 'keluar');
check('guessKategori kfc', guessKategori('kfc'), ['Makanan & Minuman', 'Makan di luar']);
check('guessKategori masuk', guessKategori('apa saja', 'masuk'), ['Lainnya', 'Umum']);

// receipt fixtures: NN.txt lines vs NN.json expectations ("merchant" → catatan)
const fixtures = readdirSync(FIX).filter((f) => f.endsWith('.json')).sort();
if (fixtures.length < 6) check('fixture count', fixtures.length, '>= 6');
for (const f of fixtures) {
  const exp = JSON.parse(readFileSync(join(FIX, f), 'utf8'));
  const lines = readFileSync(join(FIX, f.replace('.json', '.txt')), 'utf8').split(/\r?\n/);
  const got = parseReceipt(lines, exp.today);
  for (const [k, v] of Object.entries(exp)) {
    if (k !== 'today') check(`fixture ${f} ${k}`, got[k === 'merchant' ? 'catatan' : k], v);
  }
  check(`fixture ${f} jenis`, got.jenis, 'keluar');
}
check('guessJenisStruk terima kasih', guessJenisStruk('TERIMA KASIH ATAS KUNJUNGAN ANDA'), 'keluar');
// an INVOICE line + a LUNAS paid-stamp alone is normal on ordinary purchase receipts too — must not flip to masuk
check('guessJenisStruk invoice lunas alone', guessJenisStruk('NO. INVOICE: 1234567\nSTATUS: LUNAS\nTOTAL 87.500'), 'keluar');
for (const text of ['BUKTI TRANSFER\nTransfer Masuk\nDari: PT Contoh\nTOTAL 5.000.000', 'Slip Gaji Bulan September\nGaji Pokok 7.500.000',
                    'Pembayaran Diterima\nInvoice #123 Lunas\nRp 1.200.000']) {
  check(`guessJenisStruk masuk ${JSON.stringify(text)}`, guessJenisStruk(text), 'masuk');
}
{
  const r = parseReceipt(['BUKTI TRANSFER', 'Transfer Masuk', 'Dari: PT Contoh', 'TOTAL 5.000.000'], TODAY);
  check('receipt income proof', [r.jenis, r.jumlah], ['masuk', 5000000]);
}
{
  const r = parseReceipt(['', '   '], TODAY);
  check('receipt empty', [r.jumlah, r.confidence, r.tanggal, r.catatan], [null, 'low', '2026-09-06', 'Struk']);
  const s = parseReceipt(['TOKO MAJU', 'TOTAL', '45.000', 'TUNAI', '50.000'], TODAY);
  check('receipt split column', [s.jumlah, s.confidence], [45000, 'high']);
  const c = parseReceipt(['TOKO MAJU', 'ITEM A 10.000', 'TOTAL:87.500', 'TUNAI:100.000'], TODAY);
  check('receipt no space after colon', [c.jumlah, c.confidence], [87500, 'high']);
  const o = parseReceipt(['TOKO MAJU', '01/01/2020', 'TOTAL 45.000'], TODAY);
  check('receipt old date ignored', [o.tanggal, o.waktu], ['2026-09-06', '']);
  check('receipt time same line', parseReceipt(['06/09/2026 19.42', 'TOTAL 45.000'], TODAY).waktu, '19:42');
  check('receipt time next line', parseReceipt(['06/09/2026', '19:42', 'TOTAL 45.000'], TODAY).waktu, '19:42');
  check('receipt price is not time', parseReceipt(['06/09/2026', 'TOTAL 12.50'], TODAY).waktu, '');
  check('receipt merchant title', parseReceipt(['WARUNG BU TINI', 'TOTAL 45.000'], TODAY).catatan, 'Warung Bu Tini');
  check('receipt time after colon', parseReceipt(['06/09/2026', 'Jam:19.42', 'TOTAL 45.000'], TODAY).waktu, '');
  check('text date at start', parseText('3/9 kopi 20rb', TODAY).catatan, 'Kopi');
  // misread TOTAL (tests/test_parse.py test_fallback_skips_hotline_and_receipt_number): hotline / receipt no. never win the fallback
  const read = (n) => readFileSync(join(FIX, n), 'utf8').split(/\r?\n/);
  const f2 = parseReceipt(read('02.txt').map((l) => (l === 'TOTAL 82.300' ? 'T0TAL 82.300' : l)), TODAY);
  check('receipt misread total 02', [f2.jumlah, f2.confidence], [82300, 'low']);
  check('receipt misread total 01', parseReceipt(read('01.txt').map((l) => (l === 'TOTAL : 87.500' ? 'T0TAL : 87.500' : l)), TODAY).jumlah !== 1234567, true);
}

// iOS/Safari < 16.4 floor: no regex lookbehind, no logical-assignment operators anywhere in the Mini App
for (const f of readdirSync(join(ROOT, 'web')).filter((f) => f.endsWith('.js'))) {
  check(`syntax floor ${f}`, /\(\?<[=!]|\|\|=|&&=|\?\?=/.test(readFileSync(join(ROOT, 'web', f), 'utf8')), false);
}

if (failed) {
  console.log(`${failed} mismatch(es)`);
  process.exit(1);
}
console.log(`parse.js parity OK (${AMOUNTS.length} amounts, ${TEXT.length} texts, ${fixtures.length} receipts)`);
