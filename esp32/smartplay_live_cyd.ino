/*
 * SmartPLAY Live — ESP32 觸屏瀏覽器 v3.3
 * ================================================================
 * 硬件：ESP32-2432S028R "Cheap Yellow Display" (CYD)
 *       2.8" ILI9341 TFT 240x320 + 電阻觸控 (XPT2046) + ESP32-WROOM
 *
 * 功能：
 *   📺 瀏覽模式 — 每 N 秒自動翻頁，顯示未來 6 日（可預訂）晚上場次
 *      按 區份 → 日期 過濾，觸屏上下部揀區份
 *   🔔 通知模式 — 照舊 poll changes-eve.json，有 📈 放場就 buzzer beep
 *
 * 兩個模式同時運行。設定存 Preferences（斷電唔會冇）。
 *
 * Feed（GitHub Pages，無 WAF）：
 *   https://hkteddychan.github.io/smartplay-live/esp32/browse.json       ~5KB
 *   https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json  ~1KB
 *
 * Library（Arduino IDE Library Manager 全部搵到）：
 *   - ArduinoJson (>=7)          by Benoit Blanchon
 *   - TFT_eSPI                   by Bodmer   （用下面 User_Setup）
 *   - XPT2046_Touchscreen        by Paul Stoffregen
 *
 * ⚠️ TFT_eSPI User_Setup.h 要改（Arduino IDE: 文件 → 備註目錄 → TFT_eSPI/User_Setup.h）
 *    CYD 標準設定：
 *      #define ILI9341_DRIVER
 *      #define TFT_MISO 12
 *      #define TFT_MOSI 13
 *      #define TFT_SCLK 14
 *      #define TFT_CS   15
 *      #define TFT_DC    2
 *      #define TFT_RST  -1
 *      #define TFT_BL   21      // 背光
 *      #define TOUCH_CS 33      // XPT2046 touch CS
 *      #define LOAD_GLCD / LOAD_FONT2 / LOAD_FONT4 / LOAD_GFXFF
 *      #define SMOOTH_FONT
 *
 * 用法：
 *   1. 改 WIFI_SSID / WIFI_PASS
 *   2. 燒錄，開 Serial Monitor 115200 睇 debug
 *   3. 觸屏：上部 = 上一區 / 下部 = 下一區 / 中部 = 換日期
 *
 * 接線：buzzer 被動 → GPIO25(+)/GND(−)；唔使其他線（屏係板上一體）
 * ================================================================
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <HTTPUpdate.h>
#include <WiFiClientSecure.h>

// ---------------- OTA ----------------
// 開機 + 每 6 小時 GET firmware.json；版本新過 FIRMWARE_VERSION → 自動下載 .bin 更新 + reboot
const char* FIRMWARE_VERSION = "3.3.0";
const char* URL_FIRMWARE = "https://hkteddychan.github.io/smartplay-live/esp32/firmware.json";
const unsigned long OTA_CHECK_MS = 6UL * 3600 * 1000;
unsigned long lastOtaCheck = 0;

// ---------------- CONFIG ----------------
const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

const char* URL_BROWSE = "https://hkteddychan.github.io/smartplay-live/esp32/browse.json";
const char* URL_CHANGES_EVE = "https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json";

// 🔒 audit fix 2026-11-12：/esp/report 而家要 device key（同 RUN_KEY 一致）— build 時用 -DREPORT_KEY= 帶入
#ifndef REPORT_KEY
#define REPORT_KEY ""   // PlatformIO/arduino-cli build flag -DREPORT_KEY='"..."' 提供
#endif
static String reportUrl() { return String(URL_REPORT) + "?key=" + REPORT_KEY; }

const unsigned long BROWSE_REFRESH_MS = 3UL * 60 * 1000;   // browse.json 每 3min 重拉（mirror */2 加密後）
const unsigned long EVE_POLL_MS       = 3UL * 60 * 1000;    // changes-eve poll
const unsigned long WIFI_RETRY_MS     = 30UL * 1000;

const int BUZZER_PIN = 25;

