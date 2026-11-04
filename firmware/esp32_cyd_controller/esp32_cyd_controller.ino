/*
 * ============================================================
 * NEON SERPENT 3D — ESP32-CYD 240x320 無線控制器
 * ------------------------------------------------------------
 * 板子：ESP32-2432S028R（CYD，ILI9341 240x320 TFT + XPT2046 觸控）
 *
 * 功能：
 *   1) 開機在 TFT 顯示遊戲預覽圖（splash_data.h，由 tools/make-splash.mjs 產生）
 *   2) Wi-Fi 設定：SSID/密碼存入 NVS；沒有設定或連線失敗時，
 *      開啟熱點 "NEON-SERPENT-CYD"（密碼 serpent3d）+ 網頁設定入口
 *   3) 啟動 WebSocket server（port 8787），
 *      遊戲頁用 ?agentWs=ws://<板子IP>:8787 連入
 *   4) TFT 顯示即時戰況（分數 / 長度 / 速度 / 排行榜），
 *      螢幕下方為觸控方向鍵，BOOT 按鍵 = 暫停/恢復
 *
 * 通訊協定（namespace "neon-serpent-3d/1"）：
 *   板子 -> 遊戲：join / autopilot / command / pause / resume
 *   遊戲 -> 板子：hello / state / response
 *
 * 序列埠：115200 baud
 * ============================================================
 */

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <ESPmDNS.h>
#include <Preferences.h>
#include <WebSocketsServer.h>
#include <ArduinoJson.h>
#include <TFT_eSPI.h>

#include "splash_data.h"

/* ============================================================
   設定（可用 build flags 覆寫，例如 platformio.ini）
============================================================ */
#ifndef NEON_WIFI_SSID
#define NEON_WIFI_SSID ""          // 留空 = 第一次開機用 AP 設定入口
#endif
#ifndef NEON_WIFI_PASS
#define NEON_WIFI_PASS ""
#endif

#define AP_SSID      "NEON-SERPENT-CYD"
#define AP_PASS      "serpent3d"
#define WIFI_TIMEOUT 20000           // 連線逾時（ms），失敗轉設定入口

static const char *AGENT_NAMESPACE = "neon-serpent-3d/1";
static const char *DEVICE_NAME     = "ESP32-CYD";
static const char *DEVICE_COLOR    = "#9d7bff";

#define LED_PIN   2                  // CYD 藍色 LED：遊戲連結後常亮
#define BOOT_BTN  0                  // BOOT 按鍵：短按=暫停/恢復，長按3秒=清除設定

// 喇叭：CYD 板載擴大機（背面 2P 1.25mm JST 喇叭座）
#ifndef SPEAKER_PIN
#define SPEAKER_PIN 26
#endif
#ifndef HELLO_MELODY_ENABLED
#define HELLO_MELODY_ENABLED 1       // 設 0 可靜音開機問候曲
#endif

// XPT2046 觸控校正（依板子狀況可調；{xMin, xMax, yMin, yMax, rot}）
#ifndef TOUCH_CAL
#define TOUCH_CAL { 300, 3800, 300, 3800, 1 }
#endif

/* ---------- RGB565 調色板 ---------- */
#define COL_BG      0x0021   // #02050a 近黑
#define COL_HEADER  0x0083   // #04121a 深藍
#define COL_PANEL   0x0083
#define COL_LINE    0x2104   // 分隔線
#define COL_CYAN    0x67DD   // #5ffbf1
#define COL_MAGENTA 0xFD9A   // #ff2bd6
#define COL_AMBER   0xF589   // #ffb347
#define COL_VIOLET  0x9BDF   // #9d7bff
#define COL_TEXT    0xEFFF   // #eafffd
#define COL_MUTED   0x7D54   // 灰青

/* ============================================================
   全域狀態
============================================================ */
TFT_eSPI tft;
WebServer portal(80);
DNSServer dnsServer;
WebSocketsServer ws(8787);
Preferences prefs;

