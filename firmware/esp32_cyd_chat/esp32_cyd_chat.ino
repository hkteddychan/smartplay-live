/* =====================================================================
   AI MATH TUTOR  v1.0   --   ESP32-2432S028R "Cheap Yellow Display"
   ---------------------------------------------------------------------
   A touch chat toy for high-intelligence equation Q&A.

   Architecture adapted from github.com/kano92-dir/CYD-AI-CHAT (MIT):
     * separate VSPI bus for the XPT2046 touch panel
     * explicit app state machine (wifi -> keyboard -> chat -> settings)
     * layered on-screen QWERTY / math keyboard
     * word-wrapped chat bubbles, drag scrolling, viewport clipping
     * chat memory in NVS
     * OpenRouter with automatic model fallback (free models)
     * RGB status LED: blue = thinking, green = ok, red = error

   Runs in DEMO mode (canned answers) until you put an API key in
   platformio.ini -> CHAT_API_KEY.

   Libraries: TFT_eSPI, XPT2046_Touchscreen, ArduinoJson 7
   Board:     ESP32 Dev Module, 115200 baud
   ===================================================================== */

#include <TFT_eSPI.h>
#include <XPT2046_Touchscreen.h>
#include <SPI.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <time.h>
#include <vector>
#include <algorithm>

#include "cjk_font.h"

#define APP_VERSION "v1.0"

/* ---------------------------------------------------------------------
   AI CONFIG  (key comes from platformio.ini build flag)
   --------------------------------------------------------------------- */
#ifndef CHAT_API_KEY
#define CHAT_API_KEY ""
#endif

static const char *API_URL       = "https://openrouter.ai/api/v1/chat/completions";
static const int   MAX_TOKENS    = 320;     // keep answers screen-sized
static const int   API_HISTORY   = 6;       // messages of context sent
static const int   HTTP_TIMEOUT  = 30000;

/* ---------------------------------------------------------------------
   BOARD
   --------------------------------------------------------------------- */
#define SCR_W 320
#define SCR_H 240
#define SCREEN_ROTATION 1
#define TFT_INVERT 0            // set 1 if colours look negative

// XPT2046 lives on its own SPI bus on the CYD
#define XPT2046_IRQ  36
#define XPT2046_MOSI 32
#define XPT2046_MISO 39
#define XPT2046_CLK  25
#define XPT2046_CS   33
#define TOUCH_MIN_X 200
#define TOUCH_MAX_X 3900
#define TOUCH_MIN_Y 200
#define TOUCH_MAX_Y 3900

#define LED_R 4
#define LED_G 16
#define LED_B 17
#define SPEAKER_PIN 26          // onboard amp (speaker is optional hardware)

/* ---------------------------------------------------------------------
   PALETTE
   --------------------------------------------------------------------- */
#define C_BG       0x0861
#define C_HEADER   0x18E3
#define C_ACCENT   0x051F
#define C_ACCENT2  0x05E8
#define C_USER_BUB 0x021F
#define C_AI_BUB   0x31A6
#define C_ERR_BUB  0x9000
#define C_TEXT     0xFFFF
#define C_DIM      0x8410
#define C_KEY      0x2945
#define C_KEY_HI   0x051F
#define C_KEY_SP   0x4208
#define C_FIELD    0x0000
#define C_SEL      0x03E0
#define C_GREEN    0x07E0
#define C_RED      0xF800

/* ---------------------------------------------------------------------
   MODELS  (all free on OpenRouter; auto-fallback on 429 / errors)
   --------------------------------------------------------------------- */
struct ModelOpt { const char *name; const char *slug; };
ModelOpt MODELS[] = {
  { "Gemma 4 31B",  "google/gemma-4-31b-it:free"     },
  { "GPT-OSS 120B", "openai/gpt-oss-120b:free"       },
  { "GPT-OSS 20B",  "openai/gpt-oss-20b:free"        },
  { "Kimi K2.6",    "moonshotai/kimi-k2.6:free"      },
  { "Qwen3 Coder",  "qwen/qwen3-coder:free"          },
};
const int MODEL_COUNT = sizeof(MODELS) / sizeof(MODELS[0]);

/* ---------------------------------------------------------------------
   PERSONAS  (math-focused system prompts)
   --------------------------------------------------------------------- */
struct Persona { const char *name; const char *prompt; };
Persona PERSONAS[] = {
  { "Tutor", "You are a rigorous math tutor. Solve step by step: state the method, show each step, then give the final answer. Be precise about domains and edge cases." },
  { "Short", "Answer with the final result first, then one line of reasoning. No filler." },
  { "Exam",  "You are an exam coach. Show the fastest valid method, then the answer, then one common mistake to avoid." },
  { "Proof", "You are a proof explainer. Explain why the result is true from definitions, and state the exact conditions required." },
};
const int PERSONA_COUNT = sizeof(PERSONAS) / sizeof(PERSONAS[0]);

static const char *LANG_RULE =
  " 請用繁體中文（台灣用語）回答。數學式一律用純 ASCII 符號：不要 LaTeX、不要 Unicode 數學符號。"
  "整段回覆控制在 300 字以內，先給結論，再給關鍵步驟。";

/* ---------------------------------------------------------------------
   THE 5 TEST LEVELS  (quick bar)
   --------------------------------------------------------------------- */
const char *QUICK_LBL[5] = { "ALG", "CALC", "PHYS", "OPT", "PROOF" };
const char *QUICK_Q[5] = {
  "化簡 (3x^2 - 12x + 9) / (x - 3)，並說明 x 的限制。",
  "求 f(x) = x^2 * sin(x) 的導函數，並求 x = pi 時的斜率。",
  "5 公斤物體從 20 公尺高落下，求落地速度。g = 9.8。",
  "表面積 100 平方公分的密閉盒子，求體積最大時的尺寸。",
  "為什麼勾股定理一定要有直角？請用餘弦定理解釋。"
};

/* ---------------------------------------------------------------------
   DEMO ANSWERS  (used when no API key is set)
   --------------------------------------------------------------------- */
const char *DEMO_ANS[5] = {
  "(3x^2-12x+9)/(x-3) = 3(x-1)(x-3)/(x-3) = 3x-3，限制 x 不等於 3。",
  "f'(x) = 2x sin(x) + x^2 cos(x)。x = pi 時斜率 = -pi^2 = -9.87。",
  "v = sqrt(2gh) = sqrt(2*9.8*20) = 19.8 m/s，方向向下。",
  "正方體最佳：6a^2 = 100，a = 4.08 公分，V = 68.0 立方公分。",
  "cosC = (a^2+b^2-c^2)/(2ab)。C = 90 度時 cosC = 0，所以 c^2 = a^2+b^2；其他角度多出的項不能省略。"
};

/* ---------------------------------------------------------------------
   OBJECTS / STATE
   --------------------------------------------------------------------- */
TFT_eSPI tft = TFT_eSPI();
SPIClass touchSPI(VSPI);
XPT2046_Touchscreen ts(XPT2046_CS, XPT2046_IRQ);
Preferences prefs;

enum AppState { ST_WIFI_LIST, ST_KEYBOARD, ST_CONNECTING, ST_CHAT, ST_SETTINGS, ST_MODEL };
AppState state = ST_WIFI_LIST;
bool needRedraw = true;

