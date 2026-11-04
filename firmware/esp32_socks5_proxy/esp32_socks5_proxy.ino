/*
 * ============================================================
 * ESP32-2432S028R (CYD) — SOCKS5 PROXY NODE
 * 目的：遠端機（AWS / VM）經這台裝置以住宅 IP 出去
 *
 * 協定：RFC 1928 SOCKS5 + RFC 1929 username/password auth
 *       只支援 CONNECT；ATYP IPv4 + domain（IPv6 → REP 0x08）
 * 加固：20s handshake timeout、120s idle timeout、
 *       pipelined frames 用 per-session buffer + shift 處理
 * 狀態屏：IP / port / 活躍 session 數（加 -D SOCKS_NO_SCREEN=1 可收埋）
 *
 * WiFi：
 *   1) build flags WIFI_SSID / WIFI_PASS（platformio.ini）
 *   2) NVS "cydmath" -> "ssid"/"pass"（chat 韌體存過）
 *
 * RFC 1929 憑證：platformio.ini 的 SOCKS_USER / SOCKS_PASS
 * 測試：curl --proxy "socks5://teddy:<pass>@<ip>:1080" http://example.com
 * ============================================================
 */

#include <WiFi.h>
#include <Preferences.h>

#ifndef SOCKS_NO_SCREEN
#include <TFT_eSPI.h>
#include "pikachu.h"
#endif

/* ---------------- build-flag defaults ---------------- */
#ifndef SOCKS_PORT
#define SOCKS_PORT 1080
#endif
#ifndef MAX_SESSIONS
#define MAX_SESSIONS 4
#endif
#ifndef SOCKS_USER
#define SOCKS_USER "teddy"
#endif
#ifndef SOCKS_PASS
#define SOCKS_PASS "pogo-teddy-2026"
#endif
#ifndef HANDSHAKE_TIMEOUT_MS
#define HANDSHAKE_TIMEOUT_MS 20000UL
#endif
#ifndef IDLE_TIMEOUT_MS
#define IDLE_TIMEOUT_MS 120000UL
#endif
#ifndef ALLOW_NO_AUTH
#define ALLOW_NO_AUTH 0
#endif

/* ---- Reverse relay（VM 由外面連唔入 NAT，所以 ESP32 主動出連）----
 * VM_HOST 留空 = 唔開 reverse relay（純 LAN SOCKS）
 * VM_PORT = VM 端 pool port；RELAY_WORKERS = 常備 reverse channel 數 */
#ifndef VM_HOST
#define VM_HOST ""
#endif
#ifndef VM_PORT
#define VM_PORT 9000
#endif
#ifndef RELAY_WORKERS
#define RELAY_WORKERS 2
#endif
#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASS
#define WIFI_PASS ""
#endif

/* CYD RGB LED（active LOW）*/
#define LED_R 4
#define LED_G 16
#define LED_B 17

/* ---------------- SOCKS phases ---------------- */
enum Phase : uint8_t { PH_NONE, PH_GREETING, PH_AUTH, PH_REQUEST, PH_RELAY };

struct Sess {
  WiFiClient cli;        // VM / client side（reverse 模式下係 VM 端 reverse channel）
  WiFiClient rem;        // proxy-dialled target
  uint8_t buf[512];      // 任情況下未消化嘅 handshake/pipelined bytes
  size_t   len = 0;
  Phase    phase = PH_NONE;
  uint32_t tOpen = 0;    // accept 時間（handshake timeout 用）
  uint32_t tLast = 0;    // 最後活動時間（idle timeout 用）
  bool     authOk = false;
  bool     reverse = false;  // 由 reversePump 開嘅 channel
};

static Sess      sess[MAX_SESSIONS];
static WiFiServer socksServer(SOCKS_PORT);
static uint32_t  totalConns = 0;
static char      lastTarget[80] = "-";

#ifndef SOCKS_NO_SCREEN
static TFT_eSPI  tft;
static uint32_t  lastPanelMs = 0;
#endif

/* ============================================================
   小工具
   ============================================================ */
static void ledSet(bool r, bool g, bool b) {
  digitalWrite(LED_R, r ? LOW : HIGH);
  digitalWrite(LED_G, g ? LOW : HIGH);
  digitalWrite(LED_B, b ? LOW : HIGH);
}

