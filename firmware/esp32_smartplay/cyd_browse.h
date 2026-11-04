#pragma once
// ---------------------------------------------------------------------------
// Venue browser data layer.
//
// Parses esp32/evening-7d.json into a packed array the board can hold in
// RAM.  No PSRAM on the ESP32, so everything here is fixed-size C storage —
// no String, no std::vector, no DOM left alive after parsing.
//
// Feed shape (see patches/evening_feed.py):
//   {"g": "...", "d": [7 dates], "sports": [...], "v": [venues], "s": [districts],
//    "r": [[districtIdx, venueIdx, sportIdx, dateIdx, startMin, endMin, courts]]}
//
// Rows are merged per venue+time: the same hall hosts several sports, and
// the feed lists each of them separately.
// ---------------------------------------------------------------------------
#include <Arduino.h>
#include <ArduinoJson.h>

#define BROWSE_MAX_ROWS 256
#define BROWSE_MAX_VENUES 128
#define BROWSE_MAX_DISTRICTS 24
#define BROWSE_MAX_DATES 8
#define BROWSE_MAX_SPORTS 8

#ifndef FEED_BROWSE
#define FEED_BROWSE "https://hkteddychan.github.io/smartplay-live/esp32/evening-7d.json"
#endif

// Board-side names for the sports the feed reports.
static const char *BROWSE_SPORT_KEYS[] = {
    "badminton", "basketball", "volleyball", "tennis", "turf-soccer-pitch"};
static const char *BROWSE_SPORT_ZH[] = {"羽毛球", "籃球", "排球", "網球", "草地足球"};
static const int BROWSE_N_SPORTS = 5;

struct BrowseRow {
  uint8_t sIdx;       // district index
  uint8_t vIdx;       // venue index
  uint8_t dateIdx;    // 0 = today
  uint16_t start, end;  // minutes from midnight
  uint16_t courts;      // summed across sports
  uint16_t sportMask;   // bit per sport
};

struct BrowseData {
  BrowseRow rows[BROWSE_MAX_ROWS];
  uint16_t rowCount;
  char venue[BROWSE_MAX_VENUES][44];
  uint16_t venueCount;
  char district[BROWSE_MAX_DISTRICTS][16];
  uint16_t districtCount;
  char date[BROWSE_MAX_DATES][12];
  uint8_t dateCount;
  char sport[BROWSE_MAX_SPORTS][16];
  uint8_t sportCount;
  bool loaded;
  char error[32];     // why the last fetch failed ("" = ok)
};

static BrowseData g_browse = {};

// defined in smartplay.ino
bool httpGet(const char *url, String &out);

// Chinese name for a sport key; falls back to the key itself.
inline const char *browseSportZh(const char *key) {
  if (!key) return "";
  for (int i = 0; i < BROWSE_N_SPORTS; i++)
    if (strcmp(key, BROWSE_SPORT_KEYS[i]) == 0) return BROWSE_SPORT_ZH[i];
  return key;
}

// Chinese names for the sports present in a row's mask, joined with '+'.
inline String browseSportList(uint16_t mask) {
  String out;
  for (int i = 0; i < g_browse.sportCount && i < BROWSE_N_SPORTS; i++) {
    if (!(mask & (1 << i))) continue;
    if (out.length()) out += "+";
    out += browseSportZh(g_browse.sport[i]);
  }
  return out.length() ? out : String("場地");
}

inline void browseCopyChar(char *dst, size_t cap, const char *src) {
  if (!cap) return;
  strncpy(dst, src ? src : "", cap - 1);
  dst[cap - 1] = 0;
}

