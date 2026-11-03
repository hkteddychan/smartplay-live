# 🏸 SmartPLAY Live × ESP32 — Build Handoff（v2.0 晚上放場警報）

> 📅 2026-11-04 產生 · 俾 build 直接實現用
> 目標：ESP32 連 Wi-Fi，定時拉 SmartPLAY Live feed，**晚上場次有人放場就 buzzer 呻你**

---

## 1. 系統架構

```
LCSD 開放數據 ← 15min ← Cloudflare Worker 鏡像 ← GitHub repo
                                                     ↓ (每次 push)
                                        Build ESP32 Feed workflow
                                                     ↓
                        https://hkteddychan.github.io/smartplay-live/esp32/
                             ↓                        ↓
                    today.json (15min 更新)    changes-eve.json (放場偵測)
                             ↓                        ↓
                    ESP32: 場地明細顯示      ESP32: 📈放場 → buzzer beep
```

**Feed endpoint（全部 HTTPS GET、無 auth、無 WAF）：**

| Endpoint | 內容 | 大細 | Poll 週期 |
|---|---|---|---|
| `esp32/today.json` | 5 種運動今日+聽日全部有餘額時段 | ~35KB | 15 分鐘 |
| `esp32/changes-eve.json` | **淨係晚上（≥18:00）+ 淨係可預訂日（已排除未開放嘅 day-7）** | <1KB | 3 分鐘 |
| `esp32/{sport}-7d.json` | 單運動 7 日（optional） | 13–80KB | 按需 |

## 2. changes-eve.json 格式

```json
{
  "g": "2026-11-04 05:07",                // 生成時間 HKT — 版本指紋，冇變=冇新嘢
  "prev": {"badminton": "2026-11-04 04:52"},
  "sports": {
    "badminton": [
      ["2026-11-05", "香港單車館", "主場", 1080, 1140, "chg", 1, 3],
    //  ↑日期        ↑場地       ↑設施  ↑起   ↑完   ↑類型  ↑舊 ↑新
    //  類型: "chg"=餘額變動 "new"=新時段 "gone"=時段消失
    //  📈放場 = (kind=="chg" && new>old) || kind=="new"
    ]
  }
}
```

**已內置過濾（backend 做咗，ESP32 唔使理）：**
- ✅ 淨係晚上場（start ≥ 18:00 = startMin ≥ 1080）
- ✅ 排除 day-7（未開放預訂，LCSD 半夜成批放會炸幾百條假警報）
- ✅ 淨係有餘額相關嘅變化

## 3. 硬件需求

| 組件 | 接線 | 備註 |
|---|---|---|
| ESP32 DevKit | — | 任何 board 得 |
| 被動 buzzer | GPIO25 ↔ buzzer(+)，GND ↔ buzzer(−) | **冇駁都唔會壞**，淨係冇聲 |
| 內置 LED | GPIO2 | 已有 |

## 4. Library

Arduino IDE → Library Manager → **ArduinoJson by Benoit Blanchon（v7+）**

## 5. 完整 Sketch（直接燒）

改 `WIFI_SSID` / `WIFI_PASS` 兩行就OK：