static void shiftFront(Sess &s, size_t k) {
  if (k >= s.len) { s.len = 0; return; }
  memmove(s.buf, s.buf + k, s.len - k);
  s.len -= k;
}

static void killSess(int i, const char *why) {
  Sess &s = sess[i];
  s.cli.stop();
  s.rem.stop();
  s.phase = PH_NONE;
  s.len = 0;
  Serial.printf("[-] slot %d closed (%s)\n", i, why);
}

/* 微小 reply helper */
static void replyBytes(Sess &s, const uint8_t *p, size_t n) {
  s.cli.write(p, n);
}

/* ============================================================
   Parse step 1：client greeting  [05 nmethods m1..mN]
   傳回：1 = 已回覆並進入下一段 / 0 = 要更多 bytes / -1 = 出錯要切線
   ============================================================ */
static int parseGreeting(Sess &s) {
  if (s.len < 2) return 0;
  if (s.buf[0] != 0x05) return -1;              // 唔係 SOCKS5
  uint8_t n = s.buf[1];
  size_t need = 2 + n;
  if (n == 0) return -1;
  if (s.len < need) return 0;

  bool wantUser = false, wantNone = false;
  for (uint8_t k = 0; k < n; k++) {
    if (s.buf[2 + k] == 0x02) wantUser = true;
    if (s.buf[2 + k] == 0x00) wantNone = true;
  }

#if ALLOW_NO_AUTH
  if (wantNone) {
    const uint8_t r[2] = {0x05, 0x00};
    replyBytes(s, r, 2); shiftFront(s, need);
    s.phase = PH_REQUEST; s.authOk = true;
    return 1;
  }
#endif
  if (wantUser) {
    const uint8_t r[2] = {0x05, 0x02};
    replyBytes(s, r, 2); shiftFront(s, need);
    s.phase = PH_AUTH;
    return 1;
  }

  const uint8_t r[2] = {0x05, 0xFF};            // 無可接受 method
  replyBytes(s, r, 2);
  return -1;
}

/* ============================================================
   RFC 1929 subnegotiation  [01 ulen user plen pass]
   + 反爆破（#3）：連續錯_pwd 就全站凍結 1.5 s
   ============================================================ */
static uint32_t lastAuthFail = 0;
static uint16_t authFails = 0;

static int parseAuth(Sess &s) {
  /* 冷卻期：唔理對方送咩，一律即刻拒（試密碼成本急升）*/
  if (authFails != 0 && millis() - lastAuthFail < 1500) {
    const uint8_t rej[2] = {0x01, 0x01};
    replyBytes(s, rej, 2);
    return -1;
  }

  if (s.len < 2) return 0;
  uint8_t ulen = s.buf[1];
  size_t need = 2 + ulen + 1;
  if (s.len < need) return 0;
  uint8_t plen = s.buf[2 + ulen];
  need += plen;
  if (s.len < need) return 0;

  static const char USER[] = SOCKS_USER;
  static const char PASS[] = SOCKS_PASS;
  bool ok = (ulen == strlen(USER)) && (plen == strlen(PASS)) &&
            memcmp(s.buf + 2, USER, ulen) == 0 &&
            memcmp(s.buf + 3 + ulen, PASS, plen) == 0;

  const uint8_t r[2] = {0x01, ok ? 0x00 : 0x01};
  replyBytes(s, r, 2);
  shiftFront(s, need);
  if (!ok) {
    authFails = (uint16_t)(authFails + 1);
    lastAuthFail = millis();
    Serial.printf("[slot] auth FAIL #%u (cooldown 1.5 s)\n", authFails);
    return -1;
  }
  authFails = 0;
  s.authOk = true;
  s.phase = PH_REQUEST;
  return 1;
}

/* ============================================================
   DNS 快取（#1）：反覆連同一 host（PTC 類）唔使每次網上查
   ============================================================ */
struct DnsEnt {
  char      host[48];
  IPAddress ip;
  uint32_t  tMs;
};
static DnsEnt dnsCache[4];
#define DNS_TTL_MS 60000UL

