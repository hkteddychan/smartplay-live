/* =============================================================
 * SmartPLAY Live  ×  ESP32-CYD (ESP32-2432S028R, 320x240)
 * =============================================================
 * v3.0 — 放場通知器（release-only）
 *
 * 定位：呢塊板淨係答一條問題 ——「夜晚有冇場啱啱放咗出嚟？」
 *   有 → beep 一聲 + 螢幕顯示詳情
 *   冇 → 完全靜默
 * 想睇今晚有咩場 → 用網站 https://hkteddychan.github.io/smartplay-live/
 *
 * 兩條路收到放場通知（邊條都行，唔會重複）：
 *   1. PUSH：板子主動出連 VM（打穿 NAT，唔使 port forward），VM 一見到
 *            feed 有更新即刻推落嚟 → 幾乎即時
 *   2. POLL：自己 HTTPS GET changes-eve.json，每 1 分鐘一次（VM 唔在/推送
 *            斷咗嘅後備）
 *
 * Board notes (ESP32-2432S028R):
 *   display  : ILI9341, HSPI, MISO 12 / MOSI 13 / SCLK 14 / CS 15 / DC 2 / BL 21
 *   touch    : XPT2046 on its own VSPI bus (CS 33 / IRQ 36)
 *   rgb led  : 4 / 16 / 17, active LOW
 *   speaker  : onboard amp -> GPIO26 (I2S DAC left channel)
 *
 * Serial commands (115200):  b=beep  p=audio probe  r=refresh now
 *                            a=show alert  h=home  l=list releases  v=venue map
 * ============================================================= */
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <SPI.h>
#include <time.h>

#include "venue_font.h"
#include "cyd_text.h"
#include "cyd_audio.h"
#include "cyd_browse.h"

TFT_eSPI tft = TFT_eSPI();

/* ---------------- configuration ---------------- */
static const char *FEED_EVE = "https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json";
static const char *FEED_TODAY = "https://hkteddychan.github.io/smartplay-live/esp32/today.json";

static const unsigned long EVE_POLL_MS = 60UL * 1000UL;   // 每 1 分鐘 poll 一次

// Push channel — VM 端用 tools/cyd_push.py（行喺 AWS VM 上）
// VM_HOST 留空 = 淨係用 poll
#ifndef PUSH_HOST
#define PUSH_HOST ""
#endif
#ifndef PUSH_PORT
#define PUSH_PORT 9000
#endif
static const unsigned long PUSH_RETRY_MS = 5000;   // 斷線後 5 秒重連

// Which speaker path the alert beep uses (see cyd_audio.h).
#ifndef BEEP_PATH
#define BEEP_PATH AUDIO_PATH_AMP
#endif
#define BEEP_FREQ 1046   // C6
#define BEEP_MS 160
#define BEEP_AMP 4000    // DAC scale (quiet); PWM path uses this as duty

/* ---------------- geometry & colours ---------------- */
static const int SCR_W = 320, SCR_H = 240;
static const int HEADER_H = 30, FOOTER_H = 24;
static const int BODY_Y = HEADER_H;
static const int BODY_H = SCR_H - HEADER_H - FOOTER_H;

// RGB565 values (TFT_eSPI uses 16-bit colour)
#define C_BG ((uint16_t)0x10C8)
#define C_BAR ((uint16_t)0x342A)
#define C_CARD ((uint16_t)0x2644)
#define C_CARD_HOT ((uint16_t)0x1ED8)
#define C_TEXT ((uint16_t)0xFFFF)
#define C_DIM ((uint16_t)0xE6B8)
#define C_GOOD ((uint16_t)0x6730)
#define C_ACCENT ((uint16_t)0x07FF)
#define C_WARN ((uint16_t)0xFEE0)

/* ---------------- types ---------------- */
struct SportDef {
  const char *key;
  const char *zh;
};
static const SportDef SPORTS[] = {
    {"badminton", "羽毛球"},
    {"basketball", "籃球"},
    {"volleyball", "排球"},
    {"tennis", "網球"},
    {"turf-soccer-pitch", "草地足球"},
};
static const int N_SPORTS = 5;