enum KbTarget { KT_WIFI_PASS, KT_CHAT };
KbTarget kbTarget = KT_CHAT;
enum KbLayer { L_LOWER, L_UPPER, L_SYM };
KbLayer kbLayer = L_LOWER;

String inputText, wifiSSID, wifiPass;
int selModel = 0, selPersona = 0, brightness = 210;
int lastQuick = -1;

enum Role { R_USER, R_AI, R_ERR };
struct Msg { Role role; String text; };
std::vector<Msg> messages;
const size_t MAX_MESSAGES = 24;

struct Net { String ssid; int rssi; bool secure; };
std::vector<Net> nets;
int wifiPage = 0;
const int NETS_PER_PAGE = 5;

int modelPage = 0;
const int MODELS_PER_PAGE = 5;

int chatScroll = 0, chatContentH = 0;
bool sendPending = false;

struct Touch { bool down; int x; int y; };
struct KeyBox { int x, y, w, h; String label, value; int special; };
std::vector<KeyBox> keys;

/* keyboard geometry */
const int KB_TOP = 42;
const int ROW_H  = 49;
const int KGAP   = 2;
const char *rowsLower[3] = { "qwertyuiop", "asdfghjkl", "zxcvbnm" };
const char *rowsUpper[3] = { "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM" };
const char *rowsSym[3]   = { "1234567890", "+-*/=<>^_", "()[]{}.,?" };

/* chat geometry */
const int CHAT_HEADER_H = 28;
const int CHAT_INPUT_H  = 36;
const int QUICK_H       = 26;
const int QUICK_Y       = SCR_H - CHAT_INPUT_H - QUICK_H;
const int CHAT_AREA_Y   = CHAT_HEADER_H;
const int CHAT_AREA_H   = SCR_H - CHAT_HEADER_H - CHAT_INPUT_H - QUICK_H;

/* ---------------------------------------------------------------------
   LED + BRIGHTNESS
   --------------------------------------------------------------------- */
void led(bool r, bool g, bool b) {
  digitalWrite(LED_R, r ? LOW : HIGH);
  digitalWrite(LED_G, g ? LOW : HIGH);
  digitalWrite(LED_B, b ? LOW : HIGH);
}
void applyBrightness() { analogWrite(TFT_BL, brightness); }

/* ---------------------------------------------------------------------
   SOUND  (harmless if no speaker is soldered)
   --------------------------------------------------------------------- */
void beep(uint16_t freq, uint16_t ms) {
  tone(SPEAKER_PIN, freq, ms);
  delay(ms);
  noTone(SPEAKER_PIN);
}
void soundSend()  { beep(880, 55);  beep(1175, 55); }
void soundReply() { beep(1047, 55); beep(1319, 70); }
void soundError() { beep(220, 180); }
void soundBoot()  { beep(659, 70);  beep(880, 70); beep(1319, 110); }

/* ---------------------------------------------------------------------
   CLOCK (UTC+8)
   --------------------------------------------------------------------- */
const char *DOW[7]  = { "Sun","Mon","Tue","Wed","Thu","Fri","Sat" };
const char *MON[12] = { "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec" };
unsigned long lastClock = 0;

void syncTime() { configTime(8 * 3600, 0, "pool.ntp.org", "time.google.com"); }

String clockStr() {
  struct tm ti;
  if (!getLocalTime(&ti, 50)) return "--:--";
  char b[6]; snprintf(b, sizeof(b), "%02d:%02d", ti.tm_hour, ti.tm_min);
  return String(b);
}
String dateStr() {
  struct tm ti;
  if (!getLocalTime(&ti, 50)) return "";
  return String(DOW[ti.tm_wday]) + " " + String(ti.tm_mday) + " " + String(MON[ti.tm_mon]);
}

/* ---------------------------------------------------------------------
   UTF-8 -> ASCII  (the built-in font is ASCII only)
   --------------------------------------------------------------------- */
const char *cpToLatin(int cp) {
  switch (cp) {
    case 0x00E9: return "e"; case 0x00E8: return "e"; case 0x00EA: return "e";
    case 0x00E0: return "a"; case 0x00E1: return "a";
    case 0x00F6: return "o"; case 0x00FC: return "u"; case 0x00DF: return "ss";
    case 0x00B0: return "deg"; case 0x00B2: return "^2"; case 0x00B3: return "^3";
    case 0x00D7: return "x";   case 0x00F7: return "/";
    case 0x2013: return "-";   case 0x2014: return "-";
    case 0x2018: case 0x2019: return "'";
    case 0x201C: case 0x201D: return "\"";
    case 0x2026: return "...";
    case 0x03C0: return "pi";
    case 0x03B1: return "alpha"; case 0x03B2: return "beta"; case 0x03B8: return "theta";
    case 0x221A: return "sqrt";  case 0x221E: return "inf";
    case 0x2260: return "!=";    case 0x2264: return "<="; case 0x2265: return ">=";
    case 0x2192: return "->";    case 0x2211: return "sum";
  }
  return "?";
}

String foldASCII(const String &in) {
  String out; out.reserve(in.length() + 8);
  int i = 0, n = in.length();
  while (i < n) {
    uint8_t c = (uint8_t)in[i];
    if (c < 0x80) { out += (char)c; i++; continue; }
    if (c >= 0xC2 && c <= 0xDF && i + 1 < n) {
      int cp = ((c & 0x1F) << 6) | ((uint8_t)in[i + 1] & 0x3F);
      out += cpToLatin(cp); i += 2;
    } else if (c >= 0xE0 && c <= 0xEF && i + 2 < n) {
      int cp = ((c & 0x0F) << 12) | (((uint8_t)in[i + 1] & 0x3F) << 6) | ((uint8_t)in[i + 2] & 0x3F);
      out += cpToLatin(cp); i += 3;
    } else { out += "?"; i++; }
  }
  return out;
}

void delLastChar() {
  int n = inputText.length();
  if (n == 0) return;
  int i = n - 1;
  while (i > 0 && ((uint8_t)inputText[i] & 0xC0) == 0x80) i--;
  inputText.remove(i);
}

bool apiKeyOk() {
  String k = CHAT_API_KEY; k.trim();
  return k.length() > 20;
}

/* ---------------------------------------------------------------------
   TOUCH
   --------------------------------------------------------------------- */
Touch readTouch() {
  Touch t = { false, 0, 0 };
  if (ts.touched()) {
    TS_Point p = ts.getPoint();
    int x = constrain(map(p.x, TOUCH_MIN_X, TOUCH_MAX_X, 0, SCR_W), 0, SCR_W - 1);
    int y = constrain(map(p.y, TOUCH_MIN_Y, TOUCH_MAX_Y, 0, SCR_H), 0, SCR_H - 1);
    t.down = true; t.x = x; t.y = y;
  }
  return t;
}

/* ---------------------------------------------------------------------
   DRAW HELPERS
   --------------------------------------------------------------------- */
void drawButton(int x, int y, int w, int h, const String &label,
                uint16_t bg, uint16_t fg, uint8_t font = 2) {
  tft.fillRoundRect(x, y, w, h, 6, bg);
  tft.setTextColor(fg, bg);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(label, x + w / 2, y + h / 2, font);
}