static bool dnsLookup(const char *host, IPAddress &ip) {
  uint32_t now = millis();
  int slot = -1, oldest = 0;
  for (int i = 0; i < 4; i++) {
    if (dnsCache[i].host[0] == 0) { if (slot < 0) slot = i; continue; }
    if (dnsCache[i].tMs < dnsCache[oldest].tMs) oldest = i;
    if (now - dnsCache[i].tMs < DNS_TTL_MS && strcmp(dnsCache[i].host, host) == 0) {
      ip = dnsCache[i].ip;                      // cache hit
      return true;
    }
  }
  int rc = WiFi.hostByName(host, ip);
  if (rc != 1) return false;
  DnsEnt &e = dnsCache[slot >= 0 ? slot : oldest];
  strncpy(e.host, host, sizeof(e.host) - 1);
  e.host[sizeof(e.host) - 1] = 0;
  e.ip = ip; e.tMs = now;
  Serial.printf("[dns] %s -> %s%s\n", host, ip.toString().c_str(),
                slot >= 0 ? "" : " (evict)");
  return true;
}

/* ============================================================
   SOCKS request  [05 cmd rsv atyp dst port]
   ============================================================ */
static int parseRequest(Sess &s) {
  if (s.len < 5) return 0;
  if (s.buf[0] != 0x05) return -1;
  uint8_t cmd = s.buf[1], atyp = s.buf[3];
  uint8_t repFail[10] = {0x05, 0x01, 0x00, 0x01, 0,0,0,0, 0,0};  // 作廢時用

  if (cmd != 0x01) {                            // 只支援 CONNECT
    repFail[1] = 0x07;
    replyBytes(s, repFail, 10);
    return -1;
  }

  char host[64];
  uint16_t port = 0;
  size_t consumed = 0;

  if (atyp == 0x01) {                           // IPv4（4 + 4 + 2 = 10）
    if (s.len < 10) return 0;
    snprintf(host, sizeof(host), "%u.%u.%u.%u",
             s.buf[4], s.buf[5], s.buf[6], s.buf[7]);
    port  = ((uint16_t)s.buf[8] << 8) | s.buf[9];
    consumed = 10;
  } else if (atyp == 0x03) {                    // domain（5 + dlen + 2）
    uint8_t dl = s.buf[4];
    if (dl == 0) return -1;
    if (s.len < (size_t)(dl + 7)) return 0;
    memcpy(host, s.buf + 5, dl); host[dl] = 0;
    port  = ((uint16_t)s.buf[5 + dl] << 8) | s.buf[6 + dl];
    consumed = 5 + dl + 2;
  } else {                                      // IPv6 / 未知 → 0x08
    repFail[1] = 0x08;
    replyBytes(s, repFail, 10);
    return -1;
  }

  /* 連出去：先 DNS（帶快取），再 TCP connect */
  IPAddress target;
  if (!dnsLookup(host, target)) {
    repFail[1] = 0x04;                            // host unreachable (DNS fail)
    replyBytes(s, repFail, 10);
    Serial.printf("[%u->] %s:%u -> DNS fail\n", (unsigned)(&s - sess), host, port);
    return -1;
  }
  s.rem.stop();
  uint32_t t0 = millis();
  bool ok = s.rem.connect(target, port);
  uint32_t dt = millis() - t0;

  shiftFront(s, consumed);
  Serial.printf("[%u->] %s:%u -> %s (%lu ms)\n",
                (unsigned)(&s - sess), host, port,
                ok ? "OK" : "FAIL", (unsigned long)dt);

  /* 更新最後 target（狀態屏）*/
  snprintf(lastTarget, sizeof(lastTarget), "%s:%u", host, port);

  if (ok) {
    IPAddress lip = WiFi.localIP();
    uint8_t r[10] = {0x05, 0x00, 0x00, 0x01,
                     lip[0], lip[1], lip[2], lip[3],
                     (uint8_t)(SOCKS_PORT >> 8), (uint8_t)(SOCKS_PORT & 0xFF)};
    replyBytes(s, r, 10);
    s.phase = PH_RELAY;
    s.tLast = millis();
    /* pipelined：greeting+auth+request 同 payload 一齊嚟嘅 case */
    if (s.len) { s.rem.write(s.buf, s.len); s.len = 0; }
    return 1;
  }
  repFail[1] = 0x05;                            // connection refused
  replyBytes(s, repFail, 10);
  return -1;
}