static int sportIndex(const char *key) {
  for (int i = 0; i < N_SPORTS; i++)
    if (key && strcmp(key, SPORTS[i].key) == 0) return i;
  return -1;
}

// A release record, ready to put on screen.
struct Alert {
  char sport[16];      // 中文運動名
  char district[16];   // 區名（可以空）
  char venue[44];
  char facility[16];
  char date[12];
  uint16_t start, end; // minutes from midnight
  int oldC, newC;
};

#define MAX_ALERTS 4
#define MAX_VENUES 240

static Alert g_alerts[MAX_ALERTS];
static int g_alertCount = 0;
static int g_releaseTotal = 0;   // 開機至今收到幾多個放場

// venue -> district map（後備 poll 路径先用嚟查區名）
static char g_venueName[MAX_VENUES][44];
static char g_venueDistrict[MAX_VENUES][16];
static int g_venueCount = 0;

static char g_eveVersion[24] = "";
static char g_feedGen[24] = "";
static unsigned long g_lastEvePoll = 0;
static time_t g_lastPollAt = 0;
static bool g_pollOk = false;
static int g_pollFails = 0;
static bool g_timeValid = false;
static int g_hour = 0, g_min = 0;
static bool g_unread = false;

/* ---------------- screen state ---------------- */
enum Screen { SCR_HOME, SCR_ALERT };
static Screen g_screen = SCR_HOME;
static unsigned long g_alertAt = 0;
static bool g_dirty = true;
static String g_probeText;

/* ---------------- touch ---------------- */
static const int TOUCH_MIN_X = 200, TOUCH_MAX_X = 3900;
static const int TOUCH_MIN_Y = 200, TOUCH_MAX_Y = 3900;
#define XPT2046_CS 33
#define XPT2046_IRQ 36
SPIClass touchSPI(VSPI);
XPT2046_Touchscreen ts(XPT2046_CS, XPT2046_IRQ);

/* ---------------- rgb led ---------------- */
static const int LED_R = 4, LED_G = 16, LED_B = 17;
static void ledAll(uint8_t r, uint8_t g, uint8_t b) {  // active LOW
  digitalWrite(LED_R, r ? LOW : HIGH);
  digitalWrite(LED_G, g ? LOW : HIGH);
  digitalWrite(LED_B, b ? LOW : HIGH);
}
static void ledGreenBlink(int times) {
  for (int i = 0; i < times; i++) {
    ledAll(0, 1, 0);
    delay(90);
    ledAll(0, 0, 0);
    delay(90);
  }
}

/* ---------------- helpers ---------------- */
static void fmtTime(uint16_t minutes, char *buf, size_t n) {
  snprintf(buf, n, "%02d:%02d", minutes / 60, minutes % 60);
}

static void fmtClock(time_t t, char *buf, size_t n) {
  if (t <= 0) {
    snprintf(buf, n, "--:--:--");
    return;
  }
  struct tm lt;
  localtime_r(&t, &lt);
  snprintf(buf, n, "%02d:%02d:%02d", lt.tm_hour, lt.tm_min, lt.tm_sec);
}

static void rememberVenue(const char *venue, const char *district) {
  if (!venue || !*venue) return;
  for (int i = 0; i < g_venueCount; i++)
    if (strcmp(g_venueName[i], venue) == 0) return;
  if (g_venueCount >= MAX_VENUES) return;
  strncpy(g_venueName[g_venueCount], venue, sizeof(g_venueName[0]) - 1);
  strncpy(g_venueDistrict[g_venueCount], district ? district : "", sizeof(g_venueDistrict[0]) - 1);
  g_venueName[g_venueCount][sizeof(g_venueName[0]) - 1] = 0;
  g_venueDistrict[g_venueCount][sizeof(g_venueDistrict[0]) - 1] = 0;
  g_venueCount++;
}

static String venueDistrict(const char *venue) {
  for (int i = 0; i < g_venueCount; i++)
    if (strcmp(g_venueName[i], venue) == 0) return String(g_venueDistrict[i]);
  return String("");
}

/* ---------------- http ---------------- */
static WiFiClientSecure g_sec;