/* ---------------------------------------------------------------------
   UTF-8 / CJK TEXT  (16x16 bitmap glyphs from cjk_font.h)
   ASCII uses TFT_eSPI font 2; CJK uses the bitmap table.
   --------------------------------------------------------------------- */
int cjkIndex(uint16_t cp) {
  int lo = 0, hi = (int)CJK_COUNT - 1;
  while (lo <= hi) {
    int mid = (lo + hi) >> 1;
    uint16_t v = cjk_cp[mid];
    if (v == cp) return mid;
    if (v < cp) lo = mid + 1; else hi = mid - 1;
  }
  return -1;
}

int utf8Advance(const String &s, int i, uint16_t &cp) {
  int n = (int)s.length();
  uint8_t c = (uint8_t)s[i];
  if (c < 0x80) { cp = c; return i + 1; }
  if ((c & 0xE0) == 0xC0 && i + 1 < n) {
    cp = ((c & 0x1F) << 6) | ((uint8_t)s[i + 1] & 0x3F);
    return i + 2;
  }
  if ((c & 0xF0) == 0xE0 && i + 2 < n) {
    cp = ((c & 0x0F) << 12) | (((uint8_t)s[i + 1] & 0x3F) << 6) | ((uint8_t)s[i + 2] & 0x3F);
    return i + 3;
  }
  if ((c & 0xF8) == 0xF0 && i + 3 < n) { cp = '?'; return i + 4; }
  cp = '?'; return i + 1;
}

int charWidth(uint16_t cp) {
  if (cp < 0x80) return tft.textWidth(String((char)cp), 2);
  return CJK_GLYPH_W;
}

void drawUTF8Char(uint16_t cp, int x, int y, uint16_t fg, uint16_t bg) {
  if (cp < 0x20) return;
  if (cp < 0x80) {
    tft.setTextColor(fg, bg);
    tft.setTextDatum(TL_DATUM);
    tft.drawChar((uint16_t)cp, x, y, 2);
    return;
  }
  int idx = cjkIndex(cp);
  if (idx >= 0) {
    tft.drawBitmap(x, y, cjk_bits + (uint32_t)idx * CJK_GLYPH_BYTES,
                   CJK_GLYPH_W, CJK_GLYPH_H, fg, bg);
  } else {
    tft.drawRect(x + 3, y + 3, CJK_GLYPH_W - 6, CJK_GLYPH_H - 6, fg);
  }
}

void drawUTF8(const String &s, int x, int y, uint16_t fg, uint16_t bg) {
  int i = 0;
  while (i < (int)s.length()) {
    uint16_t cp;
    i = utf8Advance(s, i, cp);
    drawUTF8Char(cp, x, y, fg, bg);
    x += charWidth(cp);
  }
}

int measureUTF8(const String &s) {
  int total = 0, i = 0;
  while (i < (int)s.length()) {
    uint16_t cp;
    i = utf8Advance(s, i, cp);
    total += charWidth(cp);
  }
  return total;
}

std::vector<String> wrapText(const String &raw, int maxW) {
  std::vector<String> lines;
  String cur;
  int w = 0, i = 0;
  while (i < (int)raw.length()) {
    uint16_t cp;
    int next = utf8Advance(raw, i, cp);
    if (cp == '\n') {
      lines.push_back(cur); cur = ""; w = 0; i = next; continue;
    }
    int cw = charWidth(cp);
    if (w + cw > maxW && cur.length() > 0) {
      lines.push_back(cur); cur = ""; w = 0;
    }
    cur += raw.substring(i, next);
    w += cw;
    i = next;
  }
  if (cur.length()) lines.push_back(cur);
  if (lines.empty()) lines.push_back("");
  return lines;
}

void addMessage(Role r, const String &txt) {
  messages.push_back({ r, txt });
  if (messages.size() > MAX_MESSAGES) messages.erase(messages.begin());
}

int rssiBars(int rssi) {
  if (rssi >= -55) return 4;
  if (rssi >= -65) return 3;
  if (rssi >= -75) return 2;
  if (rssi >= -85) return 1;
  return 0;
}
void drawWifiIcon(int x, int y, int bars) {
  for (int i = 0; i < 4; i++) {
    int bh = 3 + i * 3;
    tft.fillRect(x + i * 5, y + 12 - bh, 3, bh, (i < bars) ? C_ACCENT2 : C_DIM);
  }
}
void iconPlus(int cx, int cy, uint16_t col) {
  tft.fillRoundRect(cx - 7, cy - 2, 14, 4, 2, col);
  tft.fillRoundRect(cx - 2, cy - 7, 4, 14, 2, col);
}
void iconMenu(int cx, int cy, uint16_t col) {
  for (int i = -1; i <= 1; i++) tft.fillRoundRect(cx - 8, cy + i * 5 - 1, 16, 3, 1, col);
}

/* ---------------------------------------------------------------------
   CHAT MEMORY (NVS)
   --------------------------------------------------------------------- */
void saveChat() {
  JsonDocument d;
  JsonArray arr = d.to<JsonArray>();
  int start = max(0, (int)messages.size() - 10);
  for (int i = start; i < (int)messages.size(); i++) {
    if (messages[i].role == R_ERR) continue;
    JsonObject o = arr.add<JsonObject>();
    o["r"] = (messages[i].role == R_USER) ? 0 : 1;
    o["t"] = messages[i].text;
  }
  String s; serializeJson(d, s);
  if (s.length() <= 3900) prefs.putString("chatlog", s);
}

void loadChat() {
  String s = prefs.getString("chatlog", "");
  if (s.length() < 2) return;
  JsonDocument d;
  if (deserializeJson(d, s)) return;
  for (JsonObject o : d.as<JsonArray>()) {
    Role r = (o["r"].as<int>() == 0) ? R_USER : R_AI;
    messages.push_back({ r, o["t"].as<String>() });
  }
}

/* ---------------------------------------------------------------------
   SPLASH
   --------------------------------------------------------------------- */
void drawSplash(const String &sub) {
  tft.fillScreen(C_BG);
  tft.fillRoundRect(SCR_W / 2 - 46, 54, 92, 60, 12, C_ACCENT);
  tft.fillTriangle(SCR_W / 2 - 24, 114, SCR_W / 2 - 4, 114, SCR_W / 2 - 24, 130, C_ACCENT);
  tft.setTextColor(C_TEXT, C_ACCENT);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("AI", SCR_W / 2, 84, 4);
  tft.setTextColor(C_TEXT, C_BG);
  tft.drawString("Math Tutor", SCR_W / 2, 150, 4);
  tft.setTextColor(C_DIM, C_BG);
  tft.drawString(String(APP_VERSION) + "  -  " + sub, SCR_W / 2, 178, 2);
}

/* ---------------------------------------------------------------------
   WIFI SCAN + LIST
   --------------------------------------------------------------------- */
void scanWifi() {
  drawSplash("scanning WiFi...");
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  int n = WiFi.scanNetworks();
  nets.clear();
  for (int i = 0; i < n; i++) {
    if (WiFi.SSID(i).length() == 0) continue;
    Net net; net.ssid = WiFi.SSID(i); net.rssi = WiFi.RSSI(i);
    net.secure = (WiFi.encryptionType(i) != WIFI_AUTH_OPEN);
    nets.push_back(net);
  }
  std::sort(nets.begin(), nets.end(), [](const Net &a, const Net &b) { return a.rssi > b.rssi; });
  wifiPage = 0;
}

