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
 *   1. POLL：自己 HTTPS GET changes-eve.json，每 1 分鐘一次
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
#include <ArduinoOTA.h>
#include <esp_ota_ops.h>
#include <esp_task_wdt.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <SPI.h>
#include <Preferences.h>
#include <time.h>

#include "venue_font.h"
#include "cyd_theme.h"
#include "cyd_text.h"
#include "cyd_audio.h"
#include "cyd_browse.h"
#include "cyd_notify.h"
#include "cyd_ota_pull.h"
#include "cyd_report.h"

TFT_eSPI tft = TFT_eSPI();

/* ---------------- configuration ---------------- */
static const char *FEED_EVE = "https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json";
static const char *FEED_TODAY = "https://hkteddychan.github.io/smartplay-live/esp32/today.json";

static const unsigned long EVE_POLL_MIN_MS = 60UL * 1000UL;
static const unsigned long EVE_POLL_MAX_MS = 90UL * 1000UL;
static unsigned long g_evePollInterval = 60UL * 1000UL;   // 每次 poll 後隨機 60–90s

// Which speaker path the alert beep uses (see cyd_audio.h).
#ifndef BEEP_PATH
#define BEEP_PATH AUDIO_PATH_AMP
#endif
#define BEEP_FREQ 1046   // C6
#define BEEP_MS 160
#define BEEP_AMP 4000    // DAC scale (quiet); PWM path uses this as duty

/* ---------------- geometry & colours ---------------- */
// see cyd_theme.h (shared with the browse UI)

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
#define MAX_VENUES 160

static Alert g_alerts[MAX_ALERTS];
static int g_alertCount = 0;
static int g_releaseTotal = 0;   // 開機至今收到幾多個放場

// venue -> district map（後備 poll 路径先用嚟查區名）
static char g_venueName[MAX_VENUES][44];
static char g_venueDistrict[MAX_VENUES][16];
static int g_venueCount = 0;
static bool g_venueMapLoaded = false;

static char g_eveVersion[24] = "";
static char g_feedGen[24] = "";
static unsigned long g_lastEvePoll = 0;
static time_t g_lastPollAt = 0;
static bool g_pollOk = false;
static int g_pollFails = 0;
static bool g_timeValid = false;
static int g_hour = 0, g_min = 0;
static bool g_unread = false;
// 📜 記錄 chip flash（touch 回饋用局部重繪）
static bool g_histChipFlash = false;
static unsigned long g_histFlashUntil = 0;
static bool g_homeFullDrawn = false;   // 首繪用全頁，之後只局部更新
static bool g_homeNeedsFull = true;    // true = 要全頁重繪；false = 只局部刷新

/* ---------------- screen state ---------------- */
enum Screen { SCR_HOME, SCR_ALERT };
enum Page { PAGE_NOTIFY, PAGE_BROWSE, PAGE_HISTORY };
static Screen g_screen = SCR_HOME;
static Page g_page = PAGE_NOTIFY;
static Page g_returnPage = PAGE_NOTIFY;   // 警報蓋住邊個頁，收完返返去
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

/* ---------------- WiFi credentials (from secrets.h or defaults) ---------------- */
#if __has_include("secrets.h")
#include "secrets.h"
#ifndef WIFI_SSID_1
#define WIFI_SSID_1 "REDACTED"
#endif
#ifndef WIFI_PASS_1
#define WIFI_PASS_1 "REDACTED"
#endif
#ifndef WIFI_SSID_2
#define WIFI_SSID_2 "REDACTED"
#endif
#ifndef WIFI_PASS_2
#define WIFI_PASS_2 "teddychan"
#endif
#else
#define WIFI_SSID_1 "REDACTED"
#define WIFI_PASS_1 "REDACTED"
#define WIFI_SSID_2 "REDACTED"
#define WIFI_PASS_2 "teddychan"
#endif
// ---- NVS WiFi credential storage ----
// On first boot, compiled defaults are stored in NVS.
// Subsequent boots read from NVS (allows credentials to be updated without reflash).
static Preferences wifiPrefs;
static char nvsSsid1[32] = WIFI_SSID_1;
static char nvsPass1[64] = WIFI_PASS_1;
static char nvsSsid2[32] = WIFI_SSID_2;
static char nvsPass2[64] = WIFI_PASS_2;