bool httpGet(const char *url, String &out) {
  if (WiFi.status() != WL_CONNECTED) return false;
  HTTPClient http;
  if (strncmp(url, "https://", 8) == 0) {
    g_sec.setInsecure();
    if (!http.begin(g_sec, url)) return false;
  } else {
    // plain http — a TLS client would fail the handshake
    if (!http.begin(url)) return false;
  }
  http.setTimeout(20000);
  http.setUserAgent("SmartPlayLive-ESP32/3.0");
  int code = http.GET();
  if (code != 200) {
    Serial.printf("[HTTP] %s -> %d\n", url, code);
    http.end();
    return false;
  }
  int len = http.getSize();
  out = "";
  if (len > 0) out.reserve(len);
  WiFiClient *stream = http.getStreamPtr();
  uint8_t buf[1024];
  while (http.connected() && (len > 0 || len == -1)) {
    size_t avail = stream->available();
    if (avail) {
      int c = stream->readBytes(buf, avail > sizeof(buf) ? sizeof(buf) : avail);
      out.concat((char *)buf, c);
      if (len > 0) len -= c;
    } else {
      delay(2);
    }
  }
  http.end();
  return true;
}

/* ---------------- 放場處理（push 同 poll 共用） ---------------- */
// push 同 poll 兩條路可能同時見到同一個放場事件 → 用呢個 key 去重，
// 避免響兩聲。
#define DEDUPE_N 16
static char g_seen[DEDUPE_N][72];
static int g_seenIdx = 0;

static void releaseKey(const char *sport, const char *venue, const char *date, int startMin,
                       int oldC, int newC, char *out, size_t n) {
  snprintf(out, n, "%s|%s|%s|%d|%d|%d", sport, venue, date, startMin, oldC, newC);
}

static bool seenBefore(const char *key) {
  for (int i = 0; i < DEDUPE_N; i++)
    if (g_seen[i][0] && strcmp(g_seen[i], key) == 0) return true;
  return false;
}

static void rememberSeen(const char *key) {
  strncpy(g_seen[g_seenIdx], key, sizeof(g_seen[0]) - 1);
  g_seen[g_seenIdx][sizeof(g_seen[0]) - 1] = 0;
  g_seenIdx = (g_seenIdx + 1) % DEDUPE_N;
}

static void handleRelease(const char *sportZh, const char *district, const char *venue,
                          const char *facility, const char *date, int startMin, int endMin,
                          int oldC, int newC) {
  char key[72];
  releaseKey(sportZh, venue, date, startMin, oldC, newC, key, sizeof(key));
  if (seenBefore(key)) {
    Serial.printf("[RELEASE] duplicate ignored: %s\n", key);
    return;
  }
  rememberSeen(key);

  if (g_alertCount >= MAX_ALERTS) {
    memmove(&g_alerts[0], &g_alerts[1], sizeof(Alert) * (MAX_ALERTS - 1));
    g_alertCount = MAX_ALERTS - 1;
  }
  Alert &a = g_alerts[g_alertCount++];
  strncpy(a.sport, sportZh ? sportZh : "", sizeof(a.sport) - 1);
  strncpy(a.district, district ? district : "", sizeof(a.district) - 1);
  strncpy(a.venue, venue ? venue : "", sizeof(a.venue) - 1);
  strncpy(a.facility, facility ? facility : "", sizeof(a.facility) - 1);
  strncpy(a.date, date ? date : "", sizeof(a.date) - 1);
  a.sport[sizeof(a.sport) - 1] = 0;
  a.district[sizeof(a.district) - 1] = 0;
  a.venue[sizeof(a.venue) - 1] = 0;
  a.facility[sizeof(a.facility) - 1] = 0;
  a.date[sizeof(a.date) - 1] = 0;
  a.start = (uint16_t)startMin;
  a.end = (uint16_t)endMin;
  a.oldC = oldC;
  a.newC = newC;

  g_releaseTotal++;
  char st[8], en[8];
  fmtTime(a.start, st, sizeof(st));
  fmtTime(a.end, en, sizeof(en));
  Serial.printf("[RELEASE] %s %s | %s %s-%s | %d->%d\n", a.sport, a.venue, a.facility, st, en,
                oldC, newC);
  beep();
  g_screen = SCR_ALERT;
  g_alertAt = millis();
  g_unread = true;
  ledGreenBlink(3);
  g_dirty = true;
}