/* ============================================================
   Handshake pump：盡量消化 buffer，一 staging 完就走 relay
   ============================================================ */
static void pumpHandshake(int i) {
  Sess &s = sess[i];
  for (uint8_t guard = 0; guard < 8; guard++) {
    int r = 0;
    switch (s.phase) {
      case PH_GREETING: r = parseGreeting(s); break;
      case PH_AUTH:     r = parseAuth(s);     break;
      case PH_REQUEST:  r = parseRequest(s);  break;
      default:          return;
    }
    if (r == 0) return;              // 要更多 bytes
    if (r < 0)  { killSess(i, "handshake error"); return; }
    if (s.phase == PH_RELAY) return; // parseRequest 已 flush leftover
  }
  /* 唔應該到呢度；出問題就切 */
  killSess(i, "handshake stuck");
}

/* ============================================================
   Relay：雙向 pump + idle timeout
   ============================================================ */
/* relay 大 buffer（#4）：RAM 只用咗 16%，簡單加一把提升吞吐 */
static uint8_t rbuf[4096];

static bool pumpOne(WiFiClient &from, WiFiClient &to) {
  bool acted = false;
  while (from.available()) {
    int n = from.read(rbuf, sizeof(rbuf));
    if (n <= 0) break;
    size_t w = to.write(rbuf, (size_t)n);
    if (w != (size_t)n) break;       // 對面 buffer 滿；下個 loop 再送
    acted = true;
  }
  return acted;
}

static void pumpRelay(int i) {
  Sess &s = sess[i];
  bool acted = false;
  if (s.len) { s.rem.write(s.buf, s.len); s.len = 0; }  // backlog（保安）
  acted |= pumpOne(s.cli, s.rem);
  acted |= pumpOne(s.rem, s.cli);
  if (acted) s.tLast = millis();

  bool cliDead = !s.cli.connected() && !s.cli.available();
  bool remDead = !s.rem.connected() && !s.rem.available();
  if (cliDead || remDead) { killSess(i, cliDead ? "client EOF" : "remote EOF"); return; }
  if (millis() - s.tLast > IDLE_TIMEOUT_MS) killSess(i, "idle timeout");
}

/* ============================================================
   Accept 新 client
   ============================================================ */
static void acceptNew(WiFiClient nc) {
  int slot = -1;
  for (int i = 0; i < MAX_SESSIONS; i++) if (sess[i].phase == PH_NONE) { slot = i; break; }
  if (slot < 0) { Serial.println("[!] busy, rejected new client"); nc.stop(); return; }

  Sess &s = sess[slot];
  s.cli = nc;
  s.cli.setNoDelay(true);
  s.rem.stop();
  s.len = 0;
  s.phase = PH_GREETING;
  s.authOk = false;
  s.reverse = false;
  s.tOpen = s.tLast = millis();
  totalConns++;
  Serial.printf("[+] slot %d client %s:%u\n", slot,
                s.cli.remoteIP().toString().c_str(), (unsigned)s.cli.remotePort());
}

/* ============================================================
   Reverse relay worker：ESP32 主動出連 VM 打穿 NAT
   協定：連上後送 "CYD RELAY 1\r\n"，VM 回 "OK\r\n" 就當 SOCKS 管道用
   ============================================================ */
#define VM_HOST_LEN (sizeof(VM_HOST) - 1)   // "" 時 0，唔開 reverse relay