static void loadWifiCredsFromNVS() {
    wifiPrefs.begin("wifi", true);
    String s1 = wifiPrefs.getString("ssid1", WIFI_SSID_1);
    String p1 = wifiPrefs.getString("pass1", WIFI_PASS_1);
    String s2 = wifiPrefs.getString("ssid2", WIFI_SSID_2);
    String p2 = wifiPrefs.getString("pass2", WIFI_PASS_2);
    bool initialized = wifiPrefs.getBool("init", false);
    wifiPrefs.end();
    strncpy(nvsSsid1, s1.c_str(), sizeof(nvsSsid1) - 1);
    nvsSsid1[sizeof(nvsSsid1) - 1] = 0;
    strncpy(nvsPass1, p1.c_str(), sizeof(nvsPass1) - 1);
    nvsPass1[sizeof(nvsPass1) - 1] = 0;
    strncpy(nvsSsid2, s2.c_str(), sizeof(nvsSsid2) - 1);
    nvsSsid2[sizeof(nvsSsid2) - 1] = 0;
    strncpy(nvsPass2, p2.c_str(), sizeof(nvsPass2) - 1);
    nvsPass2[sizeof(nvsPass2) - 1] = 0;
    if (!initialized) {
        // First boot: store compiled defaults to NVS
        wifiPrefs.begin("wifi", false);
        wifiPrefs.putString("ssid1", WIFI_SSID_1);
        wifiPrefs.putString("pass1", WIFI_PASS_1);
        wifiPrefs.putString("ssid2", WIFI_SSID_2);
        wifiPrefs.putString("pass2", WIFI_PASS_2);
        wifiPrefs.putBool("init", true);
        wifiPrefs.end();
        Serial.println("[WiFi] NVS first-boot migration done");
    }
    Serial.printf("[WiFi] creds from NVS: %s / %s\n", nvsSsid1, nvsSsid2);
}
struct WifiNet { const char *ssid; const char *pass; };
static const WifiNet WIFI_NETS[] = {
    {nvsSsid1, nvsPass1},
    {nvsSsid2, nvsPass2},
};
static const int N_WIFI_NETS = sizeof(WIFI_NETS) / sizeof(WIFI_NETS[0]);
static char g_wifiSsid[32] = "";

static void connectWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;
    WiFi.mode(WIFI_STA);
    WiFi.disconnect(true);
    delay(100);

    // Scan available networks first
    Serial.println("[WiFi] scanning...");
    int n = WiFi.scanNetworks();
    Serial.printf("[WiFi] found %d networks\n", n);

    // Try each configured network in priority order; only connect if seen in scan
    for (int i = 0; i < N_WIFI_NETS; i++) {
        bool seen = false;
        for (int j = 0; j < n; j++) {
            if (strcmp(WiFi.SSID(j).c_str(), WIFI_NETS[i].ssid) == 0) { seen = true; break; }
        }
        if (!seen) {
            Serial.printf("[WiFi] '%s' not in range, skip\n", WIFI_NETS[i].ssid);
            continue;
        }
        Serial.printf("[WiFi] trying %s\n", WIFI_NETS[i].ssid);
        WiFi.begin(WIFI_NETS[i].ssid, WIFI_NETS[i].pass);
        unsigned long t0 = millis();
        while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) {
            delay(400);
         esp_task_wdt_reset();
            Serial.print(".");
        }
        Serial.println();
        if (WiFi.status() == WL_CONNECTED) {
            strncpy(g_wifiSsid, WIFI_NETS[i].ssid, sizeof(g_wifiSsid) - 1);
            g_wifiSsid[sizeof(g_wifiSsid) - 1] = 0;
            Serial.printf("[WiFi] connected to %s IP=%s RSSI=%d\n", g_wifiSsid,
                          WiFi.localIP().toString().c_str(), WiFi.RSSI());
            return;
        }
        Serial.printf("[WiFi] %s FAILED\n", WIFI_NETS[i].ssid);
    }
    Serial.println("[WiFi] all networks failed");
}

/* ---------------- feed urls ---------------- */
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
  http.setTimeout(30000);
  http.setUserAgent("SmartPlayLive-ESP32/3.0");
  int code = http.GET();
  if (code != 200) {
    Serial.printf("[HTTP] %s -> %d\n", url, code);
    http.end();
    return false;
  }
  int len = http.getSize();
  Serial.printf("[HTTP] %s -> code=%d size=%d\n", url, code, len);
  out = "";
  if (len > 0 && !out.reserve(len)) {
    Serial.println("[HTTP] reserve FAILED");
  }
  WiFiClient *stream = http.getStreamPtr();
  uint8_t buf[1024];
  http.setReuse(false);
  unsigned long lastData = millis();
  while (len > 0 || len == -1) {
    size_t avail = stream->available();
    if (avail) {
      size_t toRead = avail > sizeof(buf) ? sizeof(buf) : avail;
      int c = stream->readBytes(buf, toRead);
      if (c > 0) {
        out.concat((char *)buf, c);
        if (len > 0) len -= c;
        lastData = millis();
      }
    } else {
      if (!http.connected()) {
        if (millis() - lastData > 5000) break;
      }
      delay(2);
    }
  }
  http.end();
  Serial.printf("[HTTP] got %u bytes (remaining len=%d)\n", (unsigned)out.length(), len);
  return out.length() > 0;
}

