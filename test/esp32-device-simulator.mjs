/**
 * esp32-device-simulator.mjs — ESP32-CYD 控制器的桌面模擬器
 *
 * 用純 Node 實作 WebSocket server（RFC6455），行為與韌體相同：
 *   收到 hello -> 送 join + autopilot
 *   收到 state -> 統計，並自動朝最近食物送 command（模擬觸控操作）
 *
 * 用法：node test/esp32-device-simulator.mjs [--port 8787] [--duration 60] [--quiet]
 * 結束時印 JSON 摘要；state > 0 且收到 hello 視為連線成功。
 */
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';

const args = process.argv.slice(2);
const argOf = (name, dflt) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 && args[i + 1] ? args[i + 1] : dflt;
};
const PORT = Number(argOf('port', '8787'));
const DURATION = Number(argOf('duration', '0')) * 1000;
const QUIET = args.includes('--quiet');

const NAMESPACE = 'neon-serpent-3d/1';
const WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';

const log = (...m) => { if (!QUIET) console.log(new Date().toISOString().slice(11, 23), ...m); };

const stats = {
  hellos: 0,
  states: 0,
  responses: 0,
  responsesOk: 0,
  commandsSent: 0,
  joinsSent: 0,
  lastLength: 0,
  lastScore: 0,
  gameStates: {},
  startedAt: Date.now()
};

/* ---------- RFC6455 framing ---------- */
function encodeText(str) {
  const payload = Buffer.from(str, 'utf8');
  const len = payload.length;
  let header;
  if (len < 126) {
    header = Buffer.from([0x81, len]);
  } else if (len < 65536) {
    header = Buffer.alloc(4);
    header[0] = 0x81; header[1] = 126;
    header.writeUInt16BE(len, 2);
  } else {
    header = Buffer.alloc(10);
    header[0] = 0x81; header[1] = 127;
    header.writeBigUInt64BE(BigInt(len), 2);
  }
  return Buffer.concat([header, payload]);
}

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
    if (len === 126) {
      if (buf.length - p < 2) break;
      len = buf.readUInt16BE(p); p += 2;
    } else if (len === 127) {
      if (buf.length - p < 8) break;
      len = Number(buf.readBigUInt64BE(p)); p += 8;
    }
    let mask = null;
    if (masked) {
      if (buf.length - p < 4) break;
      mask = buf.subarray(p, p + 4); p += 4;
    }
    if (buf.length - p < len) break;
    const payload = Buffer.from(buf.subarray(p, p + len));
    if (mask) for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i % 4];
    off = p + len;
    frames.push({ fin, opcode, payload });
  }
  return { frames, rest: buf.subarray(off) };
}

/* ---------- 轉向邏輯：朝最近的食物（模擬韌體觸控輸入） ---------- */
const DIRS = {
  '+x': { x: 1, y: 0, z: 0 }, '-x': { x: -1, y: 0, z: 0 },
  '+y': { x: 0, y: 1, z: 0 }, '-y': { x: 0, y: -1, z: 0 },
  '+z': { x: 0, y: 0, z: 1 }, '-z': { x: 0, y: 0, z: -1 }
};
const oppositeVec = (idA, vecB) => {
  const a = DIRS[idA];
  return !!a && !!vecB && a.x === -vecB.x && a.y === -vecB.y && a.z === -vecB.z;
};

function chooseDirection(snake, foods) {
  if (!snake || !snake.head || !Array.isArray(foods) || !foods.length) return null;
  const head = snake.head;
  const cur = snake.direction;
  let best = null, bestDist = Infinity;
  for (const food of foods) {
    const d = Math.abs(food.x - head.x) + Math.abs(food.y - head.y) + Math.abs(food.z - head.z);
    if (d < bestDist) { bestDist = d; best = food; }
  }
  const deltas = [
    ['x', '+x', '-x'], ['y', '+y', '-y'], ['z', '+z', '-z']
  ].flatMap(([axis, pos, neg]) => {
    const d = best[axis] - head[axis];
    return d === 0 ? [] : [[Math.abs(d), d > 0 ? pos : neg]];
  }).sort((a, b) => b[0] - a[0]);
  for (const [, dir] of deltas) {
    if (!oppositeVec(dir, cur)) return dir;
  }
  for (const dir of Object.keys(DIRS)) {
    if (!oppositeVec(dir, cur)) return dir;
  }
  return null;
}

/* ---------- WebSocket server（模擬韌體） ---------- */
const server = createServer((_req, res) => {
  res.writeHead(426, { 'Content-Type': 'text/plain' });
  res.end('NEON SERPENT device simulator: WebSocket only');
});