bool portalMode = false;
bool gameLinked = false;
bool autoOn     = false;
String wifiSsid;
String wifiPass;

char toastText[32] = "";
uint32_t toastUntil = 0;

struct SnakeRow {
  char name[12];
  uint16_t color;
  uint32_t score;
  bool alive;
};

struct HudState {
  bool valid;
  char game[8];        // menu / playing / paused
  uint32_t myScore;
  uint32_t myLen;
  uint32_t speedX10;
  uint32_t arenaCells;
  SnakeRow board[4];
  uint8_t boardCount;
};

HudState hud;            // 0-init：valid=false

uint16_t touchCal[5] = TOUCH_CAL;

/* ---------- 前置宣告 ---------- */
void drawStatus();
void drawScores();
void drawHelloBanner();
void playHelloMelody();
void showToast(const char *msg);
void sendJoin();
void sendAutopilot(bool on);
void sendCommand(const char *direction);
void sendSimple(const char *type);
void togglePauseCmd();

/* ============================================================
   小工具
============================================================ */
uint16_t hexTo565(const char *hex) {
  if (!hex || hex[0] != '#' || strlen(hex) < 7) return COL_MUTED;
  auto nib = [](char c) -> int {
    if (c >= '0' && c <= '9') return c - '0';
    c |= 0x20;
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return 0;
  };
  int r = (nib(hex[1]) << 4) | nib(hex[2]);
  int g = (nib(hex[3]) << 4) | nib(hex[4]);
  int b = (nib(hex[5]) << 4) | nib(hex[6]);
  return ((r * 31 + 127) / 255 << 11) | ((g * 63 + 127) / 255 << 5) | ((b * 31 + 127) / 255);
}

void showToast(const char *msg) {
  strlcpy(toastText, msg, sizeof(toastText));
  toastUntil = millis() + 1600;
  drawStatus();
}

/* ============================================================
   開機圖片：240x320 RGB565 RLE（preview.png 轉出）
============================================================ */
void drawSplash() {
  const uint8_t *p = splashRle;
  static uint16_t line[SPLASH_W];
  uint16_t run = 0;
  uint16_t color = 0;
  for (int y = 0; y < SPLASH_H; y++) {
    for (int x = 0; x < SPLASH_W;) {
      if (run == 0) {
        run = pgm_read_byte(p++);
        color = ((uint16_t)pgm_read_byte(p++) << 8) | pgm_read_byte(p++);
      }
      uint16_t take = run < (uint16_t)(SPLASH_W - x) ? run : (uint16_t)(SPLASH_W - x);
      for (uint16_t i = 0; i < take; i++) line[x + i] = color;
      x += take;
      run -= take;
    }
    tft.pushImage(0, y, SPLASH_W, 1, line);
  }
}

/* ---------- HELLO TEDDY 開機橫幅 ---------- */
void drawHelloBanner() {
  tft.fillRect(0, 268, 240, 52, COL_HEADER);
  tft.drawFastHLine(0, 268, 240, COL_LINE);
  tft.setTextFont(4);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(COL_AMBER, COL_HEADER);
  tft.drawString("HELLO TEDDY!", 120, 294);
  tft.setTextDatum(TL_DATUM);
}

/* ============================================================
   聲音：Hello Teddy 問候曲（自製簡短旋律，透過 GPIO26 擴大機）
============================================================ */
static void toneInit() {
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
  ledcAttach(SPEAKER_PIN, 4000, 10);
#else
  ledcSetup(0, 4000, 10);
  ledcAttachPin(SPEAKER_PIN, 0);
#endif
}

static void toneFreq(uint32_t freq) {
  if (freq == 0) freq = 1;  // ledcWriteTone(0) 停止輸出
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
  ledcWriteTone(SPEAKER_PIN, freq == 1 ? 0 : freq);
#else
  ledcWriteTone(0, freq == 1 ? 0 : freq);
#endif
}