/* ---------------- 放場處理（poll 路径） ---------------- */
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
  Serial.printf("[RELEASE] %s %s | %s | %s %s-%s | %d->%d\n", a.sport, a.date, a.venue, a.facility, st, en,
                oldC, newC);
  beep();
  g_returnPage = g_page;      // 警報收完返返原本個頁
  g_screen = SCR_ALERT;
  g_alertAt = millis();
  g_unread = true;
  ledGreenBlink(3);
  g_dirty = true;
}

/* ---------------- changes-eve.json poll（後備） ---------------- */
static String g_eveBody;

static void pollEve() {
  if (!g_venueMapLoaded) loadVenueMap();

  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[eve] WiFi not connected");
    g_pollFails++;
    g_dirty = true;
    return;
  }

  HTTPClient http;
  if (strncmp(FEED_EVE, "https://", 8) == 0) {
    g_sec.setInsecure();
    if (!http.begin(g_sec, FEED_EVE)) { Serial.println("[eve] begin FAILED"); g_pollFails++; g_dirty=true; return; }
  } else {
    if (!http.begin(FEED_EVE)) { Serial.println("[eve] begin FAILED"); g_pollFails++; g_dirty=true; return; }
  }
  http.setTimeout(30000);
  int code = http.GET();
  esp_task_wdt_reset();
  if (code != 200) {
    Serial.printf("[eve] HTTP %d\n", code);
    http.end();
    g_pollFails++;
    g_dirty = true;
    return;
  }
  Serial.printf("[eve] HTTP 200, streaming parse...\n");

  esp_task_wdt_reset();
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, http.getStream());
  http.end();
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
      if (d.length() == 0 && venue && *venue) {
          if (!g_venueMapLoaded) loadVenueMap();
          d = venueDistrict(venue);
      }
      if (d.length() == 0 && venue && *venue && browseLoaded) {
          for (int i = 0; i < nVenues; i++) {
              if (strcmp(venueNames[i], venue) == 0 && venueDists[i][0]) { d = String(venueDists[i]); break; }
          }
      }
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

static void loadVenueMap() {
  if (g_venueMapLoaded) return;
  if (!httpGet(FEED_TODAY, g_todayBody)) {
    Serial.println("[venue] fetch FAILED");
    return;
  }
  esp_task_wdt_reset();
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, g_todayBody);
  if (err) {
    Serial.printf("[venue] parse error: %s (size=%u)\n", err.c_str(), (unsigned)g_todayBody.length());
    doc.clear();
    return;
  }
  JsonObject sports = doc["sports"].as<JsonObject>();
  if (sports.isNull()) {
    Serial.println("[venue] no sports object");
    doc.clear();
    return;
  }
  g_venueCount = 0;
  for (JsonPair kv : sports) {
    esp_task_wdt_reset();
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
  g_todayBody = "";   // free memory after venue map loaded
  g_venueMapLoaded = true;
  Serial.printf("[venue] map loaded: %d venues, heap %u\n", g_venueCount, (unsigned)ESP.getFreeHeap());
}

// ---------- OTA 屏幕提示（覆蓋 cyd_ota_pull.h 嘅 weak 版本）----------
void otaScreenMsg(const char *line1, const char *line2) {
  Serial.printf("[OTA-SCREEN] %s | %s\n", line1 ? line1 : "", line2 ? line2 : "");
  tft.fillScreen(C_BG);
  tft.fillRect(0, 0, SCR_W, 40, C_ACCENT);
  drawUTF8(String("OTA UPDATE"), 8, 10, C_BG, C_ACCENT);
  tft.setTextColor(C_TEXT, C_BG);
  tft.setTextDatum(TL_DATUM);
  if (line1 && *line1) {
    int w = measureUTF8(String(line1));
    drawUTF8(String(line1), (SCR_W - w) / 2, 90, C_TEXT, C_BG);
  }
  if (line2 && *line2) {
    int w2 = measureUTF8(String(line2));
    drawUTF8(String(line2), (SCR_W - w2) / 2, 120, C_DIM, C_BG);
  }
}

/* ---------------- beep ---------------- */
static void beep() {
  bool ok = audioTone((AudioPath)BEEP_PATH, BEEP_FREQ, BEEP_MS, BEEP_AMP);
  if (!ok) Serial.println("[audio] tone FAILED (no speaker / wrong path?)");
}