server.on('upgrade', (req, socket) => {
  const key = req.headers['sec-websocket-key'];
  if (!key || (req.headers.upgrade || '').toLowerCase() !== 'websocket') {
    socket.destroy();
    return;
  }
  const accept = createHash('sha1').update(key + WS_GUID).digest('base64');
  socket.write(
    'HTTP/1.1 101 Switching Protocols\r\n' +
    'Upgrade: websocket\r\n' +
    'Connection: Upgrade\r\n' +
    `Sec-WebSocket-Accept: ${accept}\r\n\r\n`
  );
  socket.setNoDelay(true);
  log(`[WS] game client connected from ${socket.remoteAddress} (${req.headers.origin || 'no-origin'})`);

  let buffer = Buffer.alloc(0);
  let fragmented = null;

  const sendObj = (obj) => {
    socket.write(encodeText(JSON.stringify(obj)));
  };

  const handleMessage = (text) => {
    let data;
    try { data = JSON.parse(text); } catch { return; }
    if (!data || typeof data !== 'object') return;
    if (data.namespace && data.namespace !== NAMESPACE) return;
    if (data.type === 'hello') {
      stats.hellos += 1;
      log(`[<-] hello: game=${data.game} protocol=${data.protocol} snakes=${data.state?.snakes?.length}`);
      sendObj({
        namespace: NAMESPACE, type: 'join',
        payload: { name: 'ESP32-CYD', color: '#9d7bff' }
      });
      stats.joinsSent += 1;
      sendObj({ namespace: NAMESPACE, type: 'autopilot', payload: { enabled: false } });
      sendObj({ namespace: NAMESPACE, type: 'command', payload: { direction: '+x' } });
      stats.commandsSent += 1;
      log('[->] join ESP32-CYD + autopilot off + command +x');
    } else if (data.type === 'state') {
      stats.states += 1;
      const state = data.state || {};
      stats.gameStates[state.state] = (stats.gameStates[state.state] || 0) + 1;
      let agent = (state.snakes || []).find((s) => s.kind === 'agent');
      // 遊戲 reset 後 Agent 蛇消失 -> 自動重新 join（節流：每 10 個 state 最多一次）
      if (!agent && stats.states - (stats.lastRejoinState ?? -10) > 10) {
        stats.lastRejoinState = stats.states;
        stats.rejoinsSent = (stats.rejoinsSent || 0) + 1;
        sendObj({ namespace: NAMESPACE, type: 'join', payload: { name: 'ESP32-CYD', color: '#9d7bff' } });
        sendObj({ namespace: NAMESPACE, type: 'autopilot', payload: { enabled: false } });
        log('[->] rejoin: agent snake missing from state');
        agent = null;
      }
      if (agent) {
        stats.lastLength = agent.length;
        stats.lastScore = agent.score;
      }
      if (stats.states % 40 === 0) {
        const top = (state.leaderboard || []).map((r) => `${r.rank}.${r.name}:${r.score}`).join(' ');
        log(`[<-] state #${stats.states} game=${state.state} agentLen=${agent?.length} agentScore=${agent?.score} | ${top}`);
      }
      if (stats.states % 3 === 0 && agent && agent.alive) {
        const dir = chooseDirection(agent, state.foods || []);
        if (dir) {
          sendObj({ namespace: NAMESPACE, type: 'command', payload: { direction: dir } });
          stats.commandsSent += 1;
        }
      }
    } else if (data.type === 'response') {
      stats.responses += 1;
      if (data.ok) stats.responsesOk += 1;
      if (stats.responses === 1) log(`[<-] first response: ${text.slice(0, 140)}`);
    }
  };

  socket.on('data', (chunk) => {
    buffer = Buffer.concat([buffer, chunk]);
    const { frames, rest } = parseFrames(buffer);
    buffer = rest;
    for (const frame of frames) {
      if (frame.opcode === 0x9) {           // ping -> pong
        socket.write(Buffer.concat([Buffer.from([0x8a, frame.payload.length]), frame.payload]));
      } else if (frame.opcode === 0x8) {    // close
        socket.write(Buffer.from([0x88, 0x00]));
        socket.end();
      } else if (frame.opcode === 0x1 || frame.opcode === 0x0) {
        if (frame.opcode === 0x1 && frame.fin) {
          handleMessage(frame.payload.toString('utf8'));
        } else {
          fragmented = fragmented === null ? frame.payload : Buffer.concat([fragmented, frame.payload]);
          if (frame.fin) { handleMessage(fragmented.toString('utf8')); fragmented = null; }
        }
      }
    }
  });

  socket.on('close', () => log('[WS] game client disconnected'));
  socket.on('error', (err) => log('[WS] socket error:', err.message));
});

server.listen(PORT, () => log(`[sim] ESP32-CYD device simulator on ws://127.0.0.1:${PORT}`));

function summarize(exitCode) {
  const summary = {
    port: PORT,
    uptimeMs: Date.now() - stats.startedAt,
    ...stats
  };
  console.log('SUMMARY ' + JSON.stringify(summary));
  process.exit(exitCode);
}

process.on('SIGINT', () => summarize(0));
if (DURATION > 0) setTimeout(() => {
  const ok = stats.hellos > 0 && stats.states > 0;
  log(`[sim] duration reached, hellos=${stats.hellos} states=${stats.states} cmds=${stats.commandsSent} ok=${ok}`);
  summarize(ok ? 0 : 2);
}, DURATION);
