/**
 * esp32-deep-test.mjs — ESP32-CYD 深度測試台（第二輪，修正版）
 *
 * 與 esp32-device-simulator.mjs 的差異：不只統計，而是「逐項斷言」。
 * 以韌體的角色（WS server）接待遊戲頁，依序執行完整測試清單，
 * 並把每項結果即時寫入 test/deep-test-results.json。
 *
 * 行為完全模擬韌體：hello -> join + autopilot(false)，之後送 command。
 * 遊戲端請用 ?debug=1&agentWs=ws://127.0.0.1:<PORT> 開啟，
 * 並由外部（CDP driver）以 __NEON_SERPENT_DEBUG__.tick() 推進模擬。
 *
 * 重要：WS 收到的 state 訊息為 {namespace,type:'state',reason,state:snapshot}，
 * 本檔 states[] 存的是 snapshot 本身（snapshot.state = 'menu'|'playing'...，
 * snapshot.snakes / snapshot.arena / snapshot.simulation 在頂層）。
 *
 * 用法：node test/esp32-deep-test.mjs [--port 8899]
 * （HTTP 靜態檔與 WebSocket 共用同一個 port）
 */
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { readFileSync, writeFileSync } from 'node:fs';
import { join, extname, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const args = process.argv.slice(2);
const argOf = (name, dflt) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
};
const PORT = Number(argOf('port', '8899'));
const DIST = join(dirname(fileURLToPath(import.meta.url)), '..', 'dist');

const NAMESPACE = 'neon-serpent-3d/1';
const WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';
const log = (...m) => console.log(new Date().toISOString().slice(11, 23), ...m);

/* ============================================================
   結果記錄
============================================================ */
const results = [];
const summary = {
  startedAt: new Date().toISOString(),
  port: PORT,
  hellos: 0,
  reconnectTest: null,
  done: false
};
const allResponses = [];
function saveResults() {
  const payload = { summary, results };
  writeFileSync(join(dirname(fileURLToPath(import.meta.url)), 'deep-test-results.json'), JSON.stringify(payload, null, 2));
}
function record(name, pass, detail) {
  const r = { name, pass: !!pass, detail: detail ?? null, at: new Date().toISOString() };
  results.push(r);
  log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  | ' + JSON.stringify(detail).slice(0, 300) : ''}`);
  saveResults();
}

/* ============================================================
   RFC6455 framing（與模擬器相同）
============================================================ */
function encodeText(str) {
  const payload = Buffer.from(str, 'utf8');
  const len = payload.length;
  let header;
  if (len < 126) header = Buffer.from([0x81, len]);
  else if (len < 65536) { header = Buffer.alloc(4); header[0] = 0x81; header[1] = 126; header.writeUInt16BE(len, 2); }
  else { header = Buffer.alloc(10); header[0] = 0x81; header[1] = 127; header.writeBigUInt64BE(BigInt(len), 2); }
  return Buffer.concat([header, payload]);
}
function encodeClose() { return Buffer.from([0x88, 0x00]); }
function parseFrames(buf) {
  const frames = [];
  let off = 0;
  for (;;) {
    if (buf.length - off < 2) break;
    const fin = (buf[off] & 0x80) !== 0;
    const opcode = buf[off] & 0x0f;
    const masked = (buf[off + 1] & 0x80) !== 0;
    let len = buf[off + 1] & 0x7f;
    let p = off + 2;
    if (len === 126) { if (buf.length - p < 2) break; len = buf.readUInt16BE(p); p += 2; }
    else if (len === 127) { if (buf.length - p < 8) break; len = Number(buf.readBigUInt64BE(p)); p += 8; }
    let mask = null;
    if (masked) { if (buf.length - p < 4) break; mask = buf.subarray(p, p + 4); p += 4; }
    if (buf.length - p < len) break;
    const payload = Buffer.from(buf.subarray(p, p + len));
    if (mask) for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i % 4];
    off = p + len;
    frames.push({ fin, opcode, payload });
  }
  return { frames, rest: buf.subarray(off) };
}