void drawWifiList() {
  tft.fillScreen(C_BG);
  tft.fillRect(0, 0, SCR_W, 28, C_HEADER);
  tft.setTextColor(C_TEXT, C_HEADER);
  tft.setTextDatum(ML_DATUM);
  tft.drawString("WiFi", 10, 14, 4);
  drawButton(SCR_W - 164, 3, 76, 22, "Demo", C_KEY_SP, C_TEXT, 2);
  drawButton(SCR_W - 80, 3, 76, 22, "Rescan", C_ACCENT, C_TEXT, 2);

  if (nets.empty()) {
    tft.setTextColor(C_DIM, C_BG);
    tft.setTextDatum(MC_DATUM);
    tft.drawString("No networks found", SCR_W / 2, 120, 4);
    return;
  }
  int totalPages = (nets.size() + NETS_PER_PAGE - 1) / NETS_PER_PAGE;
  int start = wifiPage * NETS_PER_PAGE, rowH = 34, y = 32;
  for (int i = start; i < (int)nets.size() && i < start + NETS_PER_PAGE; i++) {
    tft.fillRoundRect(6, y, SCR_W - 12, rowH - 4, 6, C_KEY);
    tft.setTextColor(C_TEXT, C_KEY);
    tft.setTextDatum(ML_DATUM);
    String name = foldASCII(nets[i].ssid);
    if (name.length() > 22) name = name.substring(0, 21) + "~";
    tft.drawString(name, 14, y + (rowH - 4) / 2, 2);
    drawWifiIcon(SCR_W - 62, y + 4, rssiBars(nets[i].rssi));
    if (nets[i].secure) {
      tft.setTextColor(C_DIM, C_KEY);
      tft.drawString("lock", SCR_W - 40, y + (rowH - 4) / 2, 1);
    }
    y += rowH;
  }
  tft.setTextColor(C_DIM, C_BG);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("Page " + String(wifiPage + 1) + "/" + String(totalPages), SCR_W / 2, 224, 2);
  if (wifiPage > 0)              drawButton(6, 214, 64, 22, "< Prev", C_KEY_SP, C_TEXT, 1);
  if (wifiPage < totalPages - 1) drawButton(SCR_W - 76, 214, 72, 22, "Next >", C_KEY_SP, C_TEXT, 1);
}

void handleWifiListTouch(int x, int y) {
  if (y < 28) {
    if (x > SCR_W - 80) { scanWifi(); needRedraw = true; return; }
    if (x > SCR_W - 164 && x <= SCR_W - 84) {
      if (messages.empty()) addMessage(R_AI, "離線示範。點下面的關卡，或在序列埠輸入問題。");
      state = ST_CHAT; needRedraw = true; return;
    }
  }
  int totalPages = nets.empty() ? 1 : (nets.size() + NETS_PER_PAGE - 1) / NETS_PER_PAGE;
  if (y >= 214) {
    if (x < 72 && wifiPage > 0) { wifiPage--; needRedraw = true; return; }
    if (x > SCR_W - 82 && wifiPage < totalPages - 1) { wifiPage++; needRedraw = true; return; }
  }
  int rowH = 34, start = wifiPage * NETS_PER_PAGE;
  for (int i = start; i < (int)nets.size() && i < start + NETS_PER_PAGE; i++) {
    int ry = 32 + (i - start) * rowH;
    if (y >= ry && y < ry + rowH - 4 && x >= 6 && x <= SCR_W - 6) {
      wifiSSID = nets[i].ssid; inputText = "";
      if (!nets[i].secure) { wifiPass = ""; state = ST_CONNECTING; }
      else { kbTarget = KT_WIFI_PASS; kbLayer = L_LOWER; state = ST_KEYBOARD; }
      needRedraw = true; return;
    }
  }
}

/* ---------------------------------------------------------------------
   CONNECTING
   --------------------------------------------------------------------- */
bool connectWifi() {
  led(0, 0, 1);
  drawSplash("connecting: " + foldASCII(wifiSSID));
  WiFi.mode(WIFI_STA);
  WiFi.begin(wifiSSID.c_str(), wifiPass.c_str());
  unsigned long t0 = millis();
  int dots = 0;
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < 20000) {
    delay(300);
    dots = (dots + 1) % 4;
    tft.fillRect(0, 204, SCR_W, 24, C_BG);
    String d = ""; for (int i = 0; i < dots; i++) d += " .";
    tft.setTextColor(C_ACCENT, C_BG);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(d, SCR_W / 2, 212, 4);
  }
  led(0, 0, 0);
  if (WiFi.status() == WL_CONNECTED) {
    prefs.putString("ssid", wifiSSID);
    prefs.putString("pass", wifiPass);
    Serial.printf("[WiFi] connected, IP %s\n", WiFi.localIP().toString().c_str());
    return true;
  }
  return false;
}

/* ---------------------------------------------------------------------
   CHAT SCREEN
   --------------------------------------------------------------------- */
const int AV = 24;
int bubbleMaxW() { return SCR_W - (AV + 8) - 16; }

int computeChatHeight() {
  int total = 8;
  for (auto &m : messages) {
    std::vector<String> lines = wrapText(m.text, bubbleMaxW() - 14);
    total += (int)lines.size() * 18 + 14 + 8;
  }
  return total;
}

void drawChatHeader() {
  tft.fillRect(0, 0, SCR_W, CHAT_HEADER_H, C_HEADER);
  tft.setTextColor(C_TEXT, C_HEADER);
  tft.setTextDatum(ML_DATUM);
  String mn = foldASCII(MODELS[selModel].name);
  if (mn.length() > 9) mn = mn.substring(0, 8) + "~";
  tft.drawString(mn, 8, CHAT_HEADER_H / 2, 2);

  String ck = clockStr();
  tft.setTextColor(C_TEXT, C_HEADER);
  tft.drawString(ck, 104, CHAT_HEADER_H / 2, 2);
  int cw = tft.textWidth(ck);
  tft.setTextColor(C_DIM, C_HEADER);
  tft.drawString(dateStr(), 104 + cw + 8, CHAT_HEADER_H / 2 + 1, 1);

  if (WiFi.status() == WL_CONNECTED) drawWifiIcon(SCR_W - 92, 7, rssiBars(WiFi.RSSI()));
  tft.fillRoundRect(SCR_W - 64, 3, 28, 22, 6, C_ACCENT2); iconPlus(SCR_W - 50, 14, C_BG);
  tft.fillRoundRect(SCR_W - 32, 3, 28, 22, 6, C_KEY_SP);  iconMenu(SCR_W - 18, 14, C_TEXT);
}

void drawAvatar(int x, int y, bool user) {
  uint16_t c = user ? C_ACCENT : C_AI_BUB;
  tft.fillCircle(x + AV / 2, y + AV / 2, AV / 2, c);
  tft.setTextColor(C_TEXT, c);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(user ? "U" : "AI", x + AV / 2, y + AV / 2, 2);
}

