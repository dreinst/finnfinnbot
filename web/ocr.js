// In-browser receipt OCR: tesseract.js (jsDelivr) + self-hosted ind/eng data; the photo never leaves the device.
import { parseReceipt } from './parse.js';

const CDN = 'https://cdn.jsdelivr.net/npm/tesseract.js@7.0.0/dist/tesseract.min.js';
let loading = null, worker = null;

function loadScript() {
  if (!loading) loading = new Promise((res, rej) => {
    if (window.Tesseract) return res();
    const s = document.createElement('script');
    s.src = CDN;
    s.onload = res;
    s.onerror = () => { loading = null; rej(new Error('Gagal memuat pembaca struk — cek koneksi')); };
    document.head.append(s);
  });
  return loading;
}

async function toCanvas(file) { // EXIF-upright (the default; the option name is rejected by older WebKit), long side ≤ 1600 px, grayscale
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, 1600 / Math.max(bmp.width, bmp.height));
  const c = document.createElement('canvas');
  c.width = Math.round(bmp.width * k);
  c.height = Math.round(bmp.height * k);
  const ctx = c.getContext('2d');
  ctx.drawImage(bmp, 0, 0, c.width, c.height);
  bmp.close();
  const img = ctx.getImageData(0, 0, c.width, c.height), d = img.data;
  for (let i = 0; i < d.length; i += 4) d[i] = d[i + 1] = d[i + 2] = (d[i] * 299 + d[i + 1] * 587 + d[i + 2] * 114) / 1000;
  ctx.putImageData(img, 0, 0);
  return c;
}

export async function scanReceipt(file, todayIso, onProgress) {
  if (file.size > 10 * 1024 * 1024) throw new Error('Foto terlalu besar (maks 10 MB)');
  await loadScript();
  const canvas = await toCanvas(file);
  if (!worker) {
    onProgress('Memuat bahasa struk…');
    worker = await Tesseract.createWorker(['ind', 'eng'], 1, {
      langPath: '/static/tessdata', gzip: true,
      logger: (m) => { if (m.status === 'recognizing text') onProgress(`Membaca struk… ${Math.round(m.progress * 100)} %`); },
    });
    await worker.setParameters({ tessedit_pageseg_mode: '4', preserve_interword_spaces: '1' });
  }
  const { data } = await worker.recognize(canvas, {}, { blocks: true });
  const lines = [];
  for (const b of data.blocks || []) for (const p of b.paragraphs) for (const l of p.lines) if (l.confidence >= 40) lines.push(l.text.trim());
  return parseReceipt(lines, todayIso);
}

export async function stopOcr() {
  const w = worker;
  worker = null;
  if (w) await w.terminate().catch(() => {});
}
