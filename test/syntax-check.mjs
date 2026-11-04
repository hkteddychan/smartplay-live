import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const htmlPath = join(root, 'index.html');
let passed = 0;
const failures = [];

function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`  PASS  ${name}`);
  } catch (error) {
    failures.push(name);
    console.error(`  FAIL  ${name}`);
    console.error(`        ${error.message.split('\n')[0]}`);
  }
}

const html = readFileSync(htmlPath, 'utf8');

console.log('\nNEON SERPENT 3D — local syntax & logic check');
console.log('============================================');

check('full document, responsive viewport, title and canvas exist', () => {
  assert.ok(html.length > 40_000, 'index.html looks too small');
  assert.match(html, /^<!DOCTYPE html>/i);
  assert.match(html, /<html\b[^>]*lang="zh-Hant"/i);
  assert.match(html, /<head>[\s\S]*<\/head>/i);
  assert.match(html, /<body>[\s\S]*<\/body>/i);
  assert.match(html, /<\/html>\s*$/i);
  assert.match(html, /<meta\s+name="viewport"[^>]*width=device-width/i);
  assert.match(html, /<title>[^<]*NEON SERPENT[^<]*<\/title>/i);
  assert.match(html, /<canvas\s+id="game"/i);
});

check('start, pause and agent-link screens are present', () => {
  assert.match(html, /id="startScreen"/);
  assert.match(html, /id="pauseScreen"/);
  assert.match(html, /id="agentScreen"/);
  assert.match(html, /id="startBtn"/);
  assert.match(html, /id="resumeBtn"/);
  assert.match(html, /id="agentOpenBtn"/);
  assert.match(html, /id="agentWsInput"/);
});

check('HTML tag nesting is balanced', () => {
  const structural = html
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '<script data-script></script>')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, '<style data-style></style>');
  const voidTags = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr']);
  const tagPattern = /<(\/?)([a-zA-Z][\w:-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>/g;
  const stack = [];
  let match;
  while ((match = tagPattern.exec(structural)) !== null) {
    const closing = match[1] === '/';
    const name = match[2].toLowerCase();
    if (voidTags.has(name)) continue;
    if (closing) assert.equal(stack.pop(), name, `mismatched closing tag </${name}>`);
    else stack.push(name);
  }
  assert.deepEqual(stack, [], `unclosed tag(s): ${stack.join(', ')}`);
});

check('ids are unique and every getElementById target exists', () => {
  const ids = new Set();
  for (const match of html.matchAll(/\bid\s*=\s*["']([^"']+)["']/gi)) {
    assert.ok(!ids.has(match[1]), `duplicate id "${match[1]}"`);
    ids.add(match[1]);
  }
  for (const match of html.matchAll(/getElementById\(\s*["']([^"']+)["']\s*\)/g)) {
    assert.ok(ids.has(match[1]), `getElementById("${match[1]}") has no matching element`);
  }
});