static void reversePump() {
#if RELAY_WORKERS > 0
  if (VM_HOST_LEN == 0) return;
  if (WiFi.status() != WL_CONNECTED) return;
  static uint32_t lastTry = 0;
  if (millis() - lastTry < 5000) return;

  int revActive = 0, free = -1;
  for (int i = 0; i < MAX_SESSIONS; i++) {
    if (sess[i].phase == PH_NONE) { if (free < 0) free = i; }
    else if (sess[i].reverse) revActive++;
  }
  if (revActive >= RELAY_WORKERS || free < 0) return;
  lastTry = millis();

  Sess &s = sess[free];
  WiFiClient nc;
  uint32_t t0 = millis();
  if (!nc.connect(VM_HOST, VM_PORT)) {
    Serial.printf("[relay] dial %s:%u FAIL\n", VM_HOST, (unsigned)VM_PORT);
    return;
  }
  nc.setNoDelay(true);

  /* greeting + 等 VM OK ack（最多 3 s，阻塞可以接受：5 s 一次）*/
  nc.write("CYD RELAY 1\r\n");
  uint32_t tw = millis();
  String ack = "";
  while (millis() - tw < 3000) {
    if (nc.available() || !nc.connected()) break;
    delay(20);
  }
  while (nc.available()) {
    char c = (char)nc.read();
    if (c == '\n') break;
    if (c != '\r') ack += c;
  }
  if (!nc.connected() || !ack.startsWith("OK")) {
    Serial.printf("[relay] dial ok but bad ack '%s'\n", ack.c_str());
    nc.stop();
    return;
  }

  s.cli = nc;
  s.cli.setNoDelay(true);
  s.rem.stop();
  s.len = 0;
  s.phase = PH_GREETING;
  s.authOk = false;
  s.reverse = true;
  s.tOpen = s.tLast = millis();
  Serial.printf("[relay] channel %d wired to %s:%u (%lu ms)\n", free, VM_HOST,
                (unsigned)VM_PORT, (unsigned long)(millis() - t0));
#endif
}

/* ============================================================
   狀態屏 v2 — Pikachu + ✓/✗ 狀態（用戶要求嘅呈現設計）
   ONLINE ：Pika 兩幀跳動 + 綠色 tick
   OFFLINE：灰 Pika + 紅 cross
   全屏重繪只在「狀態/數據」變時；動畫幀只重繪 icon cell（防閃爍）
   ============================================================ */
#ifndef SOCKS_NO_SCREEN
#define COL_OK   0x07E0    // 綠
#define COL_BAD  0xF810    // 紅
#define PIKA_X   14
#define PIKA_Y   40
#define PIKA_SCL 2

static void drawPika(bool online, uint8_t frame) {
  const uint16_t *src = online ? (frame & 1 ? pik_f2 : pik_f1) : pik_grey;
  tft.fillRect(PIKA_X, PIKA_Y, PIK_W * PIKA_SCL, PIK_H * PIKA_SCL, TFT_BLACK);
  for (int r = 0; r < PIK_H; r++)
    for (int c = 0; c < PIK_W; c++) {
      uint16_t col = src[r * PIK_W + c];
      if (col)                                  // 0 = 背景 skip
        tft.fillRect(PIKA_X + c * PIKA_SCL, PIKA_Y + r * PIKA_SCL,
                     PIKA_SCL, PIKA_SCL, col);
    }
}

static void drawTick(int x, int y) {
  for (int o = 0; o < 3; o++) {                 // 粗 3px 嘅 ✓
    tft.drawLine(x + o, y + 8, x + 4 + o, y + 12, COL_OK);
    tft.drawLine(x + 4 + o, y + 12, x + 11 + o, y + 2, COL_OK);
  }
}

static void drawCross(int x, int y) {
  for (int o = 0; o < 2; o++) {                 // 粗 4px 嘅 ✗
    tft.drawLine(x + o, y, x + 11, y + 11 - o, COL_BAD);
    tft.drawLine(x + 11, y + o, x + o, y + 11 - o, COL_BAD);
  }
}