void drawChatArea() {
  chatContentH = computeChatHeight();
  int maxScroll = max(0, chatContentH - CHAT_AREA_H);
  chatScroll = constrain(chatScroll, 0, maxScroll);

  tft.setViewport(0, CHAT_AREA_Y, SCR_W, CHAT_AREA_H);
  tft.fillScreen(C_BG);

  int y = 8 - chatScroll;
  for (auto &m : messages) {
    std::vector<String> lines = wrapText(m.text, bubbleMaxW() - 14);
    int bw = 0;
    for (auto &ln : lines) bw = max(bw, measureUTF8(ln));
    bw += 14; if (bw > bubbleMaxW()) bw = bubbleMaxW();
    int bh = (int)lines.size() * 18 + 14;

    if (y + bh > -4 && y < CHAT_AREA_H + 4) {
      bool user = (m.role == R_USER);
      uint16_t bub = user ? C_USER_BUB : (m.role == R_AI) ? C_AI_BUB : C_ERR_BUB;
      int bx, ax;
      if (user) { bx = SCR_W - (AV + 6) - bw; ax = SCR_W - AV - 4; }
      else      { bx = AV + 8;                ax = 4; }
      drawAvatar(ax, y, user);
      tft.fillRoundRect(bx, y, bw, bh, 8, bub);
      tft.setTextColor(C_TEXT, bub);
      tft.setTextDatum(TL_DATUM);
      int ty = y + 7;
      for (auto &ln : lines) { drawUTF8(ln, bx + 7, ty, C_TEXT, bub); ty += 18; }
    }
    y += bh + 8;
  }
  tft.resetViewport();

  if (maxScroll > 0) {
    int barH = max(14, CHAT_AREA_H * CHAT_AREA_H / chatContentH);
    int barY = CHAT_AREA_Y + (CHAT_AREA_H - barH) * chatScroll / maxScroll;
    tft.fillRoundRect(SCR_W - 4, barY, 3, barH, 1, C_ACCENT);
  }
}

void drawQuickBar() {
  tft.fillRect(0, QUICK_Y, SCR_W, QUICK_H, C_BG);
  int gap = 4, bw = (SCR_W - gap * 6) / 5;
  for (int i = 0; i < 5; i++) {
    int bx = gap + i * (bw + gap);
    uint16_t bg = (i == lastQuick) ? C_KEY_SP : C_KEY;
    drawButton(bx, QUICK_Y + 2, bw, QUICK_H - 4, QUICK_LBL[i], bg, C_ACCENT2, 2);
  }
}

void drawChatInput() {
  int y = SCR_H - CHAT_INPUT_H;
  tft.fillRect(0, y, SCR_W, CHAT_INPUT_H, C_HEADER);
  tft.fillRoundRect(8, y + 5, SCR_W - 90, CHAT_INPUT_H - 10, 8, C_FIELD);
  tft.setTextColor(C_DIM, C_FIELD);
  tft.setTextDatum(ML_DATUM);
  tft.drawString(apiKeyOk() ? "Type a question..." : "DEMO - tap a test", 16, y + CHAT_INPUT_H / 2, 2);
  drawButton(SCR_W - 76, y + 5, 68, CHAT_INPUT_H - 10, "Write", C_ACCENT, C_TEXT, 2);
}

void drawChat() {
  tft.fillScreen(C_BG);
  drawChatHeader();
  drawChatArea();
  drawQuickBar();
  drawChatInput();
}

/* ---------------------------------------------------------------------
   MODEL PICKER
   --------------------------------------------------------------------- */
void drawModelList() {
  tft.fillScreen(C_BG);
  tft.fillRect(0, 0, SCR_W, 28, C_HEADER);
  tft.setTextColor(C_TEXT, C_HEADER);
  tft.setTextDatum(ML_DATUM);
  tft.drawString("Choose model", 10, 14, 4);
  drawButton(SCR_W - 72, 3, 68, 22, "< Back", C_ACCENT, C_TEXT, 2);

  int totalPages = (MODEL_COUNT + MODELS_PER_PAGE - 1) / MODELS_PER_PAGE;
  int start = modelPage * MODELS_PER_PAGE, rowH = 34, y = 32;
  for (int i = start; i < MODEL_COUNT && i < start + MODELS_PER_PAGE; i++) {
    uint16_t bg = (i == selModel) ? C_SEL : C_KEY;
    tft.fillRoundRect(6, y, SCR_W - 12, rowH - 4, 6, bg);
    tft.setTextColor(C_TEXT, bg);
    tft.setTextDatum(ML_DATUM);
    tft.drawString(foldASCII(MODELS[i].name), 14, y + (rowH - 4) / 2, 2);
    tft.setTextColor(C_ACCENT2, bg);
    tft.setTextDatum(MR_DATUM);
    tft.drawString("free", SCR_W - 16, y + (rowH - 4) / 2, 1);
    y += rowH;
  }
  tft.setTextColor(C_DIM, C_BG);
  tft.setTextDatum(MC_DATUM);
  tft.drawString("Page " + String(modelPage + 1) + "/" + String(totalPages), SCR_W / 2, 224, 2);
  if (modelPage > 0)              drawButton(6, 214, 64, 22, "< Prev", C_KEY_SP, C_TEXT, 1);
  if (modelPage < totalPages - 1) drawButton(SCR_W - 76, 214, 72, 22, "Next >", C_KEY_SP, C_TEXT, 1);
}

void handleModelTouch(int x, int y) {
  if (y < 28 && x > SCR_W - 72) { state = ST_CHAT; needRedraw = true; return; }
  int totalPages = (MODEL_COUNT + MODELS_PER_PAGE - 1) / MODELS_PER_PAGE;
  if (y >= 214) {
    if (x < 72 && modelPage > 0) { modelPage--; needRedraw = true; return; }
    if (x > SCR_W - 82 && modelPage < totalPages - 1) { modelPage++; needRedraw = true; return; }
  }
  int rowH = 34, start = modelPage * MODELS_PER_PAGE;
  for (int i = start; i < MODEL_COUNT && i < start + MODELS_PER_PAGE; i++) {
    int ry = 32 + (i - start) * rowH;
    if (y >= ry && y < ry + rowH - 4 && x >= 6 && x <= SCR_W - 6) {
      selModel = i; prefs.putInt("model", selModel);
      state = ST_CHAT; needRedraw = true; return;
    }
  }
}

/* ---------------------------------------------------------------------
   SETTINGS
   --------------------------------------------------------------------- */
