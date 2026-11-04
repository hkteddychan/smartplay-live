/**
 * make-splash.mjs — 把 preview.png 轉成 ESP32-CYD TFT 開機畫面資料
 *
 * 流程：PNG 解碼（純 Node，zlib inflate）→ 240×320 cover 裁切縮放
 *      → RGB565 → RLE 壓縮 → 產生 firmware/esp32_cyd_controller/splash_data.h
 *
 * 格式：每筆 3 bytes = [count(1..255), colorHi, colorLo]，RGB565 高位元組在前。
 * 用法：node tools/make-splash.mjs
 */
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs';
import { inflateSync } from 'node:zlib';
import { dirname, join, resolve, basename } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const outDir = join(root, 'firmware', 'esp32_cyd_controller');
const outPath = join(outDir, 'splash_data.h');

const TARGET_W = 240;
const TARGET_H = 320;

/* 來源圖：--input 指定 > assets/hello.png（自己的照片）> preview.png */
const argInput = process.argv[2];
const candidates = argInput
  ? [resolve(process.cwd(), argInput)]
  : [join(root, 'assets', 'hello.png'), join(root, 'preview.png')];
const inputPath = candidates.find((p) => existsSync(p));
if (!inputPath) {
  console.error('找不到來源圖片，請確認下列檔案之一存在：');
  for (const p of candidates) console.error('  - ' + p);
  process.exit(1);
}

/* ---------- PNG decode (8-bit, non-interlaced) ---------- */
function decodePng(buf) {
  if (buf.readUInt32BE(0) !== 0x89504e47 || buf.readUInt32BE(4) !== 0x0d0a1a0a) {
    throw new Error('not a PNG file');
  }
  let pos = 8;
  let ihdr = null;
  const idat = [];
  let palette = null;
  while (pos + 8 <= buf.length) {
    const len = buf.readUInt32BE(pos);
    const type = buf.toString('ascii', pos + 4, pos + 8);
    const data = buf.subarray(pos + 8, pos + 8 + len);
    pos += 12 + len;
    if (type === 'IHDR') {
      ihdr = {
        w: data.readUInt32BE(0),
        h: data.readUInt32BE(4),
        bit: data[8],
        color: data[9],
        interlace: data[12]
      };
    } else if (type === 'PLTE') {
      palette = Buffer.from(data);
    } else if (type === 'IDAT') {
      idat.push(data);
    } else if (type === 'IEND') {
      break;
    }
  }
  if (!ihdr) throw new Error('IHDR chunk missing');
  if (ihdr.interlace !== 0) throw new Error('interlaced PNG is not supported');
  if (ihdr.bit !== 8) throw new Error(`bit depth ${ihdr.bit} is not supported (need 8)`);
  const channels = { 0: 1, 2: 3, 3: 1, 4: 2, 6: 4 }[ihdr.color];
  if (!channels) throw new Error(`color type ${ihdr.color} is not supported`);

  const raw = inflateSync(Buffer.concat(idat));
  const { w, h } = ihdr;
  const stride = w * channels;
  const px = Buffer.alloc(h * stride);
  let rp = 0;
  let prev = Buffer.alloc(stride);
  for (let y = 0; y < h; y++) {
    const filter = raw[rp++];
    const line = raw.subarray(rp, rp + stride);
    rp += stride;
    if (rp > raw.length) throw new Error('truncated PNG pixel data');
    const cur = px.subarray(y * stride, (y + 1) * stride);
    for (let x = 0; x < stride; x++) {
      const a = x >= channels ? cur[x - channels] : 0;
      const b = prev[x];
      const c = x >= channels ? prev[x - channels] : 0;
      let v = line[x];
      if (filter === 1) v += a;
      else if (filter === 2) v += b;
      else if (filter === 3) v += (a + b) >> 1;
      else if (filter === 4) {
        const p = a + b - c;
        const pa = Math.abs(p - a);
        const pb = Math.abs(p - b);
        const pc = Math.abs(p - c);
        v += pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
      }
      cur[x] = v & 0xff;
    }
    prev = cur;
  }

  const getRgb = (x, y) => {
    const i = y * stride + x * channels;
    if (ihdr.color === 2) return [px[i], px[i + 1], px[i + 2]];
    if (ihdr.color === 6) return [px[i], px[i + 1], px[i + 2]];
    if (ihdr.color === 0) return [px[i], px[i], px[i]];
    if (ihdr.color === 4) return [px[i], px[i], px[i]];
    if (ihdr.color === 3) {
      const idx = px[i] * 3;
      return [palette[idx], palette[idx + 1], palette[idx + 2]];
    }
    throw new Error(`unsupported color type ${ihdr.color}`);
  };
  return { w, h, getRgb };
}