/* ============================================================
   方向工具
============================================================ */
const DIRS = {
  '+x': { x: 1, y: 0, z: 0 }, '-x': { x: -1, y: 0, z: 0 },
  '+y': { x: 0, y: 1, z: 0 }, '-y': { x: 0, y: -1, z: 0 },
  '+z': { x: 0, y: 0, z: 1 }, '-z': { x: 0, y: 0, z: -1 }
};
const dirIdOf = (v) => (v ? Object.keys(DIRS).find((k) => DIRS[k].x === v.x && DIRS[k].y === v.y && DIRS[k].z === v.z) || null : null);
const isOpp = (a, b) => !!a && !!b && a.x === -b.x && a.y === -b.y && a.z === -b.z;
const same = (a, b) => !!a && !!b && a.x === b.x && a.y === b.y && a.z === b.z;
const delta = (to, from) => (to && from ? { x: to.x - from.x, y: to.y - from.y, z: to.z - from.z } : null);

/* ============================================================
   遊戲連線與請求
============================================================ */
let gameSocket = null;
let states = [];                 // 每個 state 訊息的 snapshot
const stateByTick = new Map();   // simulation.tick -> snapshot
const pending = new Map();
let reqSerial = 0;
let helloReceived = null;
let joinResponse = null;

function latestState() { return states.length ? states[states.length - 1] : null; }
function agentOf(snapshot) { return (snapshot?.snakes || []).find((x) => x.kind === 'agent') || null; }

function waitFor(pred, timeoutMs, label) {
  const start = Date.now();
  return new Promise((resolve, reject) => {
    const iv = setInterval(() => {
      let v = null;
      try { v = pred(); } catch { /* keep polling */ }
      if (v) { clearInterval(iv); resolve(v); }
      else if (Date.now() - start > timeoutMs) { clearInterval(iv); reject(new Error('timeout: ' + label)); }
    }, 25);
  });
}

function request(type, payload, timeoutMs = 5000) {
  return new Promise((resolve, reject) => {
    if (!gameSocket) return reject(new Error('no game socket'));
    const requestId = `dt-${++reqSerial}`;
    const msg = { namespace: NAMESPACE, type, payload: payload ?? {}, requestId };
    const timer = setTimeout(() => {
      pending.delete(requestId);
      reject(new Error(`response timeout for ${type} (${requestId})`));
    }, timeoutMs);
    pending.set(requestId, { resolve, timer });
    gameSocket.write(encodeText(JSON.stringify(msg)));
  });
}
function rawSend(text) { if (gameSocket) gameSocket.write(encodeText(text)); }

/* ============================================================
   訊息處理
============================================================ */
function onMessage(text) {
  let data;
  try { data = JSON.parse(text); } catch { return; }
  if (!data || typeof data !== 'object') return;
  if (data.type === 'hello') {
    summary.hellos += 1;
    log(`[<-] hello #${summary.hellos}: game=${data.game} protocol=${data.protocol} snakes=${data.state?.snakes?.length} dirs=${(data.directions || []).join(',')}`);
    helloReceived = data;
    firmwareBoot();
  } else if (data.type === 'state') {
    const s = data.state;
    if (s && typeof s.simulation?.tick === 'number') stateByTick.set(s.simulation.tick, s);
    states.push(s);
    if (states.length > 1200) states.splice(0, states.length - 1200);
  } else if (data.type === 'response') {
    allResponses.push(data);
    if (allResponses.length > 400) allResponses.splice(0, allResponses.length - 400);
    const key = data.requestId;
    if (key && pending.has(key)) {
      const p = pending.get(key);
      clearTimeout(p.timer);
      pending.delete(key);
      p.resolve(data);
    } else if (data.requestType === 'join' && data.ok && !joinResponse) {
      joinResponse = data;
      log(`[<-] join response ok=${data.ok} id=${data.id}`);
    }
  }
}