void drawSettings() {
  tft.fillScreen(C_BG);
  tft.fillRect(0, 0, SCR_W, 28, C_HEADER);
  tft.setTextColor(C_TEXT, C_HEADER);
  tft.setTextDatum(ML_DATUM);
  tft.drawString("Settings", 10, 14, 4);
  drawButton(SCR_W - 72, 3, 68, 22, "< Back", C_ACCENT, C_TEXT, 2);

  tft.setTextColor(C_DIM, C_BG);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("WiFi: " + foldASCII(wifiSSID.length() ? wifiSSID : String("none")) +
                 (apiKeyOk() ? "   API: OK" : "   API: DEMO"), 10, 34, 2);

  drawButton(10, 56,  146, 30, "WiFi", C_KEY, C_TEXT, 2);
  drawButton(164, 56, 146, 30, "Model", C_KEY, C_TEXT, 2);
  drawButton(10, 92,  300, 30, "Persona: " + String(PERSONAS[selPersona].name), C_KEY, C_ACCENT2, 2);

  tft.setTextColor(C_TEXT, C_BG);
  tft.setTextDatum(ML_DATUM);
  tft.drawString("Brightness", 14, 143, 2);
  drawButton(150, 128, 40, 30, "-", C_KEY_SP, C_TEXT, 4);
  tft.setTextColor(C_TEXT, C_BG);
  tft.setTextDatum(MC_DATUM);
  tft.drawString(String(map(brightness, 25, 255, 0, 100)) + "%", 215, 143, 2);
  drawButton(240, 128, 40, 30, "+", C_KEY_SP, C_TEXT, 4);

  drawButton(10, 166, 300, 30, "Clear chat", C_KEY, C_TEXT, 2);
  drawButton(10, 202, 300, 30, "Forget WiFi", C_ERR_BUB, C_TEXT, 2);
}

void handleSettingsTouch(int x, int y) {
  if (y < 28 && x > SCR_W - 72) { state = ST_CHAT; needRedraw = true; return; }
  if (y >= 56 && y <= 86) {
    if (x < 160) { scanWifi(); state = ST_WIFI_LIST; needRedraw = true; return; }
    else { modelPage = 0; state = ST_MODEL; needRedraw = true; return; }
  }
  if (y >= 92 && y <= 122) {
    selPersona = (selPersona + 1) % PERSONA_COUNT;
    prefs.putInt("persona", selPersona);
    needRedraw = true; return;
  }
  if (y >= 128 && y <= 158) {
    if (x >= 150 && x <= 190) brightness = max(25, brightness - 30);
    if (x >= 240 && x <= 280) brightness = min(255, brightness + 30);
    applyBrightness(); prefs.putInt("bright", brightness);
    needRedraw = true; return;
  }
  if (y >= 166 && y <= 196) {
    messages.clear(); chatScroll = 0; prefs.remove("chatlog");
    state = ST_CHAT; needRedraw = true; return;
  }
  if (y >= 202 && y <= 232) {
    prefs.remove("ssid"); prefs.remove("pass");
    wifiSSID = ""; WiFi.disconnect(true, true); delay(200);
    scanWifi(); state = ST_WIFI_LIST; needRedraw = true; return;
  }
}

/* ---------------------------------------------------------------------
   KEYBOARD
   --------------------------------------------------------------------- */
void pushKey(int x, int y, int w, int h, String label, String value, int special) {
  KeyBox k; k.x = x; k.y = y; k.w = w; k.h = h;
  k.label = label; k.value = value; k.special = special;
  keys.push_back(k);
}

void buildKeyboard() {
  keys.clear();
  int h = ROW_H - KGAP;
  const char **rows = (kbLayer == L_LOWER) ? rowsLower : (kbLayer == L_UPPER) ? rowsUpper : rowsSym;

  { int n = strlen(rows[0]); int kw = SCR_W / n;
    for (int i = 0; i < n; i++) { String c = String(rows[0][i]); pushKey(i * kw + KGAP, KB_TOP, kw - 2 * KGAP, h, c, c, 0); } }
  { int n = strlen(rows[1]); int kw = 32; int x0 = (SCR_W - n * kw) / 2; int y = KB_TOP + ROW_H;
    for (int i = 0; i < n; i++) { String c = String(rows[1][i]); pushKey(x0 + i * kw + KGAP, y, kw - 2 * KGAP, h, c, c, 0); } }
  { int n = strlen(rows[2]); int y = KB_TOP + 2 * ROW_H; int side = 46, kw = 32;
    int x0 = (SCR_W - (2 * side + n * kw)) / 2;
    if (kbLayer == L_SYM) pushKey(x0 + KGAP, y, side - 2 * KGAP, h, "sym", "", 0);
    else pushKey(x0 + KGAP, y, side - 2 * KGAP, h, (kbLayer == L_UPPER) ? "SHFT" : "shft", "", 1);
    int xx = x0 + side;
    for (int i = 0; i < n; i++) { String c = String(rows[2][i]); pushKey(xx + i * kw + KGAP, y, kw - 2 * KGAP, h, c, c, 0); }
    pushKey(xx + n * kw + KGAP, y, side - 2 * KGAP, h, "<-", "", 2);
  }
  { int y = KB_TOP + 3 * ROW_H, layW = 50, entW = 64;
    pushKey(KGAP, y, layW - 2 * KGAP, h, (kbLayer == L_SYM) ? "ABC" : "123", "", 5);
    int spX = layW, spW = SCR_W - spX - entW;
    pushKey(spX + KGAP, y, spW - 2 * KGAP, h, "space", " ", 3);
    pushKey(SCR_W - entW + KGAP, y, entW - 2 * KGAP, h, (kbTarget == KT_CHAT) ? "Send" : "OK", "", 4);
  }
}

void drawInputField() {
  tft.fillRect(0, 0, SCR_W, KB_TOP - 2, C_HEADER);
  drawButton(2, 4, 44, KB_TOP - 10, "X", C_ERR_BUB, C_TEXT, 4);
  int fx = 50, fw = SCR_W - 54;
  tft.fillRoundRect(fx, 4, fw, KB_TOP - 10, 6, C_FIELD);
  tft.setTextDatum(ML_DATUM);
  String shown = foldASCII(inputText);
  tft.setTextFont(2);
  while (tft.textWidth(shown) > fw - 16 && shown.length() > 0) shown = shown.substring(1);
  tft.setTextColor(C_TEXT, C_FIELD);
  tft.drawString(shown, fx + 6, (KB_TOP - 2) / 2, 2);
  int cx = fx + 6 + tft.textWidth(shown);
  if (cx < SCR_W - 6) tft.fillRect(cx + 1, 8, 2, KB_TOP - 18, C_ACCENT);
}

void drawKeyboard() {
  tft.fillScreen(C_BG);
  drawInputField();
  buildKeyboard();
  for (auto &k : keys) {
    uint16_t bg = (k.special == 1 && kbLayer == L_UPPER) ? C_KEY_HI
                : (k.special != 0) ? C_KEY_SP : C_KEY;
    if (k.special == 4) bg = C_ACCENT;
    tft.fillRoundRect(k.x, k.y, k.w, k.h, 5, bg);
    tft.setTextColor(C_TEXT, bg);
    tft.setTextDatum(MC_DATUM);
    uint8_t f = (k.label.length() <= 1) ? 4 : 2;
    tft.drawString(k.label, k.x + k.w / 2, k.y + k.h / 2, f);
  }
}

void flashKey(const KeyBox &k) {
  tft.fillRoundRect(k.x, k.y, k.w, k.h, 5, C_KEY_HI);
  tft.setTextColor(C_TEXT, C_KEY_HI);
  tft.setTextDatum(MC_DATUM);
  uint8_t f = (k.label.length() <= 1) ? 4 : 2;
  tft.drawString(k.label, k.x + k.w / 2, k.y + k.h / 2, f);
}