void playHelloMelody() {
#if HELLO_MELODY_ENABLED
  static const uint32_t notes[][2] = {
    { 523, 200 },   // C5  "Hel-"
    { 659, 200 },   // E5  "-lo"
    { 784, 240 },   // G5  "Ted-"
    { 659, 180 },   // E5  "-dy"
    { 523, 260 },   // C5
    { 0, 70 },
    { 784, 200 },   // G5  歡呼短句
    { 1047, 160 },  // C6
    { 784, 160 },   // G5
    { 1047, 340 }   // C6
  };
  toneInit();
  for (const auto &note : notes) {
    toneFreq(note[0]);
    delay(note[1]);
  }
  toneFreq(0);
#endif
}

/* ============================================================
   HUD 繪製（所有螢幕文字皆為 ASCII，TFT 內建字型不含中文）
============================================================ */
void drawHeader() {
  tft.fillRect(0, 0, 240, 38, COL_HEADER);
  tft.setTextFont(2);
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(COL_CYAN, COL_HEADER);
  tft.drawString("NEON SERPENT 3D", 120, 11);
  tft.setTextFont(1);
  tft.setTextColor(COL_MUTED, COL_HEADER);
  tft.drawString("ESP32-CYD CONTROLLER", 120, 27);
  tft.setTextDatum(TL_DATUM);
  tft.drawFastHLine(0, 53, 240, COL_LINE);
}

void drawStatus() {
  tft.fillRect(0, 38, 240, 15, COL_HEADER);
  tft.setTextFont(1);
  tft.setTextDatum(TL_DATUM);
  if (portalMode) {
    tft.setTextColor(COL_AMBER, COL_HEADER);
    tft.drawString("SETUP: JOIN WIFI " AP_SSID, 4, 41);
    return;
  }
  if (toastUntil && millis() < toastUntil) {
    tft.setTextColor(COL_AMBER, COL_HEADER);
    tft.drawString(toastText, 4, 41);
    return;
  }
  if (WiFi.status() != WL_CONNECTED) {
    tft.setTextColor(COL_MAGENTA, COL_HEADER);
    tft.drawString("WIFI DOWN / RECONNECTING", 4, 41);
    return;
  }
  char line[48];
  snprintf(line, sizeof(line), "%s %lddBm %s",
           WiFi.localIP().toString().c_str(),
           (long)WiFi.RSSI(),
           gameLinked ? "LINK" : "WAIT");
  tft.setTextColor(gameLinked ? COL_CYAN : COL_MUTED, COL_HEADER);
  tft.drawString(line, 4, 41);
}

void drawScores() {
  tft.fillRect(0, 54, 240, 162, COL_PANEL);
  tft.setTextDatum(TC_DATUM);
  tft.setTextFont(1);
  tft.setTextColor(COL_MUTED, COL_PANEL);
  tft.drawString(hud.valid ? "DEVICE SNAKE SCORE" : "WAITING FOR GAME", 120, 58);

  if (hud.valid) {
    char buf[20];
    tft.setTextFont(7);
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(strcmp(hud.game, "playing") == 0 ? COL_CYAN : COL_AMBER, COL_PANEL);
    snprintf(buf, sizeof(buf), "%06lu", (unsigned long)hud.myScore);
    tft.drawString(buf, 120, 92);
    tft.setTextFont(2);
    tft.setTextColor(COL_TEXT, COL_PANEL);
    snprintf(buf, sizeof(buf), "LEN %lu  SPD %lu.%lux",
             (unsigned long)hud.myLen,
             (unsigned long)(hud.speedX10 / 10),
             (unsigned long)(hud.speedX10 % 10));
    tft.drawString(buf, 120, 122);
  }

  tft.setTextDatum(TL_DATUM);
  tft.setTextFont(1);
  tft.setTextColor(COL_MUTED, COL_PANEL);
  tft.drawString("ARENA FEED", 6, 132);
  for (uint8_t i = 0; i < hud.boardCount; i++) {
    int y = 144 + i * 17;
    tft.fillRect(6, y + 4, 5, 5, hud.board[i].color);
    tft.setTextFont(2);
    tft.setTextColor(hud.board[i].alive ? COL_TEXT : COL_MUTED, COL_PANEL);
    tft.drawString(hud.board[i].name, 16, y);
    char sc[12];
    snprintf(sc, sizeof(sc), "%lu", (unsigned long)hud.board[i].score);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(sc, 234, y);
    tft.setTextDatum(TL_DATUM);
  }
}