```cpp
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

const unsigned long REFRESH_MS = 15UL * 60UL * 1000UL;  // 15 分鐘 — today.json
const unsigned long EVE_POLL_MS = 3UL * 60UL * 1000UL;  // 3 分鐘 — changes-eve.json（放場要快知）
const int LED_PIN = 2;  // 內置 LED：拉 data 成功閃 2 下，失敗長閃 5 下
const int BUZZER_PIN = 25;  // 被動 buzzer GPIO（冇駁 buzzer 唔會壞，淨係冇聲）

// ---- 篩選設定（想淨係睇某啲區 / 晚間時段就改呢度）----
const char* MY_DISTRICTS[] = {"九龍城區", "黃大仙區", "觀塘區"};  // 空陣列 = 全部區
const int   N_MY_DISTRICTS = sizeof(MY_DISTRICTS) / sizeof(MY_DISTRICTS[0]);
const int   MIN_START_MIN  = 18 * 60;   // 18:00 之後先要（-1 = 全日）
const int   MIN_COURTS     = 1;          // 至少 N 個場

// ---- 放場通知（changes-eve.json）----
const char* FEED_CHANGES_EVE = "https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json";
String lastEveVersion = "";   // changes-eve "g" 值 — 冇變就唔使再 beep
int beepQueue = 0;            // 放場次數 — main loop 度 beep（唔阻塞 network）

unsigned long lastFetch = 0;
unsigned long lastEvePoll = 0;
int fetchCount = 0;

void beep(int times, int onMs = 120, int offMs = 80) {
  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER_PIN, HIGH); delay(onMs);
    digitalWrite(BUZZER_PIN, LOW);  delay(offMs);
  }
}

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

// ---------- changes-eve.json poll：偵測「晚上有場放咗」----------
void processEveChanges(const String& body) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    Serial.printf("[EVE] parse error: %s\n", err.c_str());
    return;
  }
  const char* gen = doc["g"] | "";
  if (lastEveVersion.length() > 0 && gen == lastEveVersion) {
    Serial.println("[EVE] no change (same version)");
    return;
  }
  bool firstRun = (lastEveVersion.length() == 0);
  lastEveVersion = gen;

  JsonObject sports = doc["sports"];
  int nReleased = 0, nNew = 0, nLost = 0;
  char st[8], en[8];
  Serial.println(firstRun ? "[EVE] first run — baseline only" : "\n🌙🌙🌙 晚上場次變化 🌙🌙🌙");
  for (JsonPair kv : sports) {
    const char* sportName = kv.key().c_str();
    JsonArray changes = kv.value();
    for (JsonArray c : changes) {
      // c = [date, venue, loc, startMin, endMin, kind, oldC, newC]
      const char* date = c[0] | "?";
      const char* venue = c[1] | "?";
      const char* loc = c[2] | "";
      int sm = c[3] | 0, em = c[4] | 0;
      const char* kind = c[5] | "";
      int oldC = c[6] | 0, newC = c[7] | 0;
      // district filter — changes.json 冇 district idx，用 venue 名過濾唔到區，
      // 所以 changes-eve 淨係做「有冇放場」觸發；明細照印
      bool isRelease = (strcmp(kind, "chg") == 0 && newC > oldC) || strcmp(kind, "new") == 0;
      if (isRelease) { nReleased++; nNew++; beepQueue++; }
      else { nLost++; }
      if (!firstRun) {
        fmtTime(sm, st, sizeof(st)); fmtTime(em, en, sizeof(en));
        if (isRelease)
          Serial.printf("  📈 [%s] %s %s | %s-%s | %d→%d 場 🔔\n", sportName, venue, loc, st, en, oldC, newC);
        else if (strcmp(kind, "gone") == 0)
          Serial.printf("  ❌ [%s] %s %s | %s-%s | 消失（原本 %d 場）\n", sportName, venue, loc, st, en, oldC);
        else
          Serial.printf("  📉 [%s] %s %s | %s-%s | %d→%d 場\n", sportName, venue, loc, st, en, oldC, newC);
      }
    }
  }
  if (!firstRun) {
    Serial.printf("🌙 共 %d 個放場/新增 🔔 | %d 個被訂/消失\n", nReleased, nLost);
  }
}

void pollEveChanges() {
  if (WiFi.status() != WL_CONNECTED) connectWiFi();
  String body;
  if (httpGet(FEED_CHANGES_EVE, body)) {
    processEveChanges(body);
  } else {
    Serial.println("[EVE] poll FAILED — retry next cycle");
  }
}

void setup() {
  Serial.begin(115200);
  delay(300);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  Serial.println("\n[SmartPLAY Live ESP32] boot v2.0 (evening release alert)");
  connectWiFi();
  fetchCount = 0;
  lastFetch = 0;      // 立即拉 today.json
  lastEvePoll = 0;    // 立即 poll changes-eve.json（first run = baseline）
}

void loop() {
  unsigned long now = millis();
  // 15 分鐘：today.json 明細
  if (now - lastFetch >= REFRESH_MS) {
    lastFetch = now;
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
  // 3 分鐘：changes-eve.json 放場偵測
  if (now - lastEvePoll >= EVE_POLL_MS) {
    lastEvePoll = now;
    pollEveChanges();
  }
  // beep queue — 唔阻塞 network
  if (beepQueue > 0) {
    beep(min(beepQueue, 5));   // 最多 beep 5 下，唔好嘈到暈
    beepQueue = 0;
  }
  delay(200);
}

```

## 6. 行為規格（驗收 checklist）

| 行為 | 預期 |
|---|---|
| 開機 | Serial 115200 顯示 `[SmartPLAY Live ESP32] boot v2.0 (evening release alert)` |
| 第一輪 poll changes-eve | `[EVE] first run — baseline only`（唔 beep，記住版本） |
| 之後每 3 分鐘 poll | 版本冇變：`[EVE] no change (same version)` |
| 放場出現（chg new>old 或 new） | Serial 印 `📈 [sport] 場地 設施 · HH:MM-HH:MM · 1→3 場 🔔` + **buzzer beep**（最多5下） |
| 場被訂走（chg new<old / gone） | Serial 印 📉 / ❌ — **唔 beep** |
| 每 15 分鐘 | 拉 today.json，印今日+聽日符合條件場次（九龍城/黃大仙/觀塘 + 18:00後 + ≥1場） |
| HTTP 失敗 | LED 長閃 5 下，下個週期重試 |
| 成功 | LED 閃 2 下 |

**District filter 注意**：today.json 明細有 district 過濾；changes-eve.json 冇 district 欄位（已喺 backend 收窄到晚上+可訂日），所以放場通知係全區觸發。如果之後想連放場都限區，要 backend 加 district 入 changes-eve — 已知 limitation，非 bug。

## 7. 攞最新檔案

- Sketch: https://raw.githubusercontent.com/hkteddychan/smartplay-live/main/esp32/smartplay_live_esp32.ino
- Feed: https://hkteddychan.github.io/smartplay-live/esp32/changes-eve.json
- Repo: https://github.com/hkteddychan/smartplay-live/tree/main/esp32

## 8. 未來 Enhancements（ optional，做咗上面先講）

1. **OLED 顯示**（SSD1306 I2C）— 今日晚上有咩場一目了然
2. **District 入 changes-eve** — 放場都限區（backend 改 5 行）
3. **多 beep 模式** — 放場=2短1長，被訂走=1長（而家淨係放場 beep）
4. **NTP 時間同步** — 顯示真實時鐘 + 淨係夜晚 6 點後先開聲
5. **Deep sleep** — 電池供電時慢電（而家假設 USB 常插）