void keyboardConfirm() {
  if (kbTarget == KT_WIFI_PASS) {
    wifiPass = inputText;
    state = ST_CONNECTING;
  } else {
    String msg = inputText; msg.trim();
    if (msg.length() > 0) {
      addMessage(R_USER, msg);
      Serial.printf("[YOU] %s\n", msg.c_str());
      soundSend();
      sendPending = true;
    }
    state = ST_CHAT;
  }
  inputText = ""; needRedraw = true;
}

int findKey(int x, int y) {
  for (int i = 0; i < (int)keys.size(); i++)
    if (x >= keys[i].x && x <= keys[i].x + keys[i].w && y >= keys[i].y && y <= keys[i].y + keys[i].h)
      return i;
  return -1;
}

/* ---------------------------------------------------------------------
   AI CALL  (OpenRouter + fallback + demo mode)
   --------------------------------------------------------------------- */
void demoAnswer() {
  led(0, 0, 1);
  delay(600);
  String ans;
  if (lastQuick >= 0 && lastQuick < 5) ans = DEMO_ANS[lastQuick];
  else ans = "示範模式：尚未設定 API 金鑰。請在 platformio.ini 的 CHAT_API_KEY 填入 OpenRouter 金鑰後重新燒錄。";
  addMessage(R_AI, ans);
  Serial.printf("[AI] %s\n", ans.c_str());
  soundReply();
  led(0, 1, 0);
}

void callAI() {
  if (!apiKeyOk()) { demoAnswer(); return; }
  if (WiFi.status() != WL_CONNECTED) { addMessage(R_ERR, "沒有 Wi-Fi 連線。"); return; }

  led(0, 0, 1);

  int order[MODEL_COUNT]; int n = 0;
  order[n++] = selModel;
  for (int i = 0; i < MODEL_COUNT; i++) if (i != selModel) order[n++] = i;

  WiFiClientSecure client;
  client.setInsecure();
  int lastCode = 0; String lastDetail = "";

  for (int a = 0; a < n; a++) {
    int mi = order[a];
    int yb = SCR_H - CHAT_INPUT_H;
    tft.fillRect(0, yb, SCR_W, CHAT_INPUT_H, C_HEADER);
    tft.setTextColor(C_ACCENT, C_HEADER);
    tft.setTextDatum(MC_DATUM);
    tft.drawString(foldASCII(MODELS[mi].name) + " thinking...", SCR_W / 2, yb + CHAT_INPUT_H / 2, 2);

    JsonDocument req;
    req["model"] = MODELS[mi].slug;
    req["max_tokens"] = MAX_TOKENS;
    JsonArray msgs = req["messages"].to<JsonArray>();
    { JsonObject s = msgs.add<JsonObject>();
      s["role"] = "system";
      s["content"] = String(PERSONAS[selPersona].prompt) + LANG_RULE; }

    std::vector<const Msg *> hist;
    for (auto it = messages.rbegin(); it != messages.rend() && (int)hist.size() < API_HISTORY; ++it) {
      if (it->role == R_ERR) continue;
      hist.push_back(&(*it));
    }
    for (auto it = hist.rbegin(); it != hist.rend(); ++it) {
      JsonObject m = msgs.add<JsonObject>();
      m["role"] = ((*it)->role == R_USER) ? "user" : "assistant";
      m["content"] = (*it)->text;
    }
    String payload; serializeJson(req, payload);

    HTTPClient https; https.setTimeout(HTTP_TIMEOUT);
    if (!https.begin(client, API_URL)) { lastDetail = "connect failed"; continue; }
    https.addHeader("Content-Type", "application/json");
    https.addHeader("Authorization", String("Bearer ") + CHAT_API_KEY);
    https.addHeader("HTTP-Referer", "https://cyd.local");
    https.addHeader("X-Title", "CYD Math Tutor");

    int code = https.POST(payload);
    if (code <= 0) { lastCode = code; lastDetail = https.errorToString(code); https.end(); continue; }
    String body = https.getString();
    https.end();

    if (code == 200) {
      JsonDocument doc;
      if (deserializeJson(doc, body)) { lastCode = 200; lastDetail = "parse error"; continue; }
      const char *content = doc["choices"][0]["message"]["content"];
      if (content != nullptr && strlen(content) > 0) {
        addMessage(R_AI, String(content));
        Serial.printf("[AI] %s\n", content);
        soundReply();
        led(0, 1, 0);
        return;
      }
      lastCode = 200; lastDetail = "empty reply"; continue;
    }
    lastCode = code;
    JsonDocument ed;
    if (deserializeJson(ed, body) == DeserializationError::Ok && !ed["error"]["message"].isNull())
      lastDetail = ed["error"]["message"].as<String>();
    else lastDetail = body.substring(0, 100);
    if (code == 401) break;
  }

  led(1, 0, 0);
  soundError();
  if (lastCode == 401)      addMessage(R_ERR, "API 金鑰無效（401），請檢查 CHAT_API_KEY。");
  else if (lastCode == 429) addMessage(R_ERR, "免費模型目前都在限流（429），請等一兩分鐘再試。");
  else                      addMessage(R_ERR, "沒有回覆（" + String(lastCode) + "）：" + lastDetail);
  Serial.printf("[ERR] code=%d %s\n", lastCode, lastDetail.c_str());
}

/* ---------------------------------------------------------------------
   TOUCH STATE
   --------------------------------------------------------------------- */
bool wasDown = false;
int  pressKey = -1;
unsigned long pressTime = 0, lastRepeat = 0, lastScrollDraw = 0;
bool chatDragging = false, dragMoved = false;
int  dragStartY = 0, dragStartScroll = 0;

void handleChatTouch_press(int x, int y) {
  if (y < CHAT_HEADER_H) {
    if (x >= SCR_W - 64 && x < SCR_W - 34) {
      messages.clear(); chatScroll = 0; prefs.remove("chatlog");
      needRedraw = true; return;
    }
    if (x >= SCR_W - 34) { state = ST_SETTINGS; needRedraw = true; return; }
    if (x < SCR_W - 96)  { modelPage = 0; state = ST_MODEL; needRedraw = true; return; }
    return;
  }
  if (y >= QUICK_Y && y < QUICK_Y + QUICK_H) {
    int gap = 4, bw = (SCR_W - gap * 6) / 5;
    for (int i = 0; i < 5; i++) {
      int bx = gap + i * (bw + gap);
      if (x >= bx && x <= bx + bw) {
        lastQuick = i;
        addMessage(R_USER, String(QUICK_LBL[i]) + ": " + QUICK_Q[i]);
        Serial.printf("[YOU] %s: %s\n", QUICK_LBL[i], QUICK_Q[i]);
        soundSend();
        sendPending = true;
        needRedraw = true;
        return;
      }
    }
    return;
  }
  if (y >= SCR_H - CHAT_INPUT_H) {
    inputText = ""; kbTarget = KT_CHAT; kbLayer = L_LOWER;
    state = ST_KEYBOARD; needRedraw = true; return;
  }
  chatDragging = true; dragStartY = y; dragStartScroll = chatScroll; dragMoved = false;
}

void handleChatTouch_move(int x, int y) {
  if (!chatDragging) return;
  int dy = dragStartY - y;
  if (abs(dy) > 5) dragMoved = true;
  chatScroll = constrain(dragStartScroll + dy, 0, max(0, chatContentH - CHAT_AREA_H));
  if (millis() - lastScrollDraw > 40) { drawChatArea(); lastScrollDraw = millis(); }
}