static void drawPanel(bool full) {
  static char prevSig[100] = "";
  static uint8_t lastFrame = 99;
  char sig[100];

  bool online = (WiFi.status() == WL_CONNECTED);
  uint8_t frame = online ? (uint8_t)((millis() / 500) & 1) : 0;

  int revActive = 0;
  for (int i = 0; i < MAX_SESSIONS; i++)
    if (sess[i].phase != PH_NONE && sess[i].reverse) revActive++;
  int used = 0;
  for (int i = 0; i < MAX_SESSIONS; i++) if (sess[i].phase != PH_NONE) used++;

  snprintf(sig, sizeof(sig), "%d|%d|%d|%lu|%s|%s", online, used, revActive,
           (unsigned long)totalConns, lastTarget,
           WiFi.localIP().toString().c_str());

  bool sameContent = !full && strcmp(sig, prevSig) == 0;
  if (sameContent && frame == lastFrame) return;      // 完全無變化

  if (sameContent) {
    /* 只有動畫幀變：只重畫 icon cell */
    lastFrame = frame;
    drawPika(true, frame);
    return;
  }
  strncpy(prevSig, sig, sizeof(prevSig) - 1);
  lastFrame = frame;

  /* ---------- 全屏重繪 ---------- */
  uint16_t bar = online ? 0x0251 : 0x6000;            // 深綠 / 深紅
  tft.fillScreen(TFT_BLACK);
  tft.fillRect(0, 0, tft.width(), 26, bar);
  tft.setTextDatum(ML_DATUM);
  tft.setTextColor(TFT_WHITE, bar);
  tft.drawString("CYD SOCKS5", 10, 13, 2);
  char right[40];
  snprintf(right, sizeof(right), "S %d/%d   V %d/%d", used, MAX_SESSIONS,
           revActive, RELAY_WORKERS);
  tft.setTextDatum(MR_DATUM);
  tft.drawString(right, tft.width() - 10, 13, 2);
  tft.setTextDatum(TL_DATUM);

  /* Pika + ✓/✗ + 大狀態字 */
  drawPika(online, frame);
  if (online) drawTick(PIKA_X + PIK_W * PIKA_SCL + 10, PIKA_Y + 14);
  else        drawCross(PIKA_X + PIK_W * PIKA_SCL + 10, PIKA_Y + 14);
  tft.setTextColor(online ? COL_OK : COL_BAD, TFT_BLACK);
  tft.drawString(online ? "ONLINE" : "OFFLINE", 96, 44, 4);
  tft.setTextColor(0x8410, TFT_BLACK);
  tft.drawString(online ? "residential egress ok" : "wifi down, retrying...",
                 96, 74, 2);

  /* 資訊區（兩欄 label=value）*/
  const int lx = 12, vx = 66, ROW = 20;
  int y = 108;
  const char *keys[5] = {"IP", "VM", "SESS", "TOTAL", "LAST"};
  String vals[5] = {
    WiFi.localIP().toString(),
#if RELAY_WORKERS > 0
    (VM_HOST_LEN ? String(revActive) + "/" + String(RELAY_WORKERS)
     + " " + VM_HOST + ":" + String(VM_PORT) : String("off (LAN only)")),
#else
    String("off (LAN only)"),
#endif
    String(used) + "/" + String(MAX_SESSIONS),
    String((unsigned long)totalConns),
    String(lastTarget),
  };
  for (int i = 0; i < 5; i++) {
    tft.setTextColor(0x9FFC, TFT_BLACK);
    tft.drawString(keys[i], lx, y, 2);
    tft.setTextColor(TFT_WHITE, TFT_BLACK);
    tft.drawString(vals[i], vx, y, 2);
    y += ROW;
  }

  /* 底部 */
  tft.setTextColor(0x630C, TFT_BLACK);
  tft.drawString("RFC1929 auth", 12, tft.height() - 22, 2);
  tft.drawString("DNS cache 60 s", 150, tft.height() - 22, 2);
}

static void panelTick() {
  static uint32_t lastMs = 0;
  if (millis() - lastMs > 250) { lastMs = millis(); drawPanel(false); }
}
#endif

/* ============================================================
   WiFi 連線：build flag 先，冇就 NVS
   ============================================================ */
static bool wifiConnect(bool &ledOK) {
  String ssid = WIFI_SSID, pass = WIFI_PASS;
  bool fromNVS = false;

  if (ssid.length() == 0) {
    Preferences prefs;
    prefs.begin("cydmath", true);
    ssid  = prefs.getString("ssid", "");
    pass  = prefs.getString("pass", "");
    prefs.end();
    fromNVS = ssid.length() > 0;
  }

  if (ssid.length() == 0) {
    Serial.println("[WiFi] no credentials in build flags or NVS — cannot connect");
    return false;
  }

  Serial.printf("[WiFi] connecting to '%s'%s...\n", ssid.c_str(), fromNVS ? " (NVS)" : "");
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);                         // proxy 要低 latency
  WiFi.begin(ssid.c_str(), pass.c_str());

  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
    Serial.print(WiFi.status() == WL_NO_SSID_AVAIL ? "x" : ".");
    ledSet(false, false, (millis() / 250) & 1);
    if (millis() - t0 > 25000) {
      Serial.println("\n[WiFi] join timeout");
      return false;
    }
  }
  ledOK = true;
  Serial.printf("\n[WiFi] connected, IP %s  rssi %d\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI());
  return true;
}