/* ---------------- drawing ---------------- */
// ---------------------------------------------------------------------------
// 狀態收集（smartplay.ino 實作）—— 把當前畫面狀態填入 ReportState
// 俾 cyd_report.h 用。
// ---------------------------------------------------------------------------
void reportCollectState(ReportState &st) {
  st.district = "";
  st.date = "";
  st.page = 0;
  st.pages = 1;
  st.rows = 0;
  st.line = "";

  if (g_page == PAGE_BROWSE) {
    // 瀏覽頁：區 / 日期 / 頁碼 / 行數
    if (curDistrict >= 0 && curDistrict < nDistricts && districts[curDistrict][0]) {
      st.district = districts[curDistrict];
    }
    if (curDate >= 0 && curDate < nDates && dateLabels[curDate][0]) {
      st.date = dateLabels[curDate];
    } else {
      st.date = "全部日子";
    }
    int idx[64];
    int n = browseFilteredRows(idx, 64);
    st.rows = n;
    st.pages = (n + BROWSE_ROWS_PER_PAGE - 1) / BROWSE_ROWS_PER_PAGE;
    if (st.pages < 1) st.pages = 1;
    st.page = curPage;
    // 第一行顯示內容：日期 + 區 + 場地
    static char lineBuf[56];
    lineBuf[0] = 0;
    if (n > 0) {
      int ri = curPage * BROWSE_ROWS_PER_PAGE;
      if (ri < n) {
        BRow &r = browses[idx[ri]];
        const char *dn = (r.d < nDates) ? dateLabels[r.d] : "";
        const char *ds = (r.v < nVenues) ? venueDists[r.v] : "";
        const char *vn = (r.v < nVenues) ? venueNames[r.v] : "";
        snprintf(lineBuf, sizeof(lineBuf), "%s %s %s", dn, ds, vn);
      }
    }
    st.line = lineBuf;
  } else {
    // 通知頁：顯示最後一次放場
    st.district = g_alertCount > 0 ? g_alerts[0].district : "";
    st.date = g_alertCount > 0 ? g_alerts[0].date : "全部日子";
    st.rows = g_releaseTotal;
    st.pages = 1;
    st.page = 0;
    static char lineBuf[56];
    lineBuf[0] = 0;
    if (g_alertCount > 0) {
      snprintf(lineBuf, sizeof(lineBuf), "%s %s", g_alerts[0].sport, g_alerts[0].date);
    }
    st.line = lineBuf;
  }
}

static void drawHeader(uint16_t barColor, uint16_t fg) {
  tft.fillRect(0, 0, SCR_W, HEADER_H, barColor);
  // 版本號（v1.3+）—— 用 build flag OTA_FW_VERSION，同 OTA manifest 永遠一致。
  // 放喺標題右邊、clock 左邊（clock 喺 x=SCR_W-8，wifi bars 喺 x=SCR_W-74）。
  tft.setTextColor(C_DIM, barColor);
  tft.setTextDatum(TL_DATUM);
  tft.setTextSize(1);
  tft.drawString(g_reportFw, 150, 10, 1);
  tft.setTextSize(2);
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
  drawUTF8(String("放場通知器"), 6, 7, C_TEXT, C_BAR);
  if (g_unread) tft.fillCircle(SCR_W - 86, 15, 5, C_GOOD);

  // 大字
  String big = "等待放場中";
  int bw = measureUTF8(big);
  drawUTF8(big, (SCR_W - bw) / 2, BODY_Y + 26, C_TEXT, C_BG);

  String sub = "晚上 6 點後 · 餘額增加或新時段";
  int sw = measureUTF8(sub);
  drawUTF8(sub, (SCR_W - sw) / 2, BODY_Y + 50, C_DIM, C_BG);

  // status lines
  char line[64];
  int y = BODY_Y + 84;
  tft.setTextColor(C_DIM, C_BG);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("last poll", 8, y, 2);
  fmtClock(g_lastPollAt, line, sizeof(line));
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(line, 92, y, 2);

  y += 22;
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("next poll", 8, y, 2);
  tft.setTextColor(C_TEXT, C_BG);

  y += 22;
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("feed", 8, y, 2);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(g_feedGen, 92, y, 2);

  y += 22;
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString("releases", 8, y, 2);
  tft.setTextColor(C_GOOD, C_BG);

  // footer
  String left = String("WiFi ") + g_wifiSsid;
  if (g_pollFails) {
    snprintf(line, sizeof(line), " fail %d", g_pollFails);
    left += line;
  }
  drawFooter(left, "");
  // bottom tabs
  tft.setTextDatum(TL_DATUM);
  tft.setTextSize(1);
  tft.setTextColor(C_DIM, C_BAR);
  drawUTF8(String("通知"), 232, SCR_H - FOOTER_H + 4, C_DIM, C_BAR);
  tft.setTextColor(C_ACCENT, C_BAR);
  drawUTF8(String("瀏覽"), 282, SCR_H - FOOTER_H + 4, C_ACCENT, C_BAR);
  // 📜 記錄 tab
  drawHistChip();

  // audio probe banner
  if (g_probeText.length()) {
    int w = measureUTF8(g_probeText);
    int bx = (SCR_W - w) / 2;
    tft.fillRect(bx - 8, BODY_Y + 40, w + 16, 24, C_WARN);
    drawUTF8(g_probeText, bx, BODY_Y + 44, C_BG, C_WARN);
  }

  g_homeFullDrawn = true;
}