/* ---------------- push channel（VM → 板子） ---------------- */
/* 協定（行式，方便 debug）：
 *   ESP32 → VM : "CYD PUSH 1\r\n"
 *   VM    → ESP32: "OK\r\n"
 *   VM    → ESP32: "RELEASE {json}\r\n"
 */
static WiFiClient g_push;
static bool g_pushConnected = false;
static unsigned long g_pushLastTry = 0;
static String g_pushBuf;

static void pushDrop() {
  if (g_pushConnected) Serial.println("[push] disconnected");
  g_push.stop();
  g_pushConnected = false;
  g_pushBuf = "";
}

static void pushConnect() {
  static int dialFails = 0;
  if (PUSH_HOST[0] == 0) return;
  if (WiFi.status() != WL_CONNECTED) return;
  if (millis() - g_pushLastTry < PUSH_RETRY_MS) return;
  // 唔好阻住 poll：poll 更加緊要
  if (millis() - g_lastEvePoll >= EVE_POLL_MS) return;
  g_pushLastTry = millis();

  // timeout 短啲，唔好因為 VM 唔喺度就成段時間冇反應
  if (!g_push.connect(PUSH_HOST, PUSH_PORT, 2000)) {
    if (dialFails == 0 || dialFails % 12 == 0)
      Serial.printf("[push] dial %s:%d FAIL (try %d)\n", PUSH_HOST, PUSH_PORT, dialFails + 1);
    dialFails++;
    g_pushConnected = false;
    return;
  }
  g_push.setNoDelay(true);
  g_push.print("CYD PUSH 1\r\n");

  // 等 VM 嘅 OK
  uint32_t t0 = millis();
  String ack = "";
  while (millis() - t0 < 3000) {
    if (g_push.available()) {
      char c = (char)g_push.read();
      if (c == '\n') break;
      if (c != '\r') ack += c;
    } else if (!g_push.connected()) {
      break;
    } else {
      delay(10);
    }
  }
  if (!g_push.connected() || !ack.startsWith("OK")) {
    Serial.printf("[push] bad ack '%s'\n", ack.c_str());
    g_push.stop();
    g_pushConnected = false;
    return;
  }
  dialFails = 0;
  g_pushConnected = true;
  Serial.printf("[push] connected to %s:%d\n", PUSH_HOST, PUSH_PORT);
  g_dirty = true;
}

static void pushHandleLine(const String &line) {
  if (!line.startsWith("RELEASE ")) return;
  String payload = line.substring(8);
  JsonDocument doc;
  if (deserializeJson(doc, payload)) {
    Serial.printf("[push] bad json: %s\n", payload.c_str());
    return;
  }
  const char *sportZh = doc["sport"] | "";
  const char *district = doc["district"] | "";
  const char *venue = doc["venue"] | "";
  const char *facility = doc["facility"] | "";
  const char *date = doc["date"] | "";
  int startMin = doc["start"] | 0, endMin = doc["end"] | 0;
  int oldC = doc["old"] | 0, newC = doc["new"] | 0;

  // VM 冇帶區名就自己查（後備 poll 路徑用）
  if (!district[0] && venue[0]) {
    String d = venueDistrict(venue);
    if (d.length()) {
      static char dbuf[16];
      strncpy(dbuf, d.c_str(), sizeof(dbuf) - 1);
      dbuf[sizeof(dbuf) - 1] = 0;
      district = dbuf;
    }
  }
  handleRelease(sportZh, district, venue, facility, date, startMin, endMin, oldC, newC);
}

static void pushPump() {
  if (!g_pushConnected) {
    pushConnect();
    return;
  }
  if (!g_push.connected()) {
    pushDrop();
    return;
  }
  while (g_push.available()) {
    char c = (char)g_push.read();
    if (c == '\n') {
      String line = g_pushBuf;
      g_pushBuf = "";
      line.trim();
      if (line.length()) pushHandleLine(line);
    } else if (c != '\r') {
      if (g_pushBuf.length() < 512) g_pushBuf += c;
    }
  }
}

/* ---------------- changes-eve.json poll（後備） ---------------- */
static String g_eveBody;

