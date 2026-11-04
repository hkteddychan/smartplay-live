/**
 * render-splash-preview.mjs — 把 splash_data.h 的 RGB565 RLE 還原成 PNG
 * 讓你在燒錄前就能看到 ESP32-CYD 開機會顯示的畫面。
 *
 * 用法：node tools/render-splash-preview.mjs
 * 輸出：docs/splash-preview.png（2 倍放大 480×640）
 */
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { deflateSync } from 'node:zlib';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const headerPath = join(root, 'firmware', 'esp32_cyd_controller', 'splash_data.h');
const outPath = join(root, 'docs', 'splash-preview.png');
const SCALE = 2;

/* ---------- 解析 splash_data.h ---------- */
const header = readFileSync(headerPath, 'utf8');
const w = Number(header.match(/#define\s+SPLASH_W\s+(\d+)/)[1]);
const h = Number(header.match(/#define\s+SPLASH_H\s+(\d+)/)[1]);
const body = header.match(/splashRle\[\]\s*PROGMEM\s*=\s*\{([\s\S]*?)\};/);
if (!body) throw new Error('splashRle array not found');
const bytes = [];
for (const m of body[1].matchAll(/0x([0-9A-Fa-f]{2}),0x([0-9A-Fa-f]{4}),/g)) {
  bytes.push(parseInt(m[1], 16), parseInt(m[2], 16) >> 8, parseInt(m[2], 16) & 0xff);
}

/* ---------- RLE -> RGB565 -> RGB888 ---------- */
const rgb = Buffer.alloc(w * h * 3);
let p = 0;
let i = 0;
while (i < w * h) {
  const count = bytes[p++];
  const color = (bytes[p] << 8) | bytes[p + 1];
  p += 2;
  const r = ((color >> 11) & 0x1f) * 255 / 31;
  const g = ((color >> 5) & 0x3f) * 255 / 63;
  const b = (color & 0x1f) * 255 / 31;
  for (let n = 0; n < count && i < w * h; n++, i++) {
    rgb[i * 3] = r; rgb[i * 3 + 1] = g; rgb[i * 3 + 2] = b;
  }
}
if (i !== w * h) throw new Error(`RLE covers ${i}/${w * h} pixels`);

/* ---------- 縮放到目標尺寸（最近鄰） ---------- */
const ow = w * SCALE, oh = h * SCALE;
const raw = Buffer.alloc(oh * (ow * 3 + 1));
for (let y = 0; y < oh; y++) {
  const sy = Math.floor(y / SCALE);
  raw[y * (ow * 3 + 1)] = 0; // filter: none
  for (let x = 0; x < ow; x++) {
    const sx = Math.floor(x / SCALE);
    const s = (sy * w + sx) * 3;
    const d = y * (ow * 3 + 1) + 1 + x * 3;
    raw[d] = rgb[s]; raw[d + 1] = rgb[s + 1]; raw[d + 2] = rgb[s + 2];
  }
}

/* ---------- PNG 編碼 ---------- */
const CRC_TABLE = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c >>> 0;
  }
  return t;
})();
const crc32 = (buf) => {
  let c = 0xffffffff;
  for (const b of buf) c = CRC_TABLE[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};
const chunk = (type, data) => {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const typed = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(typed));
  return Buffer.concat([len, typed, crc]);
};
const ihdr = Buffer.alloc(13);
ihdr.writeUInt32BE(ow, 0);
ihdr.writeUInt32BE(oh, 4);
ihdr[8] = 8;  // bit depth
ihdr[9] = 2;  // color type: truecolor RGB
const png = Buffer.concat([
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
  chunk('IHDR', ihdr),
  chunk('IDAT', deflateSync(raw, { level: 9 })),
  chunk('IEND', Buffer.alloc(0))
]);

mkdirSync(join(root, 'docs'), { recursive: true });
writeFileSync(outPath, png);
console.log(`splash preview: ${ow}x${oh} -> ${outPath} (${(png.length / 1024).toFixed(1)} KB)`);