// ---------- v1.2：局部重繪（唔再每次 fillScreen） ----------
// 只更新「last poll / next poll / feed / releases」四行數值
static void drawHomeStatusRows() {
  if (!g_homeFullDrawn) return;
  char line[64];
  int y = BODY_Y + 84;

  // last poll
  fmtClock(g_lastPollAt, line, sizeof(line));
  tft.fillRect(92, y, 120, 17, C_BG);
  tft.setTextColor(C_TEXT, C_BG);
  tft.setTextDatum(TL_DATUM);
  tft.drawString(line, 92, y, 2);

  // next poll（倒數秒數會變 → 每次只清呢個小區域）
  y += 22;
  unsigned long since = millis() - g_lastEvePoll;
  unsigned long waitMs = g_evePollInterval - (since % g_evePollInterval);
  snprintf(line, sizeof(line), "%lus", waitMs / 1000);
  tft.fillRect(92, y, 120, 17, C_BG);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(line, 92, y, 2);

  // feed
  y += 22;
  tft.fillRect(92, y, 120, 17, C_BG);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString(g_feedGen, 92, y, 2);

  // releases
  y += 22;
  snprintf(line, sizeof(line), "%d", g_releaseTotal);
  tft.fillRect(92, y, 120, 17, C_BG);
  tft.setTextColor(C_GOOD, C_BG);
  tft.drawString(line, 92, y, 2);
}

// 📜 記錄 tab 局部重繪（底部導覽列，touch 回饋用）
static void drawHistChip() {
  bool hf = (g_histChipFlash && millis() < g_histFlashUntil);
  int ty = SCR_H - FOOTER_H + 4;
  uint16_t fg = hf ? C_BG : (g_page == PAGE_HISTORY ? C_ACCENT : C_DIM);
  uint16_t bg = hf ? C_ACCENT : C_BAR;
  tft.fillRect(178, SCR_H - FOOTER_H, 50, FOOTER_H, bg);
  drawUTF8(String("記錄"), 182, ty, fg, bg);
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

    // line 2: date + time range + facility
    char st[8], en[8];
    fmtTime(a.start, st, sizeof(st));
    fmtTime(a.end, en, sizeof(en));
    char range[24];
    snprintf(range, sizeof(range), "%s-%s", st, en);
    String line2 = "";
    if (a.date[0]) line2 += String(a.date) + "  ";
    line2 += String(range);
    if (a.facility[0]) line2 += "  " + String(a.facility);
    drawUTF8(fitUTF8(line2, SCR_W - 20), 10, y + 20, C_TEXT, C_CARD_HOT);

    // line 3: venue
    drawUTF8(fitUTF8(String(a.venue), SCR_W - 24), 10, y + 37, C_TEXT, C_CARD_HOT);
    y += CARD_H + 3;
  }

  String hint = "按一下畫面關閉";
  String cnt = "共 " + String(g_alertCount) + " 個新時段";
  drawFooter(hint, cnt);
}

/* ---------------- touch ---------------- */
static bool touchDown = false;
static int tStartX = 0, tStartY = 0;
static int tLastX = 0, tLastY = 0;
static unsigned long tStartTime = 0;