static void pollEve() {
  if (!httpGet(FEED_EVE, g_eveBody)) {
    Serial.println("[eve] fetch FAILED");
    g_pollFails++;
    g_dirty = true;
    return;
  }

  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, g_eveBody);
  if (err) {
    Serial.printf("[eve] parse error: %s\n", err.c_str());
    doc.clear();
    g_pollFails++;
    return;
  }

  const char *gen = doc["g"] | "";
  bool firstRun = (g_eveVersion[0] == 0);
  if (!firstRun && gen && strcmp(gen, g_eveVersion) == 0) {
    doc.clear();
    g_lastPollAt = time(nullptr);
    g_pollOk = true;
    g_pollFails = 0;
    return;  // feed 冇變
  }
  strncpy(g_eveVersion, gen ? gen : "", sizeof(g_eveVersion) - 1);
  g_eveVersion[sizeof(g_eveVersion) - 1] = 0;
  strncpy(g_feedGen, gen ? gen : "", sizeof(g_feedGen) - 1);
  g_feedGen[sizeof(g_feedGen) - 1] = 0;

  JsonObject sports = doc["sports"].as<JsonObject>();
  for (JsonPair kv : sports) {
    int si = sportIndex(kv.key().c_str());
    const char *sportZh = SPORTS[si < 0 ? 0 : si].zh;
    JsonArray changes = kv.value().as<JsonArray>();
    for (JsonVariant cv : changes) {
      JsonArray c = cv.as<JsonArray>();
      if (c.size() < 8) continue;
      const char *kind = c[5] | "";
      int oldC = c[6] | 0, newC = c[7] | 0;
      bool isRelease = (strcmp(kind, "chg") == 0 && newC > oldC) || (strcmp(kind, "new") == 0);
      if (!isRelease) continue;   // 被訂走 / 消失：唔 beep
      if (firstRun) continue;     // 第一輪只做 baseline

      const char *venue = c[1] | "";
      String d = venueDistrict(venue);
      handleRelease(sportZh, d.c_str(), venue, c[2] | "", c[0] | "", c[3] | 0, c[4] | 0, oldC, newC);
    }
  }
  doc.clear();
  g_lastPollAt = time(nullptr);
  g_pollOk = true;
  g_pollFails = 0;
  if (firstRun) Serial.println("[eve] first run - baseline only");
  g_dirty = true;
}

/* ---------------- 區名對照（後備 poll 路徑，需要時先載入） ---------------- */
static String g_todayBody;
static bool g_venueMapLoaded = false;

static void loadVenueMap() {
  if (g_venueMapLoaded) return;
  if (!httpGet(FEED_TODAY, g_todayBody)) {
    Serial.println("[venue] fetch FAILED");
    return;
  }
  JsonDocument doc;
  if (deserializeJson(doc, g_todayBody)) {
    doc.clear();
    return;
  }
  g_venueCount = 0;
  JsonObject sports = doc["sports"].as<JsonObject>();
  for (JsonPair kv : sports) {
    JsonObject sp = kv.value().as<JsonObject>();
    JsonArray venues = sp["v"].as<JsonArray>();
    JsonArray districts = sp["s"].as<JsonArray>();
    JsonArray rows = sp["r"].as<JsonArray>();
    for (JsonVariant rv : rows) {
      JsonArray row = rv.as<JsonArray>();
      if (row.size() < 6) continue;
      int vIdx = row[0] | 0, dIdx = row[1] | 0;
      if (vIdx < 0 || vIdx >= (int)venues.size()) continue;
      const char *district = (dIdx >= 0 && dIdx < (int)districts.size()) ? districts[dIdx] | "" : "";
      rememberVenue(venues[vIdx] | "", district);
    }
  }
  doc.clear();
  g_venueMapLoaded = true;
  Serial.printf("[venue] map loaded: %d venues, heap %u\n", g_venueCount, (unsigned)ESP.getFreeHeap());
}

/* ---------------- beep ---------------- */
static void beep() {
  bool ok = audioTone((AudioPath)BEEP_PATH, BEEP_FREQ, BEEP_MS, BEEP_AMP);
  if (!ok) Serial.println("[audio] tone FAILED (no speaker / wrong path?)");
}