// ---------------- STATE ----------------
TFT_eSPI tft = TFT_eSPI();
XPT2046_Touchscreen ts(TOUCH_CS, 255);   // TOUCH_CS=33 由 TFT_eSPI config 提供
Preferences prefs;

// browse.json data（PSRAM 冇都食得落 — ~5KB JSON + 展開 strings ~40KB）
String browseG;
String dateLabels[8];        // "11-05 四"
int    nDates = 0;
String sportIcons[6];        // 🏸🏀🏐🎾⚽
int    nSports = 0;
String venueNames[200];      // "場地名"
String venueDists[200];      // "區名"
int    nVenues = 0;
int    curPage = 0;              // 而家顯示緊嘅頁（每頁 4 行場次）
struct BRow { uint8_t v, k, d; uint16_t sm, em, courts; };
BRow browses[400];           // 最多 400 行 — 6KB JSON 實際得 ~200 行
int    nRows = 0;

// UI state
String districts[24];        // 出現過嘅區（自動由 data 收集）
int    nDistricts = 0;
int    curDistrict = 0;
int    curDate = 0;          // 0=全部日子, 1..6=指定日子（全部 = 顯示所有日期）
int    pageSec = 5;          // 自動翻頁秒數（NVS）
bool   autoPage = true;
bool   paused = false;

// timings
unsigned long lastBrowsePull = 0, lastEvePoll = 0, lastWifiTry = 0, lastPageAt = 0;

// ================= WiFi / HTTP =================
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("[WiFi] connecting to %s", WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 15000) { delay(300); Serial.print("."); }
  if (WiFi.status() == WL_CONNECTED)
    Serial.printf(" OK, IP=%s, RSSI=%d\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  else
    Serial.println(" FAILED");
}

bool httpGetString(const char* url, String& out) {
  HTTPClient http;
  http.begin(url);
  http.setTimeout(15000);
  http.setUserAgent("SmartPlayLive-ESP32/3.3");
  int code = http.GET();
  if (code != 200) { http.end(); return false; }
  int len = http.getSize();
  out.reserve(len > 0 ? len : 4096);
  WiFiClient* s = http.getStreamPtr();
  uint8_t buf[1024];
  while (http.connected() && (len > 0 || len == -1)) {
    size_t a = s->available();
    if (a) {
      int c = s->readBytes(buf, a > sizeof(buf) ? sizeof(buf) : a);
      out.concat((char*)buf, c);
      if (len > 0) len -= c;
    } else delay(2);
  }
  http.end();
  return true;
}

// ================= Data model =================
int districtIndexOf(const String& d) {
  for (int i = 0; i < nDistricts; i++) if (districts[i] == d) return i;
  if (nDistricts < 24) { districts[nDistricts] = d; return nDistricts++; }
  return -1;
}

// rows for (district, date) — returns count, fills page buffer
int rowsFor(int distIdx, int dateIdx, int* out, int maxOut) {
  int n = 0;
  for (int i = 0; i < nRows && n < maxOut; i++) {
    BRow& r = browses[i];
    if (venueDists[r.v] != districts[distIdx]) continue;
    if (dateIdx > 0 && r.d != dateIdx - 1) continue;   // 0 = 全部日子
    out[n++] = i;
  }
  return n;
}

bool parseBrowse(const String& body) {
  JsonDocument doc;
  if (deserializeJson(doc, body)) return false;
  browseG = doc["g"] | "";

  nDates = 0;
  for (JsonArray d : doc["d"].as<JsonArray>()) {
    if (nDates < 8) dateLabels[nDates++] = d.as<const char*>();   // v7: 需要 (nDates < 8) check
  }
  nSports = 0;
  for (JsonArray k : doc["k"].as<JsonArray>()) {
    if (nSports < 6) sportIcons[nSports++] = k.as<const char*>();
  }
  nVenues = 0;
  for (JsonArray v : doc["v"].as<JsonArray>()) {
    if (nVenues >= 200) break;
    String s = v.as<const char*>();
    int bar = s.indexOf('|');
    venueNames[nVenues] = (bar > 0) ? s.substring(0, bar) : s;
    venueDists[nVenues] = (bar > 0) ? s.substring(bar + 1) : "";
    districtIndexOf(venueDists[nVenues]);
    nVenues++;
  }
  nRows = 0;
  for (JsonArray r : doc["r"].as<JsonArray>()) {
    if (nRows >= 400) break;
    browses[nRows].v      = r[0] | 0;
    browses[nRows].k      = r[1] | 0;
    browses[nRows].d      = r[2] | 0;
    browses[nRows].sm     = r[3] | 0;
    browses[nRows].em     = r[4] | 0;
    browses[nRows].courts = r[5] | 0;
    nRows++;
  }
  return true;
}