/* ---------- 觸控按鍵（軸向與網頁版觸控板一致） ---------- */
enum ZoneAction { ZA_DIR, ZA_PAUSE, ZA_AUTO };

struct Zone {
  int16_t x, y, w, h;
  const char *label;
  const char *dir;
  ZoneAction action;
  uint16_t color;
};

static const Zone ZONES[] = {
  {   2, 222, 56, 46, "AUTO",  nullptr, ZA_AUTO,  COL_VIOLET },
  {  62, 222, 56, 46, "FWD",   "-z",    ZA_DIR,   COL_CYAN   },
  { 122, 222, 56, 46, "PAUSE", nullptr, ZA_PAUSE, COL_MAGENTA },
  { 182, 222, 56, 46, "Y+",    "+y",    ZA_DIR,   COL_AMBER  },
  {   2, 272, 56, 46, "LT",    "-x",    ZA_DIR,   COL_CYAN   },
  {  62, 272, 56, 46, "BACK",  "+z",    ZA_DIR,   COL_CYAN   },
  { 122, 272, 56, 46, "RT",    "+x",    ZA_DIR,   COL_CYAN   },
  { 182, 272, 56, 46, "Y-",    "-y",    ZA_DIR,   COL_AMBER  },
};

void drawZone(const Zone &z, bool active) {
  uint16_t bg = active ? z.color : COL_PANEL;
  uint16_t fg = active ? COL_BG : z.color;
  tft.fillRoundRect(z.x, z.y, z.w, z.h, 6, bg);
  tft.drawRoundRect(z.x, z.y, z.w, z.h, 6, z.color);
  tft.setTextDatum(MC_DATUM);
  tft.setTextFont(2);
  tft.setTextColor(fg, bg);
  if (z.action == ZA_AUTO) tft.drawString(autoOn ? "AUTO*" : "AUTO", z.x + z.w / 2, z.y + z.h / 2);
  else tft.drawString(z.label, z.x + z.w / 2, z.y + z.h / 2);
  tft.setTextDatum(TL_DATUM);
}

void drawPad() {
  tft.fillRect(0, 218, 240, 102, COL_BG);
  for (const Zone &z : ZONES) drawZone(z, false);
}

void drawPortalScreen() {
  drawHeader();
  drawStatus();
  tft.fillRect(0, 54, 240, 266, COL_BG);
  tft.setTextDatum(MC_DATUM);
  tft.setTextFont(2);
  tft.setTextColor(COL_TEXT, COL_BG);
  tft.drawString("WIFI SETUP MODE", 120, 74);
  tft.setTextFont(2);
  tft.setTextColor(COL_MUTED, COL_BG);
  tft.drawString("1) WiFi: " AP_SSID, 120, 110);
  tft.drawString("2) pass: " AP_PASS, 120, 132);
  tft.drawString("3) open:", 120, 166);
  tft.setTextColor(COL_CYAN, COL_BG);
  tft.drawString("http://192.168.4.1", 120, 188);
  tft.setTextColor(COL_MUTED, COL_BG);
  tft.drawString("4) save home WiFi", 120, 222);
  tft.drawString("waiting ...", 120, 256);
  tft.setTextDatum(TL_DATUM);
}

void drawRunScreen() {
  drawHeader();
  drawStatus();
  drawScores();
  drawPad();
}