check('mode, size, touch and 3D directions controls are wired', () => {
  assert.equal([...html.matchAll(/data-mode="/g)].length, 3, 'three game modes expected');
  assert.equal([...html.matchAll(/data-size="/g)].length, 4, 'four arena sizes expected');
  assert.equal([...html.matchAll(/data-move="/g)].length, 6, 'six touch directions expected');
  assert.match(html, /const DIRS = \[/);
  for (const direction of ["'+x'", "'-x'", "'+y'", "'-y'", "'+z'", "'-z'"]) {
    assert.ok(html.includes(direction), `missing direction ${direction}`);
  }
});

check('import map is valid and uses Three.js 0.160.0', () => {
  const match = html.match(/<script\s+type="importmap">([\s\S]*?)<\/script>/i);
  assert.ok(match, 'import map is missing');
  const importMap = JSON.parse(match[1]);
  assert.match(importMap.imports.three, /three@0\.160\.0\/build\/three\.module\.js$/);
  assert.match(importMap.imports['three/addons/'], /three@0\.160\.0\/examples\/jsm\/$/);
});

check('rendering pipeline imports composer, bloom and rounded geometry', () => {
  assert.match(html, /import\s+\*\s+as\s+THREE\s+from\s+['"]three['"]/);
  assert.match(html, /UnrealBloomPass/);
  assert.match(html, /EffectComposer/);
  assert.match(html, /OutputPass/);
  assert.match(html, /RoomEnvironment/);
  assert.match(html, /RoundedBoxGeometry/);
});

check('module script passes node --check', () => {
  const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)];
  const tempDir = mkdtempSync(join(tmpdir(), 'neon-serpent-3d-check-'));
  try {
    let checked = 0;
    for (const [, attributes, code] of scripts) {
      const typeMatch = attributes.match(/\btype\s*=\s*["']([^"']+)["']/i);
      const type = (typeMatch ? typeMatch[1] : 'text/javascript').toLowerCase();
      if (type === 'importmap' || (type !== 'module' && type !== 'text/javascript')) continue;
      assert.ok(code.trim().length > 0, 'empty script block');
      const file = join(tempDir, `script-${checked}.mjs`);
      writeFileSync(file, code, 'utf8');
      const result = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
      assert.equal(result.status, 0, `node --check failed:\n${(result.stderr || result.stdout || '').trim()}`);
      checked += 1;
    }
    assert.ok(checked >= 1, 'no JavaScript module found');
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
});

check('30×30×30 voxel arena contract exists', () => {
  assert.match(html, /const WORLD_SIZE = 22;/);
  assert.match(html, /const MAX_GRID = 30;/);
  assert.match(html, /const DEFAULT_GRID = 18;/);
  assert.match(html, /const arena = \{ size: DEFAULT_GRID/);
  assert.match(html, /function buildArenaGrid\(size\)/);
  assert.match(html, /floorGrid = new THREE\.GridHelper\(WORLD_SIZE, safeSize/);
  assert.match(html, /sliceGroup\.position\.y = toWorld\(player\.body\[0\]\)\.y/);
  assert.match(html, /data-size="30"/);
});

check('3D movement, multi-snake simulation and collision logic exist', () => {
  assert.match(html, /const MAX_SNAKES = 4;/);
  assert.match(html, /function simulateTick\(\)/);
  assert.match(html, /function chooseAiDirection\(snake\)/);
  assert.match(html, /snake\.body\.unshift\(next\)/);
  assert.match(html, /snake\.body\.pop\(\)/);
  assert.match(html, /const next = \{ x: h\.x \+ snake\.direction\.x, y: h\.y \+ snake\.direction\.y, z: h\.z \+ snake\.direction\.z \}/);
  assert.match(html, /function inBounds\(x, y, z\)/);
  assert.match(html, /blocked\.has\(vecKey\(next\)\)/);
  assert.match(html, /headCounts\.get\(vecKey\(next\)\) > 1/);
  assert.match(html, /function killSnake\(snake/);
  assert.match(html, /function updateRespawns\(\)/);
  assert.match(html, /function spawnFood\(\)/);
  assert.match(html, /globalEaten\+\+/);
  assert.match(html, /Math\.pow\(0\.965, Math\.floor\(globalEaten \/ 3\)\)/);
});

check('AI Agent window API and 3D commands are exposed', () => {
  assert.match(html, /const NeonSerpentAgent = \{/);
  assert.match(html, /window\.NeonSerpentAgent = NeonSerpentAgent/);
  assert.match(html, /window\.NeonSerpent3D = NeonSerpentAgent/);
  assert.match(html, /function joinAgent\(options = \{\}\)/);
  assert.match(html, /function leaveAgent\(id\)/);
  assert.match(html, /function queueDirection\(snake, input\)/);
  assert.match(html, /function getSnapshot\(\)/);
  assert.match(html, /subscribe\(callback\)/);
  assert.match(html, /command\(snakeId, direction\)/);
  assert.match(html, /'\+y': \{ x: 0, y: 1, z: 0 \}/);
});

check('external agent bridges: postMessage, BroadcastChannel and WebSocket', () => {
  assert.match(html, /window\.addEventListener\('message'/);
  assert.match(html, /new BroadcastChannel\('neon-serpent-3d'\)/);
  assert.match(html, /new WebSocket\(clean\)/);
  assert.match(html, /connectAgentSocket/);
  assert.match(html, /agentWs/);
  assert.match(html, /handleControlMessage/);
  assert.match(html, /AGENT_NAMESPACE = 'neon-serpent-3d\/1'/);
});

check('rendering loop, persistence and boot hooks exist', () => {
  assert.match(html, /requestAnimationFrame\(animate\)/);
  assert.match(html, /composer\.render\(\)/);
  assert.match(html, /window\.addEventListener\('keydown'/);
  assert.match(html, /localStorage/);
  assert.match(html, /window\.__NEON_3D_READY__ = true/);
  assert.match(html, /dom\.startBtn\.disabled = false/);
  assert.match(html, /function updateHUD/);
  assert.doesNotMatch(html, /\b(TODO|FIXME|lorem ipsum)\b/i);
  assert.doesNotMatch(html, /id="gameOverScreen"/);
});

/* ============================================================
   ESP32 240×320 開發板（CYD）整合檢查
============================================================ */
const fwDir = join(root, 'firmware', 'esp32_cyd_controller');
const fwRead = (name) => {
  try { return readFileSync(join(fwDir, name), 'utf8'); } catch { return ''; }
};
const ino = fwRead('esp32_cyd_controller.ino');
const splash = fwRead('splash_data.h');
const readme = fwRead('README.md');
const pioIni = fwRead('platformio.ini');

check('ESP32 CYD firmware files exist', () => {
  assert.ok(ino.length > 0, 'missing firmware/esp32_cyd_controller/esp32_cyd_controller.ino');
  assert.ok(splash.length > 0, 'missing firmware/esp32_cyd_controller/splash_data.h');
  assert.ok(readme.length > 0, 'missing firmware/esp32_cyd_controller/README.md');
  assert.ok(pioIni.length > 0, 'missing firmware/esp32_cyd_controller/platformio.ini');
});

check('agent panel documents the ESP32 hardware controller', () => {
  assert.match(html, /ESP32 240×320 開發板/);
  assert.match(html, /firmware\/esp32_cyd_controller/);
  assert.match(html, /NEON-SERPENT-CYD/);
});

check('firmware configures Wi-Fi with NVS storage and AP setup portal', () => {
  assert.match(ino, /#include\s+<WiFi\.h>/);
  assert.match(ino, /#include\s+<Preferences\.h>/);
  assert.match(ino, /#include\s+<DNSServer\.h>/);
  assert.match(ino, /WiFi\.begin\(/, 'STA connect missing');
  assert.match(ino, /WiFi\.softAP\(/, 'AP fallback missing');
  assert.match(ino, /NEON-SERPENT-CYD/, 'AP SSID missing');
  assert.match(ino, /prefs\.putString\("ssid"/, 'NVS save missing');
  assert.match(ino, /handlePortalSave/, 'portal save handler missing');
  assert.match(ino, /ESP\.restart\(\)/, 'reboot after save missing');
});

check('firmware hosts the game WebSocket bridge on port 8787', () => {
  assert.match(ino, /#include\s+<WebSocketsServer\.h>/);
  assert.match(ino, /WebSocketsServer\s+ws\(8787\)/, 'WS server port missing');
  assert.match(ino, /neon-serpent-3d\/1/, 'agent namespace missing');
  assert.match(ino, /doc\["type"\]\s*=\s*"join"/, 'join command missing');
  assert.match(ino, /doc\["type"\]\s*=\s*"command"/, 'direction command missing');
  assert.match(ino, /doc\["type"\]\s*=\s*"autopilot"/, 'autopilot command missing');
  assert.match(ino, /sendSimple\("pause"\)/, 'pause command missing');
  assert.match(ino, /ws\.loop\(\)/, 'ws pump missing');
});

check('firmware parses game state into HUD', () => {
  assert.match(ino, /deserializeJson\(doc, payload, len\)/);
  assert.match(ino, /doc\["leaderboard"\]/);
  assert.match(ino, /doc\["snakes"\]/);
  assert.match(ino, /doc\["simulation"\]\["speed"\]/);
  assert.match(ino, /kind != "agent"/, 'device snake lookup missing');
  assert.match(ino, /!foundAgent && millis\(\) - lastRejoinMs > 3000/, 'auto-rejoin after game reset missing');
});

check('firmware shows splash image and 6-direction touch pad on 240×320 TFT', () => {
  assert.match(ino, /#include\s+"splash_data\.h"/);
  assert.match(ino, /void drawSplash\(\)/);
  assert.match(ino, /drawSplash\(\);/, 'splash call missing');
  assert.match(ino, /tft\.getTouch\(/, 'touch polling missing');
  assert.match(ino, /tft\.setTouch\(/, 'touch calibration missing');
  assert.match(ino, /pgm_read_byte/, 'PROGMEM read missing');
  for (const dir of ['+x', '-x', '+y', '-y', '+z', '-z']) {
    assert.ok(ino.includes(`"${dir}"`), `touch zone for ${dir} missing`);
  }
  assert.match(ino, /ZA_PAUSE/, 'pause zone missing');
  assert.match(ino, /ZA_AUTO/, 'autopilot zone missing');
});

check('splash_data.h is a valid 240×320 RGB565 RLE payload', () => {
  assert.match(splash, /#define\s+SPLASH_W\s+240/);
  assert.match(splash, /#define\s+SPLASH_H\s+320/);
  assert.match(splash, /PROGMEM/);
  const body = splash.match(/splashRle\[\]\s*PROGMEM\s*=\s*\{([\s\S]*?)\};/);
  assert.ok(body, 'splashRle array missing');
  let covered = 0;
  let colors = 0;
  for (const m of body[1].matchAll(/0x([0-9A-Fa-f]{2}),0x([0-9A-Fa-f]{4}),/g)) {
    const count = parseInt(m[1], 16);
    assert.ok(count >= 1 && count <= 255, `invalid run count ${count}`);
    covered += count;
    colors += 1;
  }
  assert.ok(colors > 0, 'no RLE runs parsed');
  assert.equal(covered, 240 * 320, `RLE runs cover ${covered} pixels, expected 76800`);
});

check('splash generator prefers assets/hello.png and preview renders device image', () => {
  const tool = readFileSync(join(root, 'tools', 'make-splash.mjs'), 'utf8');
  assert.match(tool, /assets['"`,\s]*hello\.png/, 'hello.png preference missing');
  assert.match(tool, /preview\.png/);
  assert.match(tool, /inflateSync/);
  assert.match(tool, /splash_data\.h/);
  const preview = readFileSync(join(root, 'tools', 'render-splash-preview.mjs'), 'utf8');
  assert.match(preview, /splash-preview\.png/);
  assert.match(preview, /deflateSync/);
  assert.ok(existsSync(join(root, 'docs', 'splash-preview.png')), 'docs/splash-preview.png not generated');
});

check('firmware plays Hello Teddy greeting and shows banner on boot', () => {
  assert.match(ino, /#define\s+SPEAKER_PIN\s+26/, 'CYD speaker pin missing');
  assert.match(ino, /ledcWriteTone/, 'LEDC tone output missing');
  assert.match(ino, /void playHelloMelody\(\)/);
  assert.match(ino, /playHelloMelody\(\);/, 'melody call missing');
  assert.match(ino, /void drawHelloBanner\(\)/);
  assert.match(ino, /drawHelloBanner\(\);/, 'banner call missing');
  assert.match(ino, /HELLO TEDDY/, 'banner text missing');
  assert.match(pioIni, /SPEAKER_PIN=26/, 'speaker pin flag missing');
});

check('firmware README documents Wi-Fi setup and game connection', () => {
  assert.match(readme, /NEON-SERPENT-CYD/, 'AP instructions missing');
  assert.match(readme, /agentWs/, 'game connect URL missing');
  assert.match(readme, /8787/, 'WS port missing');
  assert.match(readme, /TFT_eSPI/, 'library docs missing');
  assert.match(readme, /hello\.png/, 'image replacement docs missing');
  assert.match(readme, /HELLO TEDDY|GPIO\s*26|SPEAKER_PIN/, 'greeting docs missing');
});

check('platformio.ini targets CYD pins and required libraries', () => {
  assert.match(pioIni, /ILI9341_2_DRIVER/);
  assert.match(pioIni, /TOUCH_CS=33/);
  assert.match(pioIni, /TFT_BL=21/);
  assert.match(pioIni, /TFT_eSPI/);
  assert.match(pioIni, /WebSockets/);
  assert.match(pioIni, /ArduinoJson/);
});

check('dist build copy matches index.html', () => {
  const dist = readFileSync(join(root, 'dist', 'index.html'), 'utf8');
  assert.equal(dist, html, 'dist/index.html is stale — copy index.html into dist/');
});

console.log('============================================');
if (failures.length > 0) {
  console.error(`FAILED: ${failures.length} check(s) failed, ${passed} passed.\n`);
  process.exit(1);
}
console.log(`PASSED: all ${passed} checks succeeded. index.html has no JavaScript syntax errors.\n`);