static void processTap(int x, int y) {
  // 警報卡最上層：撳一下就收，收完返返原本個頁
  if (g_screen == SCR_ALERT) {
    g_screen = SCR_HOME;
    g_page = g_returnPage;
    g_unread = false;
    g_homeNeedsFull = true;
    g_dirty = true;
    return;
  }

  // 📜 底部「記錄」tab（要喺底部導覽之前判斷，否則會被通知/瀏覽攞走）
  if (g_page == PAGE_NOTIFY && x >= 176 && x <= 230 && y >= SCR_H - FOOTER_H) {
    g_histChipFlash = true;
    g_histFlashUntil = millis() + 220;
    g_page = PAGE_HISTORY;
    nhDetailBatch = -1;
    nhScroll = 0;
    if (!nhLoaded && !nhFetching) nhFetch();
    g_dirty = true;
    return;
  }

  // 底部 Tab 導航
  if (y >= SCR_H - FOOTER_H) {
    if (x < SCR_W / 2) {
      if (g_page != PAGE_NOTIFY) { g_page = PAGE_NOTIFY; g_homeNeedsFull = true; }
    } else {
      g_page = PAGE_BROWSE;
      browseReset();
      if (!browseLoaded) browseFetch();
    }
    g_dirty = true;
    return;
  }

  if (g_page == PAGE_HISTORY) {
    nhTouch(x, y);
    if (nhWantExit) {
      g_page = PAGE_NOTIFY;
      g_homeNeedsFull = true;
      nhDetailBatch = -1;
      nhScroll = 0;
    }
    g_dirty = true;
    return;
  }

  if (g_page == PAGE_BROWSE) {
    // 極左上角細角落 → 返通知頁（避免同地區 chip 衝突）
    if (x < 16 && y < 16) {
      g_page = PAGE_NOTIFY;
      g_homeNeedsFull = true;
      g_dirty = true;
      return;
    }
    browseTouch(x, y);
    g_dirty = true;
    return;
  }

  // 通知頁：撳任何位置 → 入瀏覽頁（第一次先載入資料）
  g_page = PAGE_BROWSE;
  browseReset();
  if (!browseLoaded) {
    g_dirty = true;
    browseFetch();
  }
  Serial.printf("[ui] page=browse district=%u day=%u rows=%u\n", curDistrict, curDate,
                nRows);
  g_dirty = true;
}

static void handleTouch() {
  bool touched = ts.tirqTouched() && ts.touched();
  int x = 0, y = 0;
  if (touched) {
    TS_Point p = ts.getPoint();
    // XPT2046 回傳 8191 = 冇撳；z < 10 = 壓力唔夠
    if (p.x > 4000 || p.y > 4000 || p.z < 10) touched = false;
    else {
      x = constrain(map(p.x, TOUCH_MIN_X, TOUCH_MAX_X, 0, SCR_W), 0, SCR_W - 1);
      y = constrain(map(p.y, TOUCH_MIN_Y, TOUCH_MAX_Y, 0, SCR_H), 0, SCR_H - 1);
    }
  }

  if (!touched) {
    if (touchDown) {
      int dx = tLastX - tStartX;
      int dy = tLastY - tStartY;
      unsigned long dt = millis() - tStartTime;
      touchDown = false;
      if (dt < 700 && (abs(dx) > 45 || abs(dy) > 45) && (abs(dx) + abs(dy)) > 60) {
        // swipe gesture
        if (g_page == PAGE_BROWSE && g_screen == SCR_HOME) {
          browseSwipe(dx, dy);
          g_dirty = true;
        } else if (g_page == PAGE_HISTORY && g_screen == SCR_HOME) {
          nhSwipe(dx, dy);
          g_dirty = true;
        }
      } else {
        processTap(tStartX, tStartY);
      }
    }
    return;
  }

  if (!touchDown) {
    touchDown = true;
    tStartX = x; tStartY = y; tLastX = x; tLastY = y; tStartTime = millis();
    return;
  }
  tLastX = x; tLastY = y;
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
    // v1.2：時鐘只喺 header 右上角 → 局部重畫 header（唔成頁）
    if (g_page == PAGE_NOTIFY && g_screen == SCR_HOME && g_homeFullDrawn) {
      if (g_timeValid) {
        char buf[8];
        snprintf(buf, sizeof(buf), "%02d:%02d", g_hour, g_min);
        tft.fillRect(SCR_W - 60, 2, 56, 26, C_BAR);
        tft.setTextColor(C_TEXT, C_BAR);
        tft.setTextDatum(TR_DATUM);
        tft.drawString(buf, SCR_W - 8, 7, 2);
        tft.setTextDatum(TL_DATUM);
      }
    } else {
      g_dirty = true;
    }
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
  } else if (c == 'o') {
    Serial.println("[OTA] force check triggered");
    otaPullCheck(true); else if (c == 's') {
    if (curSport == -1) curSport = 0;
    else if (curSport >= 4) curSport = -1;
    else curSport++;
    curDistrict = 0; curDate = 0; curPage = 0;
    browseSavePrefs();
    browseFetch();
    g_dirty = true;
    Serial.printf("[browse] sport=%d rows=%u\n", curSport, nRows);
  } else if (c == 't') {
    browseCycleTimePeriod();
    g_dirty = true;
    Serial.printf("[browse] timePeriod=%d\n", curTimePeriod);
  } else if (c == 'o') {
    browseOverlay = 1;
    g_dirty = true;
    Serial.println("[ui] overlay=district");
  } else if (c == 'O') {
    browseOverlay = 2;
    g_dirty = true;
    Serial.println("[ui] overlay=sport");
  } else if (c == 'u') {
    Serial.printf("[ui] page=%s district=%u/%u date=%u/%u auto=%d paused=%d loaded=%d rows=%u\n",
                  g_page == PAGE_BROWSE ? "browse" : "notify", curDistrict, nDistricts,
                  curDate, nDates, autoPage ? 1 : 0, paused ? 1 : 0,
                  browseLoaded ? 1 : 0, nRows);
  } else if (c == 'g') {
    // 去瀏覽頁（測試用，等同撳一下）
    g_page = PAGE_BROWSE;
    browseLoadPrefs();
    if (!browseLoaded) browseFetch();
    lastPageAt = millis();
    g_dirty = true;
    Serial.printf("[ui] page=browse district=%u date=%u rows=%u\n", curDistrict, curDate,
                  nRows);
  } else if (c == 'n') {
    g_page = PAGE_NOTIFY;
    g_dirty = true;
    Serial.println("[ui] page=notify");
  } else if (c == 'a') {
    g_screen = SCR_ALERT;
    g_dirty = true;
  } else if (c == 'A') {
    handleRelease("羽毛球", "西貢區", "香港單車館", "主場", "2026-11-05", 1080, 1140, 1, 3);
    g_screen = SCR_ALERT;
    g_dirty = true;
    Serial.println("[debug] injected sample alert");
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
      Serial.printf("  %s %s %s %s-%s %s (%s) %d->%d\n", a.sport, a.date, a.venue, st, en, a.facility,
                    a.district, a.oldC, a.newC);
    }
  } else if (c == 'v') {
    Serial.printf("[venue] map %s (%d entries)\n", g_venueMapLoaded ? "loaded" : "not loaded",
                  g_venueCount);
  } else if (c == 'B') {
    Serial.printf("[browse] rows=%u venues=%u districts=%u dates=%u sports=%u loaded=%d err='%s'\n",
                  nRows, nVenues, nDistricts, nDates, nSports, browseLoaded ? 1 : 0, browseError);
    for (int i = 0; i < nRows && i < 5; i++) {
      BRow &r = browses[i];
      Serial.printf("  row %u: v=%u (%s) k=%u (%s) d=%u (%s) %u-%u c=%u\n", i, r.v,
                    r.v < nVenues ? venueNames[r.v] : "?", r.k,
                    r.k < nSports ? sportIcons[r.k] : "?", r.d,
                    r.d < nDates ? dateLabels[r.d] : "?", r.sm, r.em, r.courts);
    }
    for (int i = 0; i < nDistricts && i < 8; i++)
      Serial.printf("  district %u: %s\n", i, districts[i]);
  } else {
    Serial.println("commands: b p r a h l v B");
  }
}