/* ============================================================
   對遊戲送出指令（namespace: neon-serpent-3d/1）
============================================================ */
void wsSendObject(JsonDocument &doc) {
  doc["namespace"] = AGENT_NAMESPACE;
  String out;
  serializeJson(doc, out);
  Serial.printf("[WS->] %s\n", out.c_str());
  ws.broadcastTXT(out.c_str(), out.length());
}

void sendJoin() {
  JsonDocument doc;
  doc["type"] = "join";
  doc["payload"]["name"] = DEVICE_NAME;
  doc["payload"]["color"] = DEVICE_COLOR;
  wsSendObject(doc);
}

void sendAutopilot(bool on) {
  JsonDocument doc;
  doc["type"] = "autopilot";
  doc["payload"]["enabled"] = on;
  wsSendObject(doc);
}

void sendCommand(const char *direction) {
  JsonDocument doc;
  doc["type"] = "command";
  doc["payload"]["direction"] = direction;
  wsSendObject(doc);
}

void sendSimple(const char *type) {
  JsonDocument doc;
  doc["type"] = type;
  wsSendObject(doc);
}

void togglePauseCmd() {
  if (!gameLinked) { showToast("NO GAME LINK"); return; }
  if (strcmp(hud.game, "playing") == 0) { sendSimple("pause"); showToast("PAUSE SENT"); }
  else { sendSimple("resume"); showToast("RESUME SENT"); }
}

/* ============================================================
   解析遊戲 state 訊息 -> HUD
============================================================ */
void parseState(JsonDocument &doc) {
  HudState next;
  memset(&next, 0, sizeof(next));
  const char *gs = doc["state"] | "menu";
  strlcpy(next.game, gs, sizeof(next.game));
  next.arenaCells = doc["arena"]["size"] | 0;
  double spd = doc["simulation"]["speed"] | 1.0;
  next.speedX10 = (uint32_t)(spd * 10.0 + 0.5);

  bool foundAgent = false;

  for (JsonObject s : doc["snakes"].as<JsonArray>()) {
    String kind = s["kind"] | "";
    if (kind != "agent") continue;
    next.myScore = s["score"] | 0;
    next.myLen = s["length"] | 0;
    foundAgent = true;
    break;
  }

  // 遊戲被 reset／restart 後 Agent 蛇會消失 -> 自動重新 join（3 秒節流）
  static uint32_t lastRejoinMs = 0;
  if (!foundAgent && millis() - lastRejoinMs > 3000) {
    lastRejoinMs = millis();
    sendJoin();
    sendAutopilot(false);
    showToast("REJOIN SENT");
  }

  uint8_t i = 0;
  for (JsonObject row : doc["leaderboard"].as<JsonArray>()) {
    if (i >= 4) break;
    const char *n = row["name"] | "---";
    strlcpy(next.board[i].name, n, sizeof(next.board[i].name));
    next.board[i].color = hexTo565(row["color"] | "#7caaa6");
    next.board[i].score = row["score"] | 0;
    next.board[i].alive = row["alive"] | false;
    i++;
  }
  next.boardCount = i;
  next.valid = true;
  hud = next;
  drawScores();
}

/* ============================================================
   WebSocket 事件
============================================================ */
void onWsEvent(uint8_t num, WStype_t type, uint8_t *payload, size_t len) {
  switch (type) {
    case WStype_CONNECTED:
      Serial.printf("[WS] client %u connected from %s\n", num, ws.remoteIP(num).toString().c_str());
      break;
    case WStype_DISCONNECTED:
      if (gameLinked) {
        gameLinked = false;
        autoOn = false;
        drawScores();
        showToast("GAME UNLINKED");
      }
      break;
    case WStype_TEXT: {
      JsonDocument doc;
      DeserializationError err = deserializeJson(doc, payload, len);
      if (err) {
        Serial.printf("[WS] json error: %s\n", err.c_str());
        return;
      }
      const char *msgType = doc["type"] | "";
      if (strcmp(msgType, "hello") == 0) {
        gameLinked = true;
        autoOn = false;
        sendJoin();          // 加入自己的 Agent 蛇（滿場時替換一個 AI）
        sendAutopilot(false);
        showToast("GAME LINKED");
      } else if (strcmp(msgType, "state") == 0) {
        parseState(doc);
      }
      // response / 其他訊息忽略
      break;
    }
    default:
      break;
  }
}

