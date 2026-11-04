/**
 * cdp-driver.mjs — 用系統 Edge（puppeteer-core）驅動深度測試
 *
 * 1. 開啟 ?debug=1&agentWs=... 的遊戲頁
 * 2. 等 __NEON_SERPENT_DEBUG__ 就緒後安裝 tick driver（定時 tick 推進模擬）
 * 3. 輪詢 /__results：suite 完成後 reload 頁面（觸發 T17 重連測試）
 * 4. reconnectTest 完成後關閉瀏覽器離開
 */
import puppeteer from 'puppeteer-core';
import { accessSync } from 'node:fs';
import { writeFile } from 'node:fs/promises';

const EDGE_PATHS = [
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
];
const GAME_URL = 'http://127.0.0.1:8899/?debug=1&agentWs=ws://127.0.0.1:8899';
const RESULTS_URL = 'http://127.0.0.1:8899/__results';
const HEADLESS = !process.argv.includes('--headed');

const log = (...m) => console.log(new Date().toISOString().slice(11, 23), '[driver]', ...m);

function findBrowserPath() {
  for (const p of EDGE_PATHS) {
    try { accessSync(p); return p; } catch { /* next */ }
  }
  throw new Error('no Edge/Chrome found');
}

const TICK_DRIVER = `(() => {
  if (window.__TICK_DRIVER__) return 'already';
  window.__TICK_DRIVER__ = setInterval(() => {
    const d = window.__NEON_SERPENT_DEBUG__;
    if (d) { try { d.tick(1); } catch (e) {} }
  }, 40);
  return 'installed';
})()`;

async function openAndDrive(browser) {
  const page = await browser.newPage();
  page.on('pageerror', (e) => log('PAGEERROR:', String(e).slice(0, 200)));
  page.on('console', (m) => {
    if (m.type() === 'error') log('CONSOLE-ERR:', m.text().slice(0, 200));
  });
  await page.goto(GAME_URL, { waitUntil: 'load', timeout: 30000 });
  await page.waitForFunction('window.__NEON_SERPENT_DEBUG__ && window.__NEON_3D_READY__', { polling: 250, timeout: 45000 });
  log('game booted, installing tick driver');
  const res = await page.evaluate(TICK_DRIVER);
  log('tick driver:', res);
  return page;
}

const browserPath = findBrowserPath();
log('browser:', browserPath, HEADLESS ? '(headless)' : '(headed)');

let browser;
try {
  browser = await puppeteer.launch({
    executablePath: browserPath,
    headless: HEADLESS,
    args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader', '--disable-background-timer-throttling',
      '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding', '--no-first-run',
      `--user-data-dir=${process.env.TEMP}\\edge-cyd-profile`]
  });
} catch (e) {
  log('launch failed:', e.message);
  process.exit(1);
}

let page;
try {
  page = await openAndDrive(browser);
} catch (e) {
  if (HEADLESS) {
    log('headless boot failed (', e.message.slice(0, 120), ') — retrying headed');
    await browser.close();
    browser = await puppeteer.launch({
      executablePath: browserPath,
      headless: false,
      args: ['--disable-background-timer-throttling', '--disable-backgrounding-occluded-windows',
        '--disable-renderer-backgrounding', '--no-first-run', `--user-data-dir=${process.env.TEMP}\\edge-cyd-profile`]
    });
    page = await openAndDrive(browser);
  } else {
    log('FATAL:', e.message);
    await browser.close();
    process.exit(1);
  }
}

/* 輪詢結果：suite 完成 -> reload（T17）；重連測試完成 -> 收工 */
const started = Date.now();
let reloaded = false;
try {
  for (;;) {
    if (Date.now() - started > 5 * 60 * 1000) { log('TIMEOUT waiting for suite'); break; }
    await new Promise((r) => setTimeout(r, 1000));
    let data = null;
    try {
      const res = await fetch(RESULTS_URL);
      data = await res.json();
    } catch { continue; }
    if (data?.summary?.done && !reloaded) {
      reloaded = true;
      log('suite done — reloading page for T17 reconnect test');
      await page.reload({ waitUntil: 'load', timeout: 30000 });
      await page.waitForFunction('window.__NEON_SERPENT_DEBUG__ && window.__NEON_3D_READY__', { polling: 250, timeout: 45000 });
      await page.evaluate(TICK_DRIVER);
      log('reloaded, tick driver reinstalled');
    }
    if (data?.summary?.reconnectTest === 'done') { log('reconnect test done'); break; }
  }
} finally {
  try { await writeFile(new URL('./driver-done.flag', import.meta.url), String(Date.now())); } catch { /* ignore */ }
  await browser.close();
  process.exit(0);
}
