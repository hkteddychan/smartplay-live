/*
 * SmartPLAY Live — ESP32 放場通知器 v2.1
 * ================================================
 * 純粹一個功能：每 3 分鐘 poll changes-eve.json，
 * 偵測到「晚上場次放咗出嚟」（📈餘額增加 / 🆕新時段）就 buzzer beep。
 *
 * 唔顯示場次清單 — 呢個裝置只做一件事：有場放就話你知。
 * 想睇今晚有咩場：用網站 https://hkteddychan.github.io/smartplay-live/
 *
 * Feed（backend 已過濾：淨係晚上 ≥18:00 + 淨係可預訂日，排除未開賣 day-7）：
 *   https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json
 *   格式: {"g":"生成時間","sports":{sport:[["日期","場地","設施",起分,完分,"chg|new|gone",舊,新],...]}}
 *
 * 需要 Library: ArduinoJson (>=7) — Arduino IDE Library Manager 搜 "ArduinoJson"
 *
 * 用法：
 *   1. 改 WIFI_SSID / WIFI_PASS
 *   2. 燒錄，開 Serial Monitor 115200
 *   3. 第一輪 poll = baseline（唔 beep），之後有 📈 放場先 beep
 *
 * 接線: 被動 buzzer → GPIO25(+)/GND(−)。冇駁 buzzer 都唔會壞，淨係冇聲。
 */

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "YOUR_WIFI_SSID";
const char* WIFI_PASS = "YOUR_WIFI_PASSWORD";

const char* FEED_CHANGES_EVE = "https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json";
const unsigned long EVE_POLL_MS = 90UL * 1000UL;   // 90 秒 poll 一次（mirror */2 加密後，延遲 ≤ 3 分鐘）

const int LED_PIN    = 2;    // 內置 LED：poll 成功閃 1 下，失敗長閃 5 下
const int BUZZER_PIN = 25;   // 被動 buzzer

String lastEveVersion = "";  // "g" 版本指紋 — 冇變就咩都唔做
bool   baselined = false;    // 第一輪只做 baseline，唔 beep（避免開機誤鳴）
int    beepQueue = 0;        // 放場次數 — main loop 度 beep

unsigned long lastPoll = 0;

void blink(int times, int onMs = 150, int offMs = 150) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, HIGH); delay(onMs);
    digitalWrite(LED_PIN, LOW);  delay(offMs);
  }
}

void beep(int times, int onMs = 120, int offMs = 80) {
  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER_PIN, HIGH); delay(onMs);
    digitalWrite(BUZZER_PIN, LOW);  delay(offMs);
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

bool httpGet(const char* url, String& out) {
  HTTPClient http;
  http.begin(url);
  http.setTimeout(15000);
  http.setUserAgent("SmartPlayLive-ESP32/2.1");
  int code = http.GET();
  if (code != 200) {
    Serial.printf("[HTTP] %s -> %d\n", url, code);
    http.end();
    return false;
  }
  int len = http.getSize();
  out.reserve(len > 0 ? len : 4096);
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

void processEveChanges(const String& body) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    Serial.printf("[EVE] parse error: %s\n", err.c_str());
    return;
  }
  const char* gen = doc["g"] | "";
  if (gen == lastEveVersion) {          // 版本冇變 — 咩都唔使做
    Serial.println("[EVE] no change");
    return;
  }
  bool firstRun = !baselined;
  lastEveVersion = gen;
  baselined = true;

  JsonObject sports = doc["sports"];
  int nRelease = 0, nLost = 0;
  char st[8], en[8];
  if (firstRun) {
    Serial.println("[EVE] first run — baseline (no beep)");
  } else {
    Serial.println("\n🔔🔔🔔 晚上放場偵測 🔔🔔🔔");
  }
  for (JsonPair kv : sports) {
    const char* sportName = kv.key().c_str();
    for (JsonArray c : kv.value()) {
      // c = [date, venue, loc, startMin, endMin, kind, oldC, newC]
      const char* date  = c[0] | "?";
      const char* venue = c[1] | "?";
      const char* loc   = c[2] | "";
      int sm = c[3] | 0, em = c[4] | 0;
      const char* kind = c[5] | "";
      int oldC = c[6] | 0, newC = c[7] | 0;
      bool isRelease = (strcmp(kind, "chg") == 0 && newC > oldC) || strcmp(kind, "new") == 0;
      if (isRelease) { nRelease++; if (!firstRun) beepQueue++; }
      else           { nLost++; }
      if (!firstRun) {
        fmtTime(sm, st, sizeof(st)); fmtTime(em, en, sizeof(en));
        if (isRelease)
          Serial.printf("  📈 [%s] %s %s | %s %s-%s | %d→%d 場 🔔\n", sportName, venue, loc, date, st, en, oldC, newC);
        else if (strcmp(kind, "gone") == 0)
          Serial.printf("  ❌ [%s] %s %s | %s %s-%s | 消失（原本 %d 場）\n", sportName, venue, loc, date, st, en, oldC);
        else
          Serial.printf("  📉 [%s] %s %s | %s %s-%s | %d→%d 場\n", sportName, venue, loc, date, st, en, oldC, newC);
      }
    }
  }
  if (!firstRun) {
    Serial.printf("🔔 %d 個放場（beep）| %d 個被訂走（靜默）\n", nRelease, nLost);
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  Serial.println("\n[SmartPLAY Live ESP32] boot v2.2 — 放場通知器（release-only）");
  Serial.println("feed: changes-eve.json | poll: 3min | beep on: 📈放場/🆕新時段");
  connectWiFi();
  lastPoll = 0;   // 立即 poll 第一次（baseline）
}

void loop() {
  unsigned long now = millis();
  if (now - lastPoll >= EVE_POLL_MS) {
    lastPoll = now;
    if (WiFi.status() != WL_CONNECTED) connectWiFi();
    String body;
    Serial.printf("\n[poll] changes-eve.json\n");
    if (httpGet(FEED_CHANGES_EVE, body)) {
      processEveChanges(body);
      blink(1);                      // poll OK
    } else {
      Serial.println("[poll] FAILED — retry next cycle");
      blink(5, 400, 100);            // fail
    }
  }
  if (beepQueue > 0) {
    beep(min(beepQueue, 5));         // 最多 beep 5 下
    beepQueue = 0;
  }
  delay(200);
}