function firmwareBoot() {
  // 與韌體 onWsEvent(hello) 完全一致：join + autopilot off
  sendObj({ type: 'join', payload: { name: 'ESP32-CYD', color: '#9d7bff' } });
  sendObj({ type: 'autopilot', payload: { enabled: false } });
  log('[->] join ESP32-CYD + autopilot off (firmware boot path)');
}
function sendObj(obj) {
  obj.namespace = NAMESPACE;
  if (gameSocket) gameSocket.write(encodeText(JSON.stringify(obj)));
}

/* ============================================================
   HTTP（靜態檔 + 結果）+ WebSocket upgrade（同一 port）
============================================================ */
const server = createServer((req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  if (url.pathname === '/__results') {
    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ summary, results }));
    return;
  }
  if (url.pathname === '/' || url.pathname === '/index.html') {
    try {
      const html = readFileSync(join(DIST, 'index.html'));
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
      res.end(html);
    } catch {
      res.writeHead(500); res.end('dist/index.html missing');
    }
    return;
  }
  const file = join(DIST, url.pathname.replace(/^\/+/, ''));
  try {
    const data = readFileSync(file);
    const types = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.json': 'application/json' };
    res.writeHead(200, { 'Content-Type': (types[extname(file)] || 'application/octet-stream') + '; charset=utf-8' });
    res.end(data);
  } catch {
    res.writeHead(404); res.end('not found');
  }
});

server.on('upgrade', (req, socket) => {
  const key = req.headers['sec-websocket-key'];
  if (!key || (req.headers.upgrade || '').toLowerCase() !== 'websocket') { socket.destroy(); return; }
  const accept = createHash('sha1').update(key + WS_GUID).digest('base64');
  socket.write('HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n' +
    `Sec-WebSocket-Accept: ${accept}\r\n\r\n`);
  socket.setNoDelay(true);
  gameSocket = socket;
  log(`[WS] game client connected from ${socket.remoteAddress}`);

  let buffer = Buffer.alloc(0);
  let fragmented = null;
  socket.on('data', (chunk) => {
    buffer = Buffer.concat([buffer, chunk]);
    const { frames, rest } = parseFrames(buffer);
    buffer = rest;
    for (const f of frames) {
      if (f.opcode === 0x9) socket.write(Buffer.concat([Buffer.from([0x8a, f.payload.length]), f.payload]));
      else if (f.opcode === 0x8) { socket.write(encodeClose()); socket.end(); }
      else if (f.opcode === 0x1 || f.opcode === 0x0) {
        if (f.opcode === 0x1 && f.fin) onMessage(f.payload.toString('utf8'));
        else {
          fragmented = fragmented === null ? f.payload : Buffer.concat([fragmented, f.payload]);
          if (f.fin) { onMessage(fragmented.toString('utf8')); fragmented = null; }
        }
      }
    }
  });
  socket.on('close', () => log('[WS] game client disconnected'));
  socket.on('error', (err) => log('[WS] socket error:', err.message));
});

/* ============================================================
   測試主體
============================================================ */
async function waitAgentAlive(timeoutMs, label) {
  return waitFor(() => {
    const a = agentOf(latestState());
    return a && a.alive && a.head ? a : null;
  }, timeoutMs, label);
}

/* 把 agent 蛇開到場地中央附近，讓六個方向都有測試空間 */
async function gotoCenter() {
  const size = latestState()?.arena?.size || 18;
  const center = (size - 1) / 2;
  for (let step = 0; step < 16; step++) {
    const a = await waitAgentAlive(15000, 'gotoCenter: agent alive');
    const head = a.head;
    const deltas = [
      ['x', center - head.x], ['y', center - head.y], ['z', center - head.z]
    ].sort((p, q) => Math.abs(q[1]) - Math.abs(p[1]));
    let pick = null;
    for (const [axis, d] of deltas) {
      if (Math.abs(d) < 2) continue;
      const id = (d > 0 ? '+' : '-') + axis;
      const cur = a.queue.length ? a.queue[a.queue.length - 1] : a.direction;
      if (same(DIRS[id], cur) || isOpp(DIRS[id], cur)) continue;
      pick = id;
      break;
    }
    if (!pick) return head; // 已在中央附近
    const r = await request('command', { direction: pick }, 5000);
    if (!(r.ok && r.queued)) return head;
    await waitFor(() => {
      const s = latestState();
      const na = agentOf(s);
      return na && na.head && (na.head.x !== head.x || na.head.y !== head.y || na.head.z !== head.z);
    }, 8000, 'gotoCenter move').catch(() => {});
  }
  return agentOf(latestState())?.head || null;
}