/* ============================================================
   Wi-Fi 連線 + AP 設定入口
============================================================ */
bool connectWifi(uint32_t timeoutMs) {
  wifiSsid = prefs.getString("ssid", String(NEON_WIFI_SSID));
  wifiPass = prefs.getString("pass", String(NEON_WIFI_PASS));
  if (!wifiSsid.length()) return false;
  Serial.printf("[WiFi] connecting to \"%s\"\n", wifiSsid.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    if (millis() - start > timeoutMs) {
      Serial.println("\n[WiFi] connect timeout");
      return false;
    }
    delay(250);
    Serial.print(".");
  }
  Serial.printf("\n[WiFi] connected, IP: %s\n", WiFi.localIP().toString().c_str());
  return true;
}

void handlePortalRoot() {
  String page = F(
    "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\">"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
    "<title>NEON SERPENT - WiFi 設定</title><style>"
    "body{background:#02050a;color:#dcfffb;font-family:system-ui,sans-serif;"
    "display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}"
    "form{background:#04121a;border:1px solid #0e554f;border-radius:12px;padding:24px;max-width:320px;width:92%}"
    "h1{font-size:18px;color:#5ffbf1;margin:0 0 4px}p{color:#8fc9c4;font-size:13px;margin:0 0 18px}"
    "label{display:block;font-size:12px;color:#9ededa;margin:12px 0 4px}"
    "input{width:100%;box-sizing:border-box;padding:10px;border-radius:8px;border:1px solid #1c6b64;"
    "background:#02050a;color:#eafffd;font-size:14px}"
    "button{width:100%;margin-top:18px;padding:12px;border:0;border-radius:8px;background:#5ffbf1;"
    "color:#021014;font-weight:700;font-size:14px;cursor:pointer}"
    "code{color:#ffb347;font-size:11px;word-break:break-all}</style></head><body><form>"
    "<h1>NEON SERPENT 3D</h1><p>ESP32-CYD 控制器 Wi-Fi 設定</p>"
    "<label>Wi-Fi 名稱 (SSID)<input name=\"ssid\" required maxlength=\"32\"></label>"
    "<label>Wi-Fi 密碼<input name=\"pass\" type=\"password\" maxlength=\"64\"></label>"
    "<button>連線並重新啟動</button></form></body></html>");
  portal.send(200, "text/html", page);
}

void handlePortalSave() {
  String ssid = portal.arg("ssid");
  String pass = portal.arg("pass");
  if (!ssid.length()) {
    portal.send(400, "text/plain", "SSID required");
    return;
  }
  prefs.putString("ssid", ssid);
  prefs.putString("pass", pass);
  Serial.printf("[Portal] saved ssid=\"%s\", rebooting\n", ssid.c_str());
  portal.send(200, "text/html",
              "<!doctype html><meta charset=\"utf-8\"><body style=\"background:#02050a;color:#5ffbf1;"
              "font-family:system-ui;text-align:center;padding-top:40vh\">"
              "已儲存，板子重新啟動中...</body>");
  delay(1200);
  ESP.restart();
}

void startPortal() {
  portalMode = true;
  WiFi.mode(WIFI_AP);
  WiFi.softAP(AP_SSID, AP_PASS);
  delay(120);
  dnsServer.start(53, "*", WiFi.softAPIP());
  portal.on("/", HTTP_GET, handlePortalRoot);
  portal.on("/save", HTTP_ANY, handlePortalSave);
  portal.onNotFound([]() {
    portal.sendHeader("Location", String("http://") + WiFi.softAPIP().toString() + "/");
    portal.send(302, "text/plain", "");
  });
  portal.begin();
  drawPortalScreen();
  Serial.printf("[Portal] AP \"%s\" / \"%s\" -> http://%s\n",
                AP_SSID, AP_PASS, WiFi.softAPIP().toString().c_str());
}