/* ---------- cover-crop resize to 240×320 ---------- */
function resizeCover(img, tw, th) {
  const scale = Math.max(tw / img.w, th / img.h);
  const sw = Math.min(img.w, Math.round(tw / scale));
  const sh = Math.min(img.h, Math.round(th / scale));
  const sx = Math.floor((img.w - sw) / 2);
  const sy = Math.floor((img.h - sh) / 2);
  const out = new Uint16Array(tw * th);
  for (let ty = 0; ty < th; ty++) {
    const y0 = sy + Math.floor((ty * sh) / th);
    const y1 = sy + Math.max(y0 - sy + 1, Math.floor(((ty + 1) * sh) / th));
    for (let tx = 0; tx < tw; tx++) {
      const x0 = sx + Math.floor((tx * sw) / tw);
      const x1 = sx + Math.max(x0 - sx + 1, Math.floor(((tx + 1) * sw) / tw));
      let r = 0, g = 0, b = 0, n = 0;
      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const [rr, gg, bb] = img.getRgb(x, y);
          r += rr; g += gg; b += bb; n++;
        }
      }
      const R = Math.round(r / n / 255 * 31);
      const G = Math.round(g / n / 255 * 63);
      const B = Math.round(b / n / 255 * 31);
      out[ty * tw + tx] = (R << 11) | (G << 5) | B;
    }
  }
  return out;
}

/* ---------- RLE encode ---------- */
function rleEncode(pixels) {
  const runs = [];
  let i = 0;
  while (i < pixels.length) {
    const color = pixels[i];
    let count = 1;
    while (count < 255 && i + count < pixels.length && pixels[i + count] === color) count++;
    runs.push([count, color]);
    i += count;
  }
  return runs;
}

/* ---------- main ---------- */
const png = decodePng(readFileSync(inputPath));
const pixels = resizeCover(png, TARGET_W, TARGET_H);
const runs = rleEncode(pixels);
const bytes = runs.length * 3;

const lines = runs.map(([count, color]) => `0x${count.toString(16).padStart(2, '0').toUpperCase()},0x${color.toString(16).padStart(4, '0').toUpperCase()},`);
const header = `// ============================================================
// splash_data.h — 自動產生，請勿手動編輯
// 來源：${basename(inputPath)} (${png.w}x${png.h}) → ${TARGET_W}x${TARGET_H} RGB565 RLE
// 產生：node tools/make-splash.mjs
// 格式：每筆 3 bytes = [count(1..255), colorHi, colorLo]
// ============================================================
#ifndef SPLASH_DATA_H
#define SPLASH_DATA_H

#include <Arduino.h>

#define SPLASH_W ${TARGET_W}
#define SPLASH_H ${TARGET_H}
#define SPLASH_RUNS ${runs.length}
#define SPLASH_RLE_LEN (SPLASH_RUNS * 3)

static const uint8_t splashRle[] PROGMEM = {
${lines.join('\n')}
};

#endif // SPLASH_DATA_H
`;

mkdirSync(outDir, { recursive: true });
writeFileSync(outPath, header, 'utf8');
console.log(`${basename(inputPath)} ${png.w}x${png.h} -> ${TARGET_W}x${TARGET_H} RGB565 RLE`);
console.log(`runs: ${runs.length}, bytes: ${bytes} (${(bytes / 1024).toFixed(1)} KB, raw ${(TARGET_W * TARGET_H * 2 / 1024).toFixed(1)} KB)`);
console.log(`written: ${outPath}`);