/* ============================================================
   setup / loop
   ============================================================ */
void setup() {
  Serial.begin(115200);
  delay(120);

  /* 清走舊 chat 韌體留低嘅 NVS key（proxy 只用 ssid/pass）*/
  {
    Preferences p;
    if (p.begin("cydmath", false)) {
      p.remove("chatlog"); p.remove("model");
      p.remove("persona"); p.remove("bright");
      p.end();
    }
  }

  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  ledSet(false, false, true);                   // 藍 = boot 中

#ifndef SOCKS_NO_SCREEN
  tft.init();
  tft.setRotation(1);
  tft.fillScreen(TFT_BLACK);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString("SOCKS5 proxy booting...", 8, 8, 2);
#endif

  Serial.printf("\n[SOCKS] ESP32 CYD proxy node, RFC1929 auth slot=%d port=%d\n",
                MAX_SESSIONS, SOCKS_PORT);

  bool ok = false;
  if (!wifiConnect(ok)) {
    Serial.println("[WiFi] retry every 10 s");
    ledSet(true, false, false);                 // 紅 = no wifi
    while (!ok) {
      delay(10000);
      wifiConnect(ok);
      ledSet(true, false, false);
    }
  }

  socksServer.begin();
  socksServer.setNoDelay(true);
  ledSet(false, true, false);                   // 綠 = ready
  Serial.printf("[SOCKS] listening on :%u, user='%s'\n", (unsigned)SOCKS_PORT, SOCKS_USER);

#ifndef SOCKS_NO_SCREEN
  drawPanel(true);
#endif
}

void loop() {
  /* accept */
  WiFiClient nc = socksServer.available();
  if (nc && nc.connected()) acceptNew(nc);

  /* reverse relay：維持 RELAY_WORKERS 條出連 VM 嘅 channel */
  reversePump();

  /* 每個 session */
  for (int i = 0; i < MAX_SESSIONS; i++) {
    Sess &s = sess[i];
    if (s.phase == PH_NONE) continue;

    /* 新 bytes 到 buffer（handshake 階段先入 buffer）*/
    if (s.phase != PH_RELAY && s.cli.available() && s.len < sizeof(s.buf)) {
      int n = s.cli.read(s.buf + s.len, sizeof(s.buf) - s.len);
      if (n > 0) s.len += (size_t)n;
      s.tLast = millis();
    }
    /* buffer 滿仍無法 parse（要更多 bytes）→ protocol 出事 */
    if (s.len >= sizeof(s.buf) && s.phase != PH_RELAY) {
      pumpHandshake(i);
      if (s.len >= sizeof(s.buf) && s.phase != PH_RELAY) { killSess(i, "buffer full"); continue; }
    }

    if (s.phase != PH_RELAY) {
      /* reverse channel 得 WAITING 期間耐啲（池等客）；正常 handshake 20 s */
      uint32_t hto = s.reverse ? IDLE_TIMEOUT_MS : HANDSHAKE_TIMEOUT_MS;
      if (millis() - s.tOpen > hto) { killSess(i, "handshake timeout"); continue; }
      pumpHandshake(i);
    } else {
      pumpRelay(i);
    }
  }

#ifndef SOCKS_NO_SCREEN
  panelTick();          // 動畫/重繪統一入口（250 ms 步進）
#endif

  /* LED：有活躍 session 閃藍，否則綠 */
  static uint32_t lastLedMs = 0;
  if (millis() - lastLedMs > 500) {
    lastLedMs = millis();
    bool active = false;
    for (int i = 0; i < MAX_SESSIONS; i++) if (sess[i].phase != PH_NONE) active = true;
    bool blink = active && ((millis() / 500) & 1);
    ledSet(false, !active, blink);
  }

  /* WiFi 斷線自癒 */
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] lost, reconnecting");
    ledSet(true, false, false);
    socksServer.stop();
    // wait
    while (WiFi.status() != WL_CONNECTED) {
      delay(2000);
      WiFi.disconnect();
      WiFi.reconnect();
      if (WiFi.status() == WL_CONNECTED) break;
    }
    socksServer.begin();
    socksServer.setNoDelay(true);
    ledSet(false, true, false);
  }
}