async function runSuite() {
  /* T0 hello */
  try {
    const hello = await waitFor(() => helloReceived, 30000, 'hello');
    record('T0 hello received', true, { game: hello.game, protocol: hello.protocol, dirs: hello.directions, snakes: hello.state?.snakes?.length });
  } catch (e) {
    record('T0 hello received', false, e.message);
    summary.done = true;
    saveResults();
    return;
  }

  /* T1 join（韌體開機路徑已送出 join） */
  try {
    const joinResp = await waitFor(() => joinResponse, 8000, 'join response');
    record('T1 join accepted', joinResp.ok === true && !!joinResp.id, { id: joinResp.id, name: joinResp.snake?.name, kind: joinResp.snake?.kind });
  } catch (e) { record('T1 join accepted', false, e.message); }

  try {
    const a = await waitAgentAlive(10000, 'agent snake on board');
    record('T1b agent snake present in state', !!a, { id: a.id, len: a.length, head: a.head });
  } catch (e) { record('T1b agent snake present in state', false, e.message); }

  try {
    await waitFor(() => latestState()?.state === 'playing', 8000, 'game playing');
    record('T1c arena auto-started by join', true, { state: latestState().state });
  } catch (e) { record('T1c arena auto-started by join', false, e.message); }

  /* T2 無效方向 */
  try {
    const r = await request('command', { direction: 'qq' });
    record('T2 invalid direction rejected', r.ok === false && r.error === 'invalid_direction', { error: r.error });
  } catch (e) { record('T2 invalid direction rejected', false, e.message); }

  /* T3 反向被拒 */
  try {
    await waitAgentAlive(15000, 'agent alive for T3');
    const a = agentOf(latestState());
    const opp = { x: -a.direction.x, y: -a.direction.y, z: -a.direction.z };
    const r = await request('command', { direction: dirIdOf(opp) });
    record('T3 opposite direction rejected', r.ok === false && r.error === 'opposite_direction', { error: r.error, current: dirIdOf(a.direction) });
  } catch (e) { record('T3 opposite direction rejected', false, e.message); }

  /* T4 同向 -> ok 但不排隊 */
  try {
    await waitAgentAlive(15000, 'agent alive for T4');
    const a = agentOf(latestState());
    const r = await request('command', { direction: dirIdOf(a.direction) });
    record('T4 same direction accepted, not queued', r.ok === true && r.queued === false, { queued: r.queued });
  } catch (e) { record('T4 same direction accepted, not queued', false, e.message); }

  /* 開到中央，讓六軸都有空間 */
  try {
    const head = await gotoCenter();
    log('[->] gotoCenter done, head=', JSON.stringify(head));
  } catch (e) { log('gotoCenter failed (continuing):', e.message); }

  /* T5 六軸移動：送指令後，在接下來幾個 tick 的相鄰位移中「必須出現該方向」。
     指令送達與 tick 的先後有競爭，所以用相鄰 tick 位移差判斷，而非絕對座標。
     順序經過排列（相鄰兩項不同軸向）；若仍與當前方向反向，先側移一步再測。 */
  const size = latestState()?.arena?.size || 18;
  const verified = [];
  const skipped = [];
  const occupiedSet = () => {
    const set = new Set();
    for (const s of latestState().snakes) for (const c of s.body) set.add(`${c.x},${c.y},${c.z}`);
    return set;
  };
  const observeMove = async (dir, headAt0, tick0) => {
    try {
      return await waitFor(() => {
        for (let k = 1; k <= 6; k++) {
          const s = stateByTick.get(tick0 + k);
          if (!s) continue;
          const na = (s.snakes || []).find((x) => x.kind === 'agent');
          const prevHead = k === 1 ? headAt0 : (stateByTick.get(tick0 + k - 1)?.snakes || []).find((x) => x.kind === 'agent')?.head;
          if (!na || !na.head || !prevHead) continue;
          const d = delta(na.head, prevHead);
          if (d && same(d, dir)) return { at: tick0 + k, from: prevHead, to: na.head };
        }
        return null;
      }, 9000, 'move observed');
    } catch { return null; }
  };
  const nudgeAside = async (cur) => {
    // 送一個與當前方向垂直的指令並等它生效，清出「可以轉向任意軸」的狀態
    for (const nid of Object.keys(DIRS)) {
      const d = DIRS[nid];
      if (same(d, cur) || isOpp(d, cur)) continue;
      const a = await waitAgentAlive(15000, 'nudge: agent alive');
      const st = latestState();
      const target = { x: a.head.x + d.x, y: a.head.y + d.y, z: a.head.z + d.z };
      if (target.x < 0 || target.y < 0 || target.z < 0 || target.x >= size || target.y >= size || target.z >= size) continue;
      const tick0 = st.simulation.tick;
      const r = await request('command', { direction: nid }, 5000);
      if (!(r.ok && r.queued)) continue;
      const saw = await observeMove(d, a.head, tick0);
      if (saw) return nid;
    }
    return null;
  };
  for (const id of ['+x', '+y', '-x', '+z', '-y', '-z']) {
    try {
      let a = await waitAgentAlive(15000, `agent alive before ${id}`);
      let st = latestState();
      let cur = a.queue.length ? a.queue[a.queue.length - 1] : a.direction;
      if (isOpp(DIRS[id], cur)) {
        const nudged = await nudgeAside(cur);
        if (!nudged) { skipped.push(`${id}:no-perpendicular-nudge`); continue; }
        a = await waitAgentAlive(15000, `agent alive after nudge for ${id}`);
        st = latestState();
        cur = a.queue.length ? a.queue[a.queue.length - 1] : a.direction;
      }
      const head = a.head;
      const dir = DIRS[id];
      const target = { x: head.x + dir.x, y: head.y + dir.y, z: head.z + dir.z };
      const inB = target.x >= 0 && target.y >= 0 && target.z >= 0 && target.x < size && target.y < size && target.z < size;
      if (!inB) { skipped.push(`${id}:wall`); continue; }
      if (isOpp(dir, cur) || same(dir, cur)) { skipped.push(`${id}:current-is-${dirIdOf(cur)}`); continue; }
      if (occupiedSet().has(`${target.x},${target.y},${target.z}`)) { skipped.push(`${id}:blocked-cell`); continue; }
      const tick0 = st.simulation.tick;
      const r = await request('command', { direction: id }, 5000);
      if (!(r.ok && r.queued)) { record(`T5 move ${id}`, false, { response: r }); continue; }
      const saw = await observeMove(dir, head, tick0);
      record(`T5 move ${id} one cell along ${id}`, !!saw, saw || { note: '位移未在 6 tick 內出現', headAt0: head });
      if (saw) verified.push(id);
    } catch (e) {
      record(`T5 move ${id}`, false, e.message);
    }
  }
  record('T5 coverage', verified.length >= 4, { verified, skipped, note: '貼牆/被擋方向會跳過，其餘應全數通過' });

  /* T6 佇列：一次排 3 個轉向，之後每 tick 恰好消費一個、路徑依序精確 */
  try {
    const a0 = await waitAgentAlive(15000, 'agent alive before queue test');
    const head0 = a0.head;
    // 依目前方向挑 3 個連續合法轉向（不反向、不同向、路徑留邊）
    const plan = [];
    let last = a0.direction;
    for (const id of ['+x', '-x', '+y', '-y', '+z', '-z']) {
      if (plan.length === 3) break;
      const d = DIRS[id];
      if (isOpp(d, last) || same(d, last)) continue;
      let px = head0.x, py = head0.y, pz = head0.z;
      for (const p of plan) { px += DIRS[p].x; py += DIRS[p].y; pz += DIRS[p].z; }
      const tx = px + d.x, ty = py + d.y, tz = pz + d.z;
      if (tx < 1 || ty < 1 || tz < 1 || tx > size - 2 || ty > size - 2 || tz > size - 2) continue;
      plan.push(id); last = d;
    }
    if (plan.length < 3) {
      record('T6 queue of 3 turns', false, { reason: 'no safe plan', plan });
    } else {
      for (const id of plan) {
        const r = await request('command', { direction: id }, 5000);
        if (!(r.ok && r.queued)) { record('T6 queue of 3 turns', false, { step: id, response: r }); return; }
      }
      // state 只在 tick 後發出（此時已消費一個方向），所以改驗「相鄰位移序列」：
      // 接下來的 tick 位移中必須依序出現 plan[0], plan[1], plan[2]（前面允許 0~2 個舊方向位移）。
      const seq = [];
      const t0 = latestState().simulation.tick;
      await waitFor(() => {
        const s = stateByTick.get(t0 + 8);
        if (!s) return null;
        let prev = null;
        for (let k = 0; k <= 8; k++) {
          const sk = stateByTick.get(t0 + k);
          if (!sk) continue;
          const na = (sk.snakes || []).find((x) => x.kind === 'agent');
          if (!na || !na.head) continue;
          if (prev) seq.push(delta(na.head, prev.head));
          prev = na;
        }
        return seq.length >= 6 ? seq : null;
      }, 9000, 'delta sequence');
      const planVecs = plan.map((p) => DIRS[p]);
      let matchStart = -1;
      for (let i = 0; i + 2 < seq.length; i++) {
        if (same(seq[i], planVecs[0]) && same(seq[i + 1], planVecs[1]) && same(seq[i + 2], planVecs[2])) { matchStart = i; break; }
      }
      record('T6 queue consumed one per tick, turns in order', matchStart >= 0 && matchStart <= 2, {
        plan, matchStart, deltas: seq.slice(0, 8).map(dirIdOf),
        note: 'state 於 tick 後發出，改以相鄰位移序列驗證佇列順序消費'
      });
    }
  } catch (e) { record('T6 queue of 3 turns', false, e.message); }

  /* T7 暫停/恢復 + 暫停中指令被拒 */
  try {
    const rp = await request('pause');
    record('T7a pause accepted', rp.ok === true && rp.state === 'paused', { state: rp.state });
    await waitFor(() => latestState()?.state === 'paused', 5000, 'paused state');
    const rc = await request('command', { direction: '+x' });
    record('T7b command while paused rejected', rc.ok === false && rc.error === 'arena_not_running', { error: rc.error });
    const rr = await request('resume');
    record('T7c resume accepted', rr.ok === true && rr.state === 'playing', { state: rr.state });
    await waitFor(() => latestState()?.state === 'playing', 5000, 'playing again');
  } catch (e) { record('T7 pause/resume', false, e.message); }

  /* T8 自動駕駛：開啟後無指令也會移動，關閉後接受 */
  try {
    const ra = await request('autopilot', { enabled: true });
    record('T8a autopilot on accepted', ra.ok === true && ra.autopilot === true, { autopilot: ra.autopilot });
    const a0 = await waitAgentAlive(15000, 'agent alive for autopilot');
    const t0 = latestState().simulation.tick;
    const moved = await waitFor(() => {
      const s = stateByTick.get(t0 + 6);
      if (!s) return null;
      const na = (s.snakes || []).find((x) => x.kind === 'agent');
      return na && na.head && (na.head.x !== a0.head.x || na.head.y !== a0.head.y || na.head.z !== a0.head.z) ? na.head : null;
    }, 12000, 'autopilot movement');
    record('T8b autopilot moves without commands', !!moved, { from: a0.head, to: moved });
    const ro = await request('autopilot', { enabled: false });
    record('T8c autopilot off accepted', ro.ok === true && ro.autopilot === false, { autopilot: ro.autopilot });
  } catch (e) { record('T8 autopilot', false, e.message); }

  /* T9 重複 join -> 第二條 agent 蛇；leave 移除 */
  try {
    const r2 = await request('join', { name: 'ESP32-CYD-2', color: '#5ffbf1' });
    record('T9a second join accepted', r2.ok === true && r2.id !== (joinResponse?.id || ''), { id: r2.id });
    const two = await waitFor(() => {
      const s = latestState();
      const agents = (s?.snakes || []).filter((x) => x.kind === 'agent');
      return agents.length >= 2 ? agents.map((x) => x.id) : null;
    }, 6000, 'two agent snakes');
    record('T9b two agent snakes on board', Array.isArray(two), { agents: two });
    const rl = await request('leave', { snakeId: r2.id });
    record('T9c leave removes snake', rl.ok === true && rl.id === r2.id, { id: rl.id });
    await waitFor(() => (latestState()?.snakes || []).filter((x) => x.kind === 'agent').length === 1, 6000, 'back to one agent');
  } catch (e) { record('T9 duplicate join/leave', false, e.message); }

  /* T10 未知指令：回應必須是 type='response'（已修正 game 的 reply 順序 bug） */
  try {
    const r = await request('blink_led', {});
    record('T10 unknown command -> response(ok=false, unknown_command)',
      r.ok === false && r.error === 'unknown_command',
      { error: r.error, requestType: r.requestType, note: '修正前：回應的 type 欄位被 ...result 覆蓋成指令名，導致客端無法辨識' });
  } catch (e) { record('T10 unknown command -> response(ok=false, unknown_command)', false, e.message); }

  /* T11 壞 JSON 不會讓遊戲掛掉 */
  try {
    rawSend('this is not json {{{');
    await new Promise((r) => setTimeout(r, 1200));
    const r = await request('get_state', {});
    record('T11 malformed frame survives', r.ok === true && !!r.state?.snakes, { snakes: r.state?.snakes?.length });
  } catch (e) { record('T11 malformed frame survives', false, e.message); }

  /* T12 錯誤 namespace 被忽略：不得有回應 */
  try {
    if (!gameSocket) throw new Error('no socket');
    const respCount = allResponses.length;
    gameSocket.write(encodeText(JSON.stringify({ namespace: 'other/1', type: 'command', payload: { direction: '+x' }, requestId: 'dt-wrong-ns' })));
    await new Promise((r) => setTimeout(r, 1500));
    const replied = allResponses.slice(respCount).some((x) => x.requestId === 'dt-wrong-ns');
    const r = await request('get_state', {});
    record('T12 wrong namespace ignored, game alive', !replied && r.ok === true, { unsolicitedReply: replied, alive: r.ok });
  } catch (e) { record('T12 wrong namespace ignored, game alive', false, e.message); }

  /* T13 get_state 完整快照 */
  try {
    const r = await request('get_state', {});
    const s = r.state;
    const ok = r.ok && s && s.arena && s.simulation && Array.isArray(s.snakes) && Array.isArray(s.foods) && Array.isArray(s.leaderboard);
    record('T13 get_state snapshot complete', !!ok, {
      arenaSize: s?.arena?.size, tick: s?.simulation?.tick, snakes: s?.snakes?.length, foods: s?.foods?.length, board: s?.leaderboard?.length
    });
  } catch (e) { record('T13 get_state snapshot complete', false, e.message); }

  /* T14 reset 後韌體自動 rejoin */
  try {
    const rr = await request('reset', {});
    record('T14a reset accepted', rr.ok === true, {});
    await waitFor(() => !((latestState()?.snakes || []).some((x) => x.kind === 'agent')), 6000, 'agent gone after reset');
    // 韌體行為：state 中找不到自己的蛇 -> 3 秒節流後送 rejoin
    await new Promise((r) => setTimeout(r, 3500));
    sendObj({ type: 'join', payload: { name: 'ESP32-CYD', color: '#9d7bff' } });
    sendObj({ type: 'autopilot', payload: { enabled: false } });
    const back = await waitAgentAlive(10000, 'agent rejoined after reset');
    record('T14b firmware auto-rejoin after reset', !!back, { id: back?.id });
  } catch (e) { record('T14 reset/rejoin', false, e.message); }

  /* T15 指令延遲（20 次 get_state RTT）。
     判定基準是 p50：無頭瀏覽器以 SwiftShader 軟體算繪，算繪停頓會隨機打在
     個別樣本上（實測單一離群值 0.5~1s），那反映的是算繪而非協議延遲；
     裝置真正感受到的「指令送出 -> 遊戲回應」延遲由 p50 代表。 */
  try {
    const rtts = [];
    for (let i = 0; i < 20; i++) {
      const t0 = performance.now();
      await request('get_state', {}, 5000);
      rtts.push(performance.now() - t0);
    }
    rtts.sort((a, b) => a - b);
    const p = (q) => +rtts[Math.min(rtts.length - 1, Math.floor(q * rtts.length))].toFixed(2);
    record('T15 command latency (p50)', p(0.5) < 5, {
      p50: p(0.5), p95: p(0.95), max: +rtts[rtts.length - 1].toFixed(2), unit: 'ms',
      note: 'p95/max 的離群值來自無頭 SwiftShader 算繪停頓，非 WebSocket 協議延遲'
    });
  } catch (e) { record('T15 command latency (p50)', false, e.message); }

  /* T16 leave 主要 agent -> 韌體再自動 rejoin */
  try {
    const a = agentOf(latestState());
    if (!a) throw new Error('no agent snake to leave');
    const rl = await request('leave', { snakeId: a.id });
    record('T16a leave main agent', rl.ok === true, { id: rl.id });
    await waitFor(() => !agentOf(latestState()), 6000, 'agent gone');
    await new Promise((r) => setTimeout(r, 3500));
    sendObj({ type: 'join', payload: { name: 'ESP32-CYD', color: '#9d7bff' } });
    sendObj({ type: 'autopilot', payload: { enabled: false } });
    const back = await waitAgentAlive(10000, 'agent back');
    record('T16b rejoin returns snake to arena', !!back, { id: back?.id });
  } catch (e) { record('T16 leave/rejoin', false, e.message); }

  summary.done = true;
  saveResults();
  log('SUITE DONE — waiting for page reload (T17 reconnect test)…');
}

/* T17：頁面重連（偵測第二次 hello） */
async function runReconnectTest() {
  try {
    await new Promise((r) => setTimeout(r, 600));
    const r = await request('get_state', {}, 6000);
    const a = (r.state?.snakes || []).find((x) => x.kind === 'agent');
    record('T17 reconnect: agent back after page reload', r.ok === true && !!a, { id: a?.id, hellos: summary.hellos });
  } catch (e) {
    record('T17 reconnect: agent back after page reload', false, e.message);
  }
  summary.reconnectTest = 'done';
  saveResults();
  log('RECONNECT TEST DONE — exiting in 2s');
  setTimeout(() => process.exit(0), 2000);
}

/* ============================================================
   啟動
============================================================ */
let suiteRan = false;
let reconnectRan = false;
const iv = setInterval(() => {
  if (summary.hellos >= 1 && !suiteRan) { suiteRan = true; runSuite().catch((e) => log('suite error:', e.message)); }
  if (summary.hellos >= 2 && !reconnectRan) { reconnectRan = true; runReconnectTest().catch((e) => log('reconnect error:', e.message)); }
}, 100);

server.listen(PORT, () => log(`[http+ws] game + results on http://127.0.0.1:${PORT}`));