/* ---------------- setup ---------------- */

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
  // Boot splash
  tft.fillRect(0, 0, 320, 40, C_ACCENT);
  drawUTF8(String("SmartPLAY Live"), 8, 10, C_BG, C_ACCENT);
  tft.setTextColor(C_TEXT, C_BG);
  tft.setTextDatum(TL_DATUM);
  drawUTF8(String("CYD v3.3"), 8, 50, C_DIM, C_BG);
  drawUTF8(String("連接中..."), 8, 70, C_DIM, C_BG);
  // CYD 觸控用獨立 VSPI bus：SCK=25, MISO=39, MOSI=32, CS=33
  touchSPI.begin(25, 39, 32, 33);
  ts.begin(touchSPI);
  ts.setRotation(1);

  Serial.println("\n[SmartPLAY Live CYD] boot v3.3 — 放場通知器 + 狀態回報");
  Serial.printf("[REPORT] firmware %s, endpoint OK\n", g_reportFw);
  // OTA rollback: mark current app as valid (cancel rollback)
  esp_ota_mark_app_valid_cancel_rollback();
  // Load WiFi creds from NVS (first-boot migration from compiled defaults)
  loadWifiCredsFromNVS();
  // Watchdog: deinit framework's default TWDT (5s), reinit with 60s, then register loopTask
  esp_task_wdt_deinit();
  esp_task_wdt_config_t wdt_config = { .timeout_ms = 60000, .idle_core_mask = 0, .trigger_panic = true };
  esp_task_wdt_init(&wdt_config);
  esp_task_wdt_add(NULL);
  connectWiFi();
  // ---- OTA (over-the-air) 更新 ----
  ArduinoOTA.setHostname("smartplay-cyd");
  ArduinoOTA.setPassword("smartplay");
  ArduinoOTA.onStart([]() {
    Serial.println("[OTA] start");
    otaScreenMsg("更新中…", "ArduinoOTA");
  });
  ArduinoOTA.onEnd([]() {
    Serial.println("[OTA] end");
    otaScreenMsg("更新完成", "重新啟動中");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("[OTA] %u%%\r", (progress * 100) / total);
  });
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("[OTA] error %u\n", error);
    otaScreenMsg("更新失敗", "請用 USB 救板");
  });
  ArduinoOTA.begin();
  Serial.printf("[OTA] ready, IP=%s, hostname=smartplay-cyd, password=smartplay\n",
                WiFi.localIP().toString().c_str());

  configTime(8 * 3600, 0, "pool.ntp.org", "hk.pool.ntp.org");  // HKT

  g_lastEvePoll = 0;
  loadVenueMap();
  pollEve();   // 第一輪 = baseline，唔會誤嗶

  // 瀏覽頁初始化（NVS 設定 + 第一次拉 browse.json）
  browseInit();
  browseFetch();
  g_dirty = true;

  // OTA pull：開機 45 秒後做第一次遠端版本檢查
  g_lastOtaCheck = millis() - OTA_CHECK_INTERVAL_MS + 45000UL;

  // v1.3：狀態回報初始化（開機 30 秒後做第一次 POST）
  reportInit();
}