// Parse the feed body.  Returns true when at least one row landed.
inline bool browseParse(const char *body) {
  g_browse.rowCount = 0;
  g_browse.venueCount = 0;
  g_browse.districtCount = 0;
  g_browse.dateCount = 0;
  g_browse.sportCount = 0;
  g_browse.loaded = false;

  JsonDocument doc;
  if (deserializeJson(doc, body ? body : "")) {
    doc.clear();
    browseCopyChar(g_browse.error, sizeof(g_browse.error), "JSON 解析失敗");
    return false;
  }

  JsonArray dates = doc["d"].as<JsonArray>();
  for (JsonVariant v : dates) {
    if (g_browse.dateCount >= BROWSE_MAX_DATES) break;
    const char *d = v.as<const char *>();
    if (!d) continue;
    browseCopyChar(g_browse.date[g_browse.dateCount], sizeof(g_browse.date[0]), d);
    g_browse.dateCount++;
  }

  JsonArray sports = doc["sports"].as<JsonArray>();
  for (JsonVariant v : sports) {
    if (g_browse.sportCount >= BROWSE_MAX_SPORTS) break;
    const char *s = v.as<const char *>();
    if (!s) continue;
    browseCopyChar(g_browse.sport[g_browse.sportCount], sizeof(g_browse.sport[0]), s);
    g_browse.sportCount++;
  }

  JsonArray venues = doc["v"].as<JsonArray>();
  for (JsonVariant v : venues) {
    if (g_browse.venueCount >= BROWSE_MAX_VENUES) break;
    const char *s = v.as<const char *>();
    if (!s) continue;
    browseCopyChar(g_browse.venue[g_browse.venueCount], sizeof(g_browse.venue[0]), s);
    g_browse.venueCount++;
  }

  JsonArray districts = doc["s"].as<JsonArray>();
  for (JsonVariant v : districts) {
    if (g_browse.districtCount >= BROWSE_MAX_DISTRICTS) break;
    const char *s = v.as<const char *>();
    if (!s) continue;
    browseCopyChar(g_browse.district[g_browse.districtCount], sizeof(g_browse.district[0]), s);
    g_browse.districtCount++;
  }

  JsonArray rows = doc["r"].as<JsonArray>();
  for (JsonVariant v : rows) {
    JsonArray r = v.as<JsonArray>();
    if (r.size() < 7) continue;
    if (g_browse.rowCount >= BROWSE_MAX_ROWS) break;

    BrowseRow b = {};
    b.sIdx = (uint8_t)r[0].as<int>();
    b.vIdx = (uint8_t)r[1].as<int>();
    uint8_t sportIdx = (uint8_t)r[2].as<int>();
    b.dateIdx = (uint8_t)r[3].as<int>();
    b.start = (uint16_t)r[4].as<int>();
    b.end = (uint16_t)r[5].as<int>();
    b.courts = (uint16_t)r[6].as<int>();
    if (b.sIdx >= g_browse.districtCount || b.vIdx >= g_browse.venueCount) continue;
    if (b.dateIdx >= g_browse.dateCount) continue;
    if (b.courts == 0) continue;
    b.sportMask = (sportIdx < 16) ? (uint16_t)(1u << sportIdx) : 0;

    // merge same venue + same slot (several sports share a hall)
    bool merged = false;
    for (uint16_t i = 0; i < g_browse.rowCount; i++) {
      BrowseRow &e = g_browse.rows[i];
      if (e.sIdx == b.sIdx && e.vIdx == b.vIdx && e.dateIdx == b.dateIdx &&
          e.start == b.start && e.end == b.end) {
        e.courts += b.courts;
        e.sportMask |= b.sportMask;
        merged = true;
        break;
      }
    }
    if (!merged) g_browse.rows[g_browse.rowCount++] = b;
  }

  doc.clear();
  g_browse.loaded = true;
  browseCopyChar(g_browse.error, sizeof(g_browse.error), "");
  return g_browse.rowCount > 0;
}

// Fetch + parse the browse feed.  Returns true when it worked.
inline bool browseFetch() {
  if (WiFi.status() != WL_CONNECTED) {
    browseCopyChar(g_browse.error, sizeof(g_browse.error), "WiFi 未連接");
    return false;
  }
  static String body;
  if (!httpGet(FEED_BROWSE, body)) {
    browseCopyChar(g_browse.error, sizeof(g_browse.error), "抓取失敗");
    g_browse.loaded = false;
    return false;
  }
  Serial.printf("[browse] %s -> %u bytes\n", FEED_BROWSE, (unsigned)body.length());
  return browseParse(body.c_str());
}

// How many slots does this district have on this day?
inline uint16_t browseCountFor(uint8_t sIdx, uint8_t dateIdx) {
  uint16_t n = 0;
  for (uint16_t i = 0; i < g_browse.rowCount; i++) {
    const BrowseRow &r = g_browse.rows[i];
    if (r.sIdx == sIdx && r.dateIdx == dateIdx) n++;
  }
  return n;
}