/* ---------------- drawing ---------------- */
static void drawHeader(uint16_t barColor, uint16_t fg) {
  tft.fillRect(0, 0, SCR_W, HEADER_H, barColor);
  if (g_timeValid) {
    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", g_hour, g_min);
    tft.setTextColor(fg, barColor);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(buf, SCR_W - 8, 7, 2);
    tft.setTextDatum(TL_DATUM);
  }
  // wifi bars
  if (WiFi.status() == WL_CONNECTED) {
    int rssi = WiFi.RSSI();
    int bars = rssi > -60 ? 4 : (rssi > -70 ? 3 : (rssi > -80 ? 2 : 1));
    for (int i = 0; i < 4; i++) {
      uint16_t col = (i < bars) ? fg : C_DIM;
      tft.fillRect(SCR_W - 74 + i * 5, HEADER_H - 6 - (i + 1) * 4, 3, (i + 1) * 4, col);
    }
  }
}

static void drawFooter(const String &left, const String &right) {
  tft.fillRect(0, SCR_H - FOOTER_H, SCR_W, FOOTER_H, C_BAR);
  drawUTF8(left, 6, SCR_H - FOOTER_H + 4, C_DIM, C_BAR);
  int w = measureUTF8(right);
  drawUTF8(right, SCR_W - 6 - w, SCR_H - FOOTER_H + 4, C_DIM, C_BAR);
}

// 主畫面：等待放場 + 狀態
static void drawHome() {
  tft.fillScreen(C_BG);
  drawHeader(C_BAR, C_TEXT);

  tft.setTextColor(C_TEXT, C_BAR);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("放場通知器", 6, 7, 2);
  if (g_unread) tft.fillCircle(SCR_W - 86, 15, 5, C_GOOD);

  // push link state
  if (PUSH_HOST[0]) {
    if (g_pushConnected) {
      tft.fillCircle(SCR_W - 120, 15, 4, C_GOOD);
    } else {
      tft.fillCircle(SCR_W - 120, 15, 4, C_WARN);
    }
  }

  // 大字
  String big = "等待放場中";
  int bw = measureUTF8(big);
  drawUTF8(big, (SCR_W - bw) / 2, BODY_Y + 26, C_TEXT, C_BG);

  String sub = "晚上 6 點後 · 餘額增加或新時段";
  int sw = measureUTF8(sub);
  drawUTF8(sub, (SCR_W - sw) / 2, BODY_Y + 50, C_DIM, C_BG);

  // status lines
  int y = BODY_Y + 84;
  char line[64];
  tft.setTextColor(C_DIM, C_BG);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("last poll", 8, y, 2);
  fmtClock(g_lastPollAt, line, sizeof(line));
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(line, 92, y, 2);

  y += 22;
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("next poll", 8, y, 2);
  unsigned long since = millis() - g_lastEvePoll;
  unsigned long waitMs = EVE_POLL_MS - (since % EVE_POLL_MS);
  snprintf(line, sizeof(line), "%lus", waitMs / 1000);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(line, 92, y, 2);

  y += 22;
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("feed", 8, y, 2);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(g_feedGen, 92, y, 2);

  y += 22;
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("releases", 8, y, 2);
  snprintf(line, sizeof(line), "%d", g_releaseTotal);
  tft.setTextColor(C_GOOD, C_BG);
  tft.drawString(line, 92, y, 2);

  // footer
  String left = PUSH_HOST[0] ? (g_pushConnected ? "push 已連線" : "push 未連線") : "只用 poll";
  String right = g_pollOk ? "" : "poll 失敗";
  if (g_pollFails) {
    snprintf(line, sizeof(line), "fail %d", g_pollFails);
    right = line;
  }
  drawFooter(left, right);

  // audio probe banner
  if (g_probeText.length()) {
    int w = measureUTF8(g_probeText);
    int bx = (SCR_W - w) / 2;
    tft.fillRect(bx - 8, BODY_Y + 40, w + 16, 24, C_WARN);
    drawUTF8(g_probeText, bx, BODY_Y + 44, C_BG, C_WARN);
  }
}