void handleKeyboardPress(int tx, int ty) {
  if (ty < KB_TOP - 2 && tx < 48) {
    if (kbTarget == KT_WIFI_PASS) { scanWifi(); state = ST_WIFI_LIST; }
    else state = ST_CHAT;
    inputText = ""; needRedraw = true; return;
  }
  int ki = findKey(tx, ty);
  if (ki < 0) return;
  KeyBox k = keys[ki];
  pressKey = ki; pressTime = millis(); lastRepeat = millis();
  flashKey(k);
  switch (k.special) {
    case 0: case 3:
      if (k.value.length() && inputText.length() < 512) inputText += k.value;
      drawInputField(); break;
    case 1: kbLayer = (kbLayer == L_LOWER) ? L_UPPER : L_LOWER; drawKeyboard(); break;
    case 2: delLastChar(); drawInputField(); break;
    case 4: keyboardConfirm(); break;
    case 5: kbLayer = (kbLayer == L_SYM) ? L_LOWER : L_SYM; drawKeyboard(); break;
  }
}

/* ---------------------------------------------------------------------
   SETUP
   --------------------------------------------------------------------- */
void setup() {
  Serial.begin(115200);
  Serial.setTimeout(60);
  delay(100);

  pinMode(LED_R, OUTPUT); pinMode(LED_G, OUTPUT); pinMode(LED_B, OUTPUT);
  pinMode(SPEAKER_PIN, OUTPUT);
  led(0, 0, 0);

  tft.init();
  tft.setRotation(SCREEN_ROTATION);
#if TFT_INVERT
  tft.invertDisplay(true);
#endif

  prefs.begin("cydmath", false);
  wifiSSID   = prefs.getString("ssid", "");
  selModel   = prefs.getInt("model", 0);
  selPersona = prefs.getInt("persona", 0);
  brightness = prefs.getInt("bright", 210);
  if (selModel < 0 || selModel >= MODEL_COUNT) selModel = 0;
  if (selPersona < 0 || selPersona >= PERSONA_COUNT) selPersona = 0;
  brightness = constrain(brightness, 25, 255);

  applyBrightness();
  drawSplash("starting...");
  soundBoot();
  Serial.printf("[BOOT] screen %d x %d (rot %d)\n", tft.width(), tft.height(), SCREEN_ROTATION);
  delay(600);

  touchSPI.begin(XPT2046_CLK, XPT2046_MISO, XPT2046_MOSI, XPT2046_CS);
  ts.begin(touchSPI);
  ts.setRotation(SCREEN_ROTATION);

  loadChat();

  if (wifiSSID.length() > 0) {
    wifiPass = prefs.getString("pass", "");
    led(0, 0, 1);
    drawSplash("joining saved WiFi...");
    WiFi.mode(WIFI_STA);
    WiFi.begin(wifiSSID.c_str(), wifiPass.c_str());
    unsigned long t0 = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - t0 < 12000) delay(200);
    led(0, 0, 0);
    if (WiFi.status() == WL_CONNECTED)
      Serial.printf("[WiFi] connected, IP %s\n", WiFi.localIP().toString().c_str());
  }

  if (WiFi.status() == WL_CONNECTED) {
    syncTime();
    if (messages.empty()) {
      addMessage(R_AI, apiKeyOk()
        ? "你好，我是數學導師。點下面的關卡，或按「Write」輸入問題。"
        : "示範模式：尚未設定 API 金鑰。先玩下面五個關卡，或輸入問題看看。");
    }
    state = ST_CHAT;
  } else {
    scanWifi();
    state = ST_WIFI_LIST;
  }
  needRedraw = true;
}

/* ---------------------------------------------------------------------
   LOOP
   --------------------------------------------------------------------- */
void loop() {
  if (needRedraw) {
    switch (state) {
      case ST_WIFI_LIST: drawWifiList();  break;
      case ST_KEYBOARD:  drawKeyboard();  break;
      case ST_CHAT:      drawChat();      break;
      case ST_SETTINGS:  drawSettings();  break;
      case ST_MODEL:     drawModelList(); break;
      default: break;
    }
    needRedraw = false;
  }

  // serial console: "demo" jumps to chat, any other line is a question
  if (Serial.available()) {
    String line = Serial.readStringUntil('\n');
    line.trim();
    if (line.length() > 0) {
      if (line.equalsIgnoreCase("demo")) {
        state = ST_CHAT; needRedraw = true;
      } else if (line.equalsIgnoreCase("cjk")) {
        addMessage(R_AI, "中文測試：餘弦定理 c^2 = a^2 + b^2 - 2ab cosC。當 C = 90 度時，cosC = 0，所以 c^2 = a^2 + b^2。");
        state = ST_CHAT; needRedraw = true;
      } else if (state == ST_CHAT && !sendPending) {
        lastQuick = -1;
        addMessage(R_USER, line);
        Serial.printf("[YOU] %s\n", line.c_str());
        soundSend();
        sendPending = true;
        needRedraw = true;
      }
    }
  }

  if (state == ST_CONNECTING) {
    if (connectWifi()) {
      syncTime();
      if (messages.empty()) {
        addMessage(R_AI, apiKeyOk()
          ? "你好，我是數學導師。點下面的關卡，或按「Write」輸入問題。"
          : "示範模式：尚未設定 API 金鑰。先玩下面五個關卡，或輸入問題看看。");
      }
      state = ST_CHAT;
    } else {
      led(1, 0, 0);
      drawSplash("connect failed - wrong password?");
      delay(1800); led(0, 0, 0);
      scanWifi(); state = ST_WIFI_LIST;
    }
    needRedraw = true;
    return;
  }

  if (state == ST_CHAT && sendPending) {
    sendPending = false;
    drawChat();
    callAI();
    saveChat();
    chatScroll = 1000000;
    needRedraw = true;
    return;
  }

  if (state == ST_CHAT && !wasDown && millis() - lastClock > 15000) {
    lastClock = millis();
    drawChatHeader();
  }

  // (serial console handled above)

  Touch t = readTouch();
  if (t.down && !wasDown) {
    wasDown = true;
    switch (state) {
      case ST_WIFI_LIST: handleWifiListTouch(t.x, t.y); break;
      case ST_SETTINGS:  handleSettingsTouch(t.x, t.y); break;
      case ST_MODEL:     handleModelTouch(t.x, t.y);    break;
      case ST_CHAT:      handleChatTouch_press(t.x, t.y); break;
      case ST_KEYBOARD:  handleKeyboardPress(t.x, t.y);   break;
      default: break;
    }
  } else if (t.down && wasDown) {
    if (state == ST_CHAT) handleChatTouch_move(t.x, t.y);
    else if (state == ST_KEYBOARD && pressKey >= 0 && pressKey < (int)keys.size() && keys[pressKey].special == 2) {
      unsigned long now = millis();
      if (now - pressTime > 450 && now - lastRepeat > 120) { delLastChar(); drawInputField(); lastRepeat = now; }
    }
  } else if (!t.down && wasDown) {
    wasDown = false;
    if (state == ST_CHAT) chatDragging = false;
    pressKey = -1;
  }
  delay(12);
}