void startRunMode() {
  portalMode = false;
  if (MDNS.begin("neon-serpent-cyd")) {
    MDNS.addService("http", "tcp", 80);
  }
  ws.begin();
  ws.onEvent(onWsEvent);
  drawRunScreen();
  Serial.printf("[WS] server on ws://%s:8787\n", WiFi.localIP().toString().c_str());
}

/* ============================================================
   輸入：觸控 + BOOT 按鍵
============================================================ */
void handleTouch() {
  static bool touchDown = false;
  uint16_t tx, ty;
  bool touched = tft.getTouch(&tx, &ty);
  if (touched && !touchDown) {
    touchDown = true;
    for (const Zone &z : ZONES) {
      if (tx >= z.x && tx < z.x + z.w && ty >= z.y && ty < z.y + z.h) {
        drawZone(z, true);
        if (!gameLinked) showToast("NO GAME LINK");
        else if (z.action == ZA_DIR) sendCommand(z.dir);
        else if (z.action == ZA_PAUSE) togglePauseCmd();
        else if (z.action == ZA_AUTO) {
          autoOn = !autoOn;
          sendAutopilot(autoOn);
          showToast(autoOn ? "AUTOPILOT ON" : "AUTOPILOT OFF");
        }
        delay(140);
        drawZone(z, false);
        break;
      }
    }
  } else if (!touched) {
    touchDown = false;
  }
}

void handleBootButton() {
  static uint32_t pressStart = 0;
  bool pressed = digitalRead(BOOT_BTN) == LOW;
  if (pressed && pressStart == 0) pressStart = millis();
  if (!pressed && pressStart > 0) {
    uint32_t held = millis() - pressStart;
    pressStart = 0;
    if (held > 40 && held <= 3000) togglePauseCmd();
  }
  if (pressed && pressStart > 0 && millis() - pressStart > 3000) {
    Serial.println("[BTN] long press -> clear settings, reboot");
    prefs.clear();
    delay(300);
    ESP.restart();
  }
}

/* ============================================================
   setup / loop
============================================================ */
void watchWifi() {
  static uint32_t lastOk = 0;
  static bool first = true;
  if (WiFi.status() == WL_CONNECTED) {
    lastOk = millis();
    first = false;
    return;
  }
  if (first) lastOk = millis();
  if (millis() - lastOk > 30000) {
    Serial.println("[WiFi] lost > 30s, rebooting");
    delay(200);
    ESP.restart();
  }
}

void setup() {
  Serial.begin(115200);
  delay(150);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BOOT_BTN, INPUT_PULLUP);
  WiFi.persistent(false);

  tft.init();
  tft.setRotation(0);
  tft.fillScreen(COL_BG);
  tft.setTouch(touchCal);

  drawSplash();               // 開機顯示圖片（assets/hello.png 或 preview.png）
  drawHelloBanner();          // HELLO TEDDY! 橫幅
  playHelloMelody();          // GPIO26 喇叭播放問候曲
  delay(600);

  prefs.begin("serpent-cfg", false);

  if (!connectWifi(WIFI_TIMEOUT)) {
    Serial.println("[WiFi] -> setup portal");
    startPortal();
  } else {
    startRunMode();
  }
}

void loop() {
  if (portalMode) {
    dnsServer.processNextRequest();
    portal.handleClient();
    digitalWrite(LED_PIN, (millis() / 400) % 2);   // 設定模式：LED 慢閃
    return;
  }
  ws.loop();
  handleTouch();
  handleBootButton();
  digitalWrite(LED_PIN, gameLinked ? HIGH : LOW);  // 遊戲連結：LED 常亮
  if (toastUntil && millis() > toastUntil) {
    toastUntil = 0;
    drawStatus();
  }
  watchWifi();
}