static void drawAlert() {
  tft.fillScreen(C_BG);

  tft.fillRect(0, 0, SCR_W, HEADER_H, C_GOOD);
  drawUTF8("放場", 6, 7, C_BG, C_GOOD);
  tft.setTextColor(C_BG, C_GOOD);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("AVAILABLE", 48, 7, 2);
  if (g_timeValid) {
    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", g_hour, g_min);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(buf, SCR_W - 8, 7, 2);
    tft.setTextDatum(TL_DATUM);
  }

  int y = BODY_Y + 4;
  const int CARD_H = 54;
  int n = g_alertCount > 3 ? 3 : g_alertCount;
  for (int i = 0; i < n; i++) {
    const Alert &a = g_alerts[i];
    tft.fillRect(0, y, SCR_W, CARD_H, C_CARD_HOT);
    tft.fillRect(0, y, 4, CARD_H, C_GOOD);

    // line 1: sport · district   ......  old -> new
    String sport = String(a.sport);
    if (a.district[0]) sport += " · " + String(a.district);
    drawUTF8(sport, 10, y + 3, C_GOOD, C_CARD_HOT);

    String delta = String(a.oldC) + " → " + String(a.newC) + " 場";
    int dw = measureUTF8(delta);
    drawUTF8(delta, SCR_W - 10 - dw, y + 3, C_GOOD, C_CARD_HOT);

    // line 2: time range + facility
    char st[8], en[8];
    fmtTime(a.start, st, sizeof(st));
    fmtTime(a.end, en, sizeof(en));
    char range[24];
    snprintf(range, sizeof(range), "%s-%s", st, en);
    tft.setTextColor(C_TEXT, C_CARD_HOT);
    tft.setTextDatum(TL_DATUM);
    tft.drawString(range, 10, y + 20, 2);
    int rw = tft.textWidth(range, 2);
    if (a.facility[0]) drawUTF8(String(a.facility), 14 + rw, y + 20, C_DIM, C_CARD_HOT);

    // line 3: venue
    drawUTF8(fitUTF8(String(a.venue), SCR_W - 24), 10, y + 37, C_TEXT, C_CARD_HOT);
    y += CARD_H + 3;
  }

  String hint = "按一下畫面關閉";
  String cnt = "共 " + String(g_alertCount) + " 個新時段";
  drawFooter(hint, cnt);
}

/* ---------------- touch ---------------- */
static void handleTouch() {
  if (!ts.tirqTouched() || !ts.touched()) return;
  TS_Point p = ts.getPoint();
  (void)constrain(map(p.x, TOUCH_MIN_X, TOUCH_MAX_X, 0, SCR_W), 0, SCR_W - 1);
  (void)constrain(map(p.y, TOUCH_MIN_Y, TOUCH_MAX_Y, 0, SCR_H), 0, SCR_H - 1);
  if (g_screen == SCR_ALERT) {
    g_screen = SCR_HOME;
    g_unread = false;
    g_dirty = true;
  }
}

/* ---------------- clock ---------------- */
static void updateClock() {
  time_t now;
  time(&now);
  struct tm lt;
  localtime_r(&now, &lt);
  if (lt.tm_year + 1900 < 2024) {
    if (g_timeValid) { g_timeValid = false; g_dirty = true; }
    return;
  }
  if (!g_timeValid || lt.tm_hour != g_hour || lt.tm_min != g_min) {
    g_hour = lt.tm_hour;
    g_min = lt.tm_min;
    g_timeValid = true;
    g_dirty = true;
  }
}