// ================= UI =================
void drawPage() {
  int rowIdx[12];
  int n = rowsFor(curDistrict, curDate, rowIdx, 12);
  int totalPages = (n + 3) / 4; if (totalPages < 1) totalPages = 1;
  int page = curPage % totalPages;

  tft.fillScreen(TFT_BLACK);
  // header
  tft.setTextColor(TFT_CYAN, TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.drawString(districts[curDistrict], 8, 6, 2);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString(curDate == 0 ? "全部日子" : dateLabels[curDate - 1], 130, 6, 2);
  tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
  tft.drawString(String(pageSec) + "s" + (paused ? " ⏸" : " ▶"), 190, 6, 2);
  tft.drawFastHLine(0, 26, 240, TFT_DARKGREY);

  // 4 data rows
  if (n == 0) {
    tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
    tft.drawString("呢個時段冇場", 20, 140, 2);
  } else {
    for (int i = 0; i < 4; i++) {
      int ri = page * 4 + i;
      if (ri >= n) break;
      BRow& r = browses[rowIdx[ri]];
      int y = 34 + i * 64;
      tft.setTextColor(sportIcons[r.k] == "🏸" ? TFT_GREENYELLOW :
                       sportIcons[r.k] == "⚽" ? TFT_ORANGE : TFT_SKYBLUE, TFT_BLACK);
      tft.drawString(sportIcons[r.k] + " " + dateLabels[r.d], 8, y, 2);
      tft.setTextColor(TFT_WHITE, TFT_BLACK);
      tft.drawString(venueNames[r.v], 8, y + 18, 2);
      tft.setTextColor(TFT_YELLOW, TFT_BLACK);
      char tm[16]; snprintf(tm, 16, "%02d:%02d", r.sm / 60, r.sm % 60);
      tft.drawString(String(tm) + "  " + String(r.courts) + " 場", 8, y + 36, 2);
    }
  }

  // footer
  tft.drawFastHLine(0, 296, 240, TFT_DARKGREY);
  tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
  tft.drawString(String(curDistrict + 1) + "/" + String(nDistricts) + " 區 · 頁 " +
                 String(page + 1) + "/" + String(totalPages), 8, 302, 2);
  tft.setTextColor(TFT_OLIVE, TFT_BLACK);
  tft.drawString(browseG, 100, 302, 2);
}

// ================= Touch =================
bool touchRead(int16_t& x, int16_t& y) {
  TS_Point p = ts.getPoint();
  if (p.z < 300) return false;
  // CYD 觸屏方向（多數板係 Portrait 旋轉 0 但 touch 對應 Landscape 1）
  x = map(p.x, 200, 3800, 0, 239);
  y = map(p.y, 200, 3800, 0, 319);
  return true;
}

void handleTouch() {
  int16_t x, y;
  if (!touchRead(x, y)) return;
  static unsigned long lastTouch = 0;
  if (millis() - lastTouch < 400) return;    // debounce
  lastTouch = millis();
  lastPageAt = millis();                     // touch 重置自動翻頁計時

  if (y < 100) {                             // 上部：上一區
    curDistrict = (curDistrict - 1 + nDistricts) % nDistricts;
    curPage = 0;
  } else if (y > 220) {                      // 下部：下一區
    curDistrict = (curDistrict + 1) % nDistricts;
    curPage = 0;
  } else {                                   // 中部：換日期
    curDate = (curDate + 1) % (nDates + 1);  // 0=全部 → 1..6 → 0
    curPage = 0;
  }
  savePrefs();
  drawPage();
}

// ================= Prefs =================
void savePrefs() {
  prefs.begin("spl", false);
  prefs.putInt("dist", curDistrict);
  prefs.putInt("date", curDate);
  prefs.putInt("sec", pageSec);
  prefs.putBool("auto", autoPage);
  prefs.end();
}
void loadPrefs() {
  prefs.begin("spl", false);
  curDistrict = prefs.getInt("dist", 0);
  curDate     = prefs.getInt("date", 0);
  pageSec     = prefs.getInt("sec", 5);
  autoPage    = prefs.getBool("auto", true);
  prefs.end();
}

// ================= ESP32 屏狀態上報（網站「ESP32 視角」） =================
// 每 3 分鐘 POST 當前畫面快照去 Worker — 網站「ESP32 視角」tab 顯示 + 歷史記錄
// Worker 會 de-dupe（畫面冇變唔記 history），唔使怕重複
unsigned long lastReport = 0;

void reportScreen() {
  if (WiFi.status() != WL_CONNECTED) return;
  // 當前畫面資訊（同 drawPage 一致）
  int rowIdx[12];
  int n = rowsFor(curDistrict, curDate, rowIdx, 12);
  int totalPages = (n + 3) / 4; if (totalPages < 1) totalPages = 1;
  String line1 = "";
  if (n > 0) {
    BRow& r = browses[rowIdx[(curPage % totalPages) * 4]];
    line1 = sportIcons[r.k] + " " + dateLabels[r.d];
  }
  // payload — date 用 JSON escape 好 UTF-8 直接出（Arduino String 係 UTF-8 bytes）
  String dateStr = (curDate == 0) ? String("ALL") : dateLabels[curDate - 1];
  String payload = "{\"id\":\"cyd-01\",\"fw\":\"v3.3\",";
  payload += "\"district\":\"" + districts[curDistrict] + "\",";
  payload += "\"date\":\"" + dateStr + "\",";
  payload += "\"page\":" + String(curPage % totalPages) + ",";
  payload += "\"pages\":" + String(totalPages) + ",";
  payload += "\"rows\":" + String(n) + ",";
  payload += "\"line\":\"" + line1 + "\",";
  payload += "\"rssi\":" + String(WiFi.RSSI()) + ",";
  payload += "\"heap\":" + String(ESP.getFreeHeap()) + ",";
  payload += "\"up\":" + String(millis() / 1000) + "}";
  HTTPClient http;
  http.begin(reportUrl());
  http.setTimeout(10000);
  http.addHeader("Content-Type", "application/json");
  http.setUserAgent("SmartPlayLive-ESP32/3.3");
  int code = http.POST(payload);
  if (code != 200) Serial.printf("[REPORT] HTTP %d\n", code);
  else Serial.printf("[REPORT] %s/%s p%d (%d rows)\n", districts[curDistrict].c_str(), dateStr.c_str(), curPage % totalPages, n);
  http.end();
}

// ================= Eve changes（通知模式照舊） =================
String lastEveVersion = "";
bool baselined = false;
int beepQueue = 0;

void processEveChanges(const String& body) {
  JsonDocument doc;
  if (deserializeJson(doc, body)) return;
  const char* gen = doc["g"] | "";
  if (String(gen) == lastEveVersion) return;
  bool firstRun = !baselined;
  lastEveVersion = gen;
  baselined = true;

  int nRel = 0;
  JsonObject sports = doc["sports"];
  for (JsonPair kv : sports) {
    for (JsonArray c : kv.value().as<JsonArray>()) {
      const char* kind = c[5] | "";
      int oldC = c[6] | 0, newC = c[7] | 0;
      bool isRelease = (String(kind) == "chg" && newC > oldC) || String(kind) == "new";
      if (isRelease) { nRel++; if (!firstRun) beepQueue++; }
    }
  }
  if (!firstRun && nRel > 0) {
    Serial.printf("[EVE] 🔔 %d releases\n", nRel);
    tft.fillRect(0, 26, 240, 8, TFT_ORANGE);    // 頂部閃一條橙色線提示（背景黑，橙對比強）
  }
}

// ================= OTA =================
void otaScreen(const char* msg) {
  tft.fillRect(0, 296, 240, 24, TFT_BLACK);
  tft.setTextColor(TFT_ORANGE, TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.drawString(msg, 8, 302, 2);
}

void checkOTA() {
  HTTPClient http;
  http.begin(URL_FIRMWARE);
  http.setTimeout(10000);
  http.setUserAgent("SmartPlayLive-CYD-OTA");
  int code = http.GET();
  if (code != 200) { http.end(); return; }
  String body = http.getString();
  http.end();
  JsonDocument doc;
  if (deserializeJson(doc, body)) return;
  const char* latest = doc["cyd_v"] | "";
  const char* binUrl = doc["cyd_bin"] | "";
  if (!latest[0] || !binUrl[0]) return;
  if (strcmp(latest, FIRMWARE_VERSION) == 0) {
    Serial.printf("[OTA] up-to-date (%s)\n", latest);
    return;
  }
  Serial.printf("[OTA] %s -> %s, updating...\n", FIRMWARE_VERSION, latest);
  otaScreen("OTA updating...");
  WiFiClientSecure client;
  client.setInsecure();
  httpUpdate.rebootOnUpdate(true);
  HTTPUpdateResult r = httpUpdate.update(client, binUrl);
  switch (r) {
    case HTTP_UPDATE_FAILED:      otaScreen("OTA failed"); Serial.printf("[OTA] failed: %s\n", httpUpdate.getLastErrorString().c_str()); break;
    case HTTP_UPDATE_NO_UPDATES:  otaScreen("OTA no update"); break;
    case HTTP_UPDATE_OK:          break;  // rebooting
  }
  delay(3000);
  drawPage();   // 還原屏
}

// ================= Setup / Loop =================
void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(BUZZER_PIN, OUTPUT);
  tft.init();
  tft.setRotation(1);          // Landscape 240(寬) x 320(高)
  tft.fillScreen(TFT_BLACK);
  ts.begin();
  ts.setRotation(1);

  tft.setTextColor(TFT_CYAN, TFT_BLACK); tft.setTextDatum(TL_DATUM);
  tft.drawString("SmartPLAY Live", 10, 10, 2);
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString("ESP32 瀏覽器 v3.3 booting...", 10, 30, 2);

  loadPrefs();
  connectWiFi();
  checkOTA();     // 開機 check OTA
  lastOtaCheck = millis();
  lastPageAt = millis();
}

void loop() {
  unsigned long now = millis();
  bool wifiOk = (WiFi.status() == WL_CONNECTED);

  // browse.json pull
  if (nRows == 0 || now - lastBrowsePull >= BROWSE_REFRESH_MS) {
    if (!wifiOk && now - lastWifiTry > WIFI_RETRY_MS) { connectWiFi(); lastWifiTry = now; }
    String body;
    if (wifiOk && httpGetString(URL_BROWSE, body) && parseBrowse(body)) {
      lastBrowsePull = now;
      if (curDistrict >= nDistricts) curDistrict = 0;
      drawPage();
      Serial.printf("[BROWSE] %d rows, %d districts, gen=%s\n", nRows, nDistricts, browseG.c_str());
    }
  }

  // eve poll
  if (wifiOk && now - lastEvePoll >= EVE_POLL_MS) {
    lastEvePoll = now;
    String body;
    if (httpGetString(URL_CHANGES_EVE, body)) processEveChanges(body);
  }

  // OTA check（每 6 小時）
  if (wifiOk && now - lastOtaCheck >= OTA_CHECK_MS) {
    lastOtaCheck = now;
    checkOTA();
  }

  // 屏狀態上報（每 3 分鐘）
  if (wifiOk && now - lastReport >= 3UL * 60 * 1000) {
    lastReport = now;
    reportScreen();
  }

  // auto page
  if (autoPage && !paused && nRows > 0 && millis() - lastPageAt >= pageSec * 1000UL) {
    curPage++;
    lastPageAt = millis();
    drawPage();
  }

  handleTouch();

  // beep queue
  if (beepQueue > 0) {
    for (int i = 0; i < min(beepQueue, 5); i++) {
      digitalWrite(BUZZER_PIN, HIGH); delay(120);
      digitalWrite(BUZZER_PIN, LOW);  delay(80);
    }
    beepQueue = 0;
  }
  delay(50);
}