void loop() {
  unsigned long now = millis();

  if (now - g_lastEvePoll >= g_evePollInterval) {
    g_lastEvePoll = now;
    if (WiFi.status() != WL_CONNECTED) connectWiFi();
    pollEve();
    g_evePollInterval = EVE_POLL_MIN_MS + (unsigned long)random((int)(EVE_POLL_MAX_MS - EVE_POLL_MIN_MS + 1));
  }

  handleSerial();
  ArduinoOTA.handle();
  otaPullCheck();
  reportTick();
  handleTouch();
  if (browseFlashUntil && millis() >= browseFlashUntil) {
    browseFlashUntil = 0;
    browseFlashChip = -1;
    // v1.2：只重畫 header（局部），唔成頁 fillScreen
    if (g_page == PAGE_BROWSE && g_screen == SCR_HOME) browseMarkHeader();
    g_dirty = true;
  }
  updateClock();
  if (g_page == PAGE_BROWSE && g_screen == SCR_HOME) {
    browseTick();
    // 瀏覽頁開著嘅時候每 15 分鐘更新一次場次資料
    static unsigned long lastBrowseFetch = 0;
    if (millis() - lastBrowseFetch >= 15UL * 60UL * 1000UL) {
      lastBrowseFetch = millis();
      browseFetch();
      g_dirty = true;
    }
  }

  // 📜 記錄 chip flash 到期 → 局部重繪 chip（唔成頁重畫）
  if (g_histChipFlash && millis() >= g_histFlashUntil) {
    g_histChipFlash = false;
    if (g_page == PAGE_NOTIFY && g_screen == SCR_HOME) drawHistChip();
  }

  // 📜 放場記錄頁：首次未載入就背景拉 + 每 5 分鐘更新
  if (!nhLoaded && !nhFetching && WiFi.status() == WL_CONNECTED &&
      millis() > 10000UL) {
    nhFetch();
  } else if (nhLoaded && g_page == PAGE_HISTORY &&
             millis() - nhLastFetch >= 5UL * 60UL * 1000UL) {
    nhFetch();
    g_dirty = true;
  }

  // 警報畫面自動返回（通知已經響過，唔好霸住個位）
  if (g_screen == SCR_ALERT && millis() - g_alertAt > 120000) {
    g_screen = SCR_HOME;
    g_page = g_returnPage;
    g_unread = false;
    g_homeNeedsFull = true;
    g_dirty = true;
  }

  // 通知頁主畫面：每 5 秒只局部更新四行狀態（唔再 fillScreen → 冇閃爍）
  static unsigned long lastNotifyRedraw = 0;
  if (g_page == PAGE_NOTIFY && g_screen == SCR_HOME &&
      millis() - lastNotifyRedraw >= 5000UL) {
    lastNotifyRedraw = millis();
    drawHomeStatusRows();
  }

  if (g_dirty) {
    g_dirty = false;
    if (g_screen == SCR_ALERT && g_alertCount > 0) drawAlert();
    else if (g_page == PAGE_BROWSE) browseDrawCurrent();
    else if (g_page == PAGE_HISTORY) {
      if (nhDetailBatch >= 0) nhDrawDetail(); else nhDrawList();
    }
    else {
      if (g_homeNeedsFull || !g_homeFullDrawn) { drawHome(); g_homeFullDrawn = true; g_homeNeedsFull = false; }
      else drawHomeStatusRows();
    }
  }

  esp_task_wdt_reset();
  delay(100);
}