/* ---------------- serial console ---------------- */
static void handleSerial() {
  if (!Serial.available()) return;
  String line = Serial.readStringUntil('\n');
  if (!line.length()) return;
  char c = line[0];
  if (c == 'b') {
    beep();
  } else if (c == 'p') {
    AudioPath paths[] = {AUDIO_PATH_AMP, AUDIO_PATH_AMP_ALT, AUDIO_PATH_PWM_26};
    const uint16_t freqs[] = {880, 1174, 1567};
    for (int i = 0; i < 3; i++) {
      AudioPath p = paths[i];
      Serial.printf("[audio] probing %s @ %uHz\n", audioPathName(p), freqs[i]);
      g_probeText = String(audioPathName(p)) + " " + String(freqs[i]) + "Hz";
      g_dirty = true;
      delay(300);
      audioTone(p, freqs[i], 250, p == AUDIO_PATH_PWM_26 ? 18 : 4000);
      delay(250);
    }
    g_probeText = "";
    g_dirty = true;
  } else if (c == 'r') {
    loadVenueMap();
    pollEve();
    browseFetch();
  } else if (c == 'a') {
    g_screen = SCR_ALERT;
    g_dirty = true;
  } else if (c == 'h') {
    g_screen = SCR_HOME;
    g_dirty = true;
  } else if (c == 'l') {
    Serial.printf("[releases] %d since boot, %d on screen\n", g_releaseTotal, g_alertCount);
    for (int i = 0; i < g_alertCount; i++) {
      const Alert &a = g_alerts[i];
      char st[8], en[8];
      fmtTime(a.start, st, sizeof(st));
      fmtTime(a.end, en, sizeof(en));
      Serial.printf("  %s %s %s-%s %s (%s) %d->%d\n", a.sport, a.venue, st, en, a.facility,
                    a.district, a.oldC, a.newC);
    }
  } else if (c == 'v') {
    Serial.printf("[venue] map %s (%d entries)\n", g_venueMapLoaded ? "loaded" : "not loaded",
                  g_venueCount);
  } else if (c == 'B') {
    Serial.printf("[browse] rows=%u venues=%u districts=%u dates=%u loaded=%d err='%s'\n",
                  g_browse.rowCount, g_browse.venueCount, g_browse.districtCount,
                  g_browse.dateCount, g_browse.loaded ? 1 : 0, g_browse.error);
    for (uint16_t i = 0; i < g_browse.rowCount && i < 5; i++) {
      const BrowseRow &r = g_browse.rows[i];
      Serial.printf("  row %u: s=%u v=%u d=%u %u-%u c=%u mask=%u (%s)\n", i, r.sIdx, r.vIdx,
                    r.dateIdx, r.start, r.end, r.courts, r.sportMask,
                    browseSportList(r.sportMask).c_str());
    }
    for (uint16_t i = 0; i < g_browse.districtCount && i < 4; i++)
      Serial.printf("  district %u: %s\n", i, g_browse.district[i]);
  } else {
    Serial.println("commands: b p r a h l v B");
  }
}

/* ---------------- setup ---------------- */
static void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("[WiFi] connecting to %s", WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(400);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED)
    Serial.printf(" OK IP=%s RSSI=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  else
    Serial.println(" FAILED");
}

void setup() {
  Serial.begin(115200);
  delay(200);

  pinMode(LED_R, OUTPUT);
  pinMode(LED_G, OUTPUT);
  pinMode(LED_B, OUTPUT);
  ledAll(0, 0, 0);

  tft.init();
  tft.setRotation(1);  // 320x240 landscape
  tft.fillScreen(C_BG);
  tft.setTextDatum(TL_DATUM);

  ts.begin();
  ts.setRotation(1);

  Serial.println("\n[SmartPLAY Live CYD] boot v3.0 — 放場通知器");
  Serial.printf("[push] host '%s:%d'\n", PUSH_HOST, PUSH_PORT);
  connectWiFi();
  configTime(8 * 3600, 0, "pool.ntp.org", "hk.pool.ntp.org");  // HKT

  g_lastEvePoll = 0;
  pollEve();   // 第一輪 = baseline，唔會誤嗶
  pushConnect();

  g_dirty = true;
}

void loop() {
  unsigned long now = millis();

  if (now - g_lastEvePoll >= EVE_POLL_MS) {
    g_lastEvePoll = now;
    if (WiFi.status() != WL_CONNECTED) connectWiFi();
    pollEve();
  }

  pushPump();
  handleSerial();
  handleTouch();
  updateClock();

  // 警報畫面自動返回（通知已經響過，唔好霸住個位）
  if (g_screen == SCR_ALERT && millis() - g_alertAt > 120000) {
    g_screen = SCR_HOME;
    g_dirty = true;
  }

  if (g_dirty) {
    g_dirty = false;
    if (g_screen == SCR_ALERT && g_alertCount > 0) drawAlert();
    else drawHome();
  }

  delay(100);
}
