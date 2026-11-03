/*
 * SmartPLAY Live — ESP32 客戶端
 * ================================================
 * 由 https://hkteddychan.github.io/smartplay-live/esp32/ 拉 compact JSON feed，
 * 喺 Serial Monitor 列出今日+聽日有餘額嘅場地時段。
 *
 * Feed 格式（positional arrays，慳 RAM）：
 *   today.json -> {"g":"2026-11-04 02:01","d":["2026-11-04","2026-11-05"],
 *                  "sports":{"badminton":{"v":[場地名...],"s":[區名...],"r":[[vIdx,dIdx,dateIdx,startMin,endMin,courts]...]}}}
 *
 * 需要 Library: ArduinoJson (>=7) — Arduino IDE Library Manager 搜 "ArduinoJson" by Benoit Blanchon
 *
 * 用法：
 *   1. 改 WIFI_SSID / WIFI_PASS
 *   2. 燒錄，開 Serial Monitor 115200
 *   3. 每 15 分鐘自動重新拉一次（同 worker 鏡像同步）
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

// Feed URLs（Pages，無 WAF，直接 GET）
const char* FEED_TODAY = "https://hkteddychan.github.io/smartplay-live/esp32/today.json";
// 想睇 7 日資料改用（每個 sport 一個檔，例如 badminton-7d.json ~幾十KB）：
// const char* FEED_7D   = "https://hkteddychan.github.io/smartplay-live/esp32/badminton-7d.json";

const unsigned long REFRESH_MS = 15UL * 60UL * 1000UL;  // 15 分鐘
const int LED_PIN = 2;  // 內置 LED：拉 data 成功閃 2 下，失敗長閃 5 下

// ---- 篩選設定（想淨係睇某啲區 / 晚間時段就改呢度）----
const char* MY_DISTRICTS[] = {"九龍城區", "黃大仙區", "觀塘區"};  // 空陣列 = 全部區
const int   N_MY_DISTRICTS = sizeof(MY_DISTRICTS) / sizeof(MY_DISTRICTS[0]);
const int   MIN_START_MIN  = 18 * 60;   // 18:00 之後先要（-1 = 全日）
const int   MIN_COURTS     = 1;          // 至少 N 個場

unsigned long lastFetch = 0;
int fetchCount = 0;

void blink(int times, int onMs = 150, int offMs = 150) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, HIGH); delay(onMs);
    digitalWrite(LED_PIN, LOW);  delay(offMs);
  }
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.printf("[WiFi] connecting to %s", WIFI_SSID);
  unsigned long t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(400);
    Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf(" OK, IP=%s, RSSI=%d dBm\n", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  } else {
    Serial.println(" FAILED");
  }
}

// HTTP GET -> String（with size guard）
bool httpGet(const char* url, String& out) {
  HTTPClient http;
  http.begin(url);
  http.setTimeout(15000);
  http.setUserAgent("SmartPlayLive-ESP32/1.0");
  int code = http.GET();
  if (code != 200) {
    Serial.printf("[HTTP] %s -> %d\n", url, code);
    http.end();
    return false;
  }
  // stream 讀，避免一次過 alloc
  int len = http.getSize();
  Serial.printf("[HTTP] %s -> 200, %d bytes\n", url, len);
  out.reserve(len > 0 ? len : 32768);
  WiFiClient* stream = http.getStreamPtr();
  uint8_t buf[1024];
  while (http.connected() && (len > 0 || len == -1)) {
    size_t avail = stream->available();
    if (avail) {
      int c = stream->readBytes(buf, ((avail > sizeof(buf)) ? sizeof(buf) : avail));
      out.concat((char*)buf, c);
      if (len > 0) len -= c;
    } else {
      delay(2);
    }
  }
  http.end();
  return true;
}

void fmtTime(int minutes, char* buf, size_t n) {
  snprintf(buf, n, "%02d:%02d", minutes / 60, minutes % 60);
}

void printSport(JsonObject sport, const char* sportName, JsonArray dates) {
  const char* todayStr = dates[0];
  const char* tmrwStr  = dates[1];

  JsonArray venues     = sport["v"];
  JsonArray districts  = sport["s"];
  JsonArray rows       = sport["r"];

  // 統計今日有幾多行符合 filter
  int matched = 0;
  for (JsonObject row : rows) {
    int vIdx = row[0], dIdx = row[1], dateIdx = row[2];
    int startMin = row[3], endMin = row[4], courts = row[5];
    if (dateIdx != 0) continue;                       // 淨係今日
    if (startMin < MIN_START_MIN) continue;           // 時段 filter
    if (courts < MIN_COURTS) continue;
    if (N_MY_DISTRICTS > 0) {
      const char* dist = districts[dIdx] | "";
      bool ok = false;
      for (int i = 0; i < N_MY_DISTRICTS; i++)
        if (strcmp(dist, MY_DISTRICTS[i]) == 0) { ok = true; break; }
      if (!ok) continue;
    }
    matched++;
  }
  Serial.printf("\n=== %s — 今日(%s)符合條件: %d 個時段 ===\n", sportName, todayStr, matched);
  if (matched == 0) { Serial.println("  (無)"); return; }

  char st[8], en[8];
  for (JsonObject row : rows) {
    int vIdx = row[0], dIdx = row[1], dateIdx = row[2];
    int startMin = row[3], endMin = row[4], courts = row[5];
    if (dateIdx >= 2) continue;         // 0=今日 1=聽日（7d feed 會有更多）
    if (startMin < MIN_START_MIN) continue;
    if (courts < MIN_COURTS) continue;
    if (N_MY_DISTRICTS > 0) {
      const char* dist = districts[dIdx] | "";
      bool ok = false;
      for (int i = 0; i < N_MY_DISTRICTS; i++)
        if (strcmp(dist, MY_DISTRICTS[i]) == 0) { ok = true; break; }
      if (!ok) continue;
    }
    fmtTime(startMin, st, sizeof(st));
    fmtTime(endMin, en, sizeof(en));
    const char* dateLabel = (dateIdx == 0) ? "今日" : "聽日";
    Serial.printf("  [%s|%s] %s | %s-%s | %d 場\n",
      dateLabel, districts[dIdx] | "?", venues[vIdx] | "?", st, en, courts);
  }
}

void processFeed(const String& body) {
  // today.json 全部 sport 加埋 ~幾十KB；JsonDocument 256KB 應該夠（PSRAM 可再加）
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    Serial.printf("[JSON] parse error: %s (body %u bytes)\n", err.c_str(), body.length());
    return;
  }
  const char* gen = doc["g"] | "?";
  Serial.printf("\n╔══════════════════════════════════════╗");
  Serial.printf("\n║  🏸 SmartPLAY Live  (更新: %s HKT)", gen);
  Serial.printf("\n╚══════════════════════════════════════╝\n");

  JsonObject sports = doc["sports"];
  for (JsonPair kv : sports) {
    printSport(kv.value(), kv.key().c_str(), doc["d"]);
  }
  Serial.println("\n--- done ---");
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("\n[SmartPLAY Live ESP32] boot v1.0");
  connectWiFi();
  fetchCount = 0;
  lastFetch = 0;  // 立即拉第一次
}

void loop() {
  if (millis() - lastFetch >= REFRESH_MS) {
    lastFetch = millis();
    if (WiFi.status() != WL_CONNECTED) connectWiFi();
    String body;
    fetchCount++;
    Serial.printf("\n[fetch #%d] %s\n", fetchCount, FEED_TODAY);
    if (httpGet(FEED_TODAY, body)) {
      processFeed(body);
      blink(2);  // success
    } else {
      Serial.println("[fetch] FAILED — will retry next cycle");
      blink(5, 400, 100);  // fail
    }
  }
  delay(1000);
}
