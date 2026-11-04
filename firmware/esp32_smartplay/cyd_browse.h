#pragma once
// ===========================================================================
//  Venue browser data layer + UI for the SmartPLAY CYD firmware.
//
//  Consumes the upstream `browse.json` feed:
//    {"g": "...",
//     "k": ["🏸","🏀",...],                 // sport icons
//     "d": ["11-04 三","11-05 四",...],    // pre-formatted date labels
//     "v": ["場地名|區名", ...],            // venue + district
//     "r": [[vIdx, sportIdx, dateIdx, startMin, endMin, courts], ...]}
//
//  No PSRAM on the ESP32, so everything is fixed-size C storage.
//  No String/std::vector/DOM left alive after parsing.
// ===========================================================================
#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <time.h>

#include "cyd_theme.h"

// ---------------- geometry ----------------
#define BROWSE_ROWS_PER_PAGE 4
#define BROWSE_ROW_H 64
#define BROWSE_HEADER_H 26
#define BROWSE_FOOTER_H 14

// ---------------- capacity ----------------
#define BROWSE_MAX_VENUES 256
#define BROWSE_MAX_ROWS 512
#define BROWSE_MAX_DISTRICTS 32
#define BROWSE_MAX_DATES 8
#define BROWSE_MAX_SPORTS 8

#ifndef FEED_BROWSE
#define FEED_BROWSE "https://hkteddychan.github.io/smartplay-live/esp32/browse.json"
#endif

// ---------------- data ----------------
struct BRow { uint8_t v, k, d; uint16_t sm, em, courts; };

static char browseG[24] = "";
static char sportIcons[BROWSE_MAX_SPORTS][8];
static int nSports = 0;
static char dateLabels[BROWSE_MAX_DATES][12];
static int nDates = 0;
static char venueNames[BROWSE_MAX_VENUES][44];
static char venueDists[BROWSE_MAX_VENUES][16];
static int nVenues = 0;
static char districts[BROWSE_MAX_DISTRICTS][16];
static int nDistricts = 0;
static BRow browses[BROWSE_MAX_ROWS];
static int nRows = 0;

static bool browseLoaded = false;
static char browseError[32] = "";

// ---------------- ui state (NVS-backed) ----------------
static Preferences browsePrefs;
static int curDistrict = 0;
static int curDate = 0;       // 0 = 全部日子, 1..nDates = 指定日子
static int pageSec = 5;       // 自動翻頁秒數
static bool autoPage = true;
static bool paused = false;
static int curPage = 0;       // 目前頁（每頁 4 行）

static unsigned long lastPageAt = 0;
static int browseOverlay = 0;  // 0=none 1=detail (reserved)

// ---------------- helpers ----------------
static void browseCopy(char *dst, size_t cap, const char *src) {
  if (!cap) return;
  strncpy(dst, src ? src : "", cap - 1);
  dst[cap - 1] = 0;
}

static int districtIndexOf(const char *d) {
  if (!d || !*d) return -1;
  for (int i = 0; i < nDistricts; i++)
    if (strcmp(districts[i], d) == 0) return i;
  if (nDistricts < BROWSE_MAX_DISTRICTS) {
    browseCopy(districts[nDistricts], sizeof(districts[0]), d);
    return nDistricts++;
  }
  return -1;
}

// defined in smartplay.ino
bool httpGet(const char *url, String &out);

// ---------------- parse ----------------
static bool browseParse(const char *body) {
  nSports = 0; nDates = 0; nVenues = 0; nDistricts = 0; nRows = 0;
  browseLoaded = false;
  browseCopy(browseError, sizeof(browseError), "");

  JsonDocument doc;
  if (deserializeJson(doc, body ? body : "")) {
    browseCopy(browseError, sizeof(browseError), "JSON 解析失敗");
    doc.clear();
    return false;
  }

  browseCopy(browseG, sizeof(browseG), doc["g"] | "");

  // sport icons
  JsonArray ks = doc["k"].as<JsonArray>();
  for (JsonVariant v : ks) {
    if (nSports >= BROWSE_MAX_SPORTS) break;
    const char *s = v.as<const char *>();
    if (!s) continue;
    browseCopy(sportIcons[nSports], sizeof(sportIcons[0]), s);
    nSports++;
  }

  // date labels (pre-formatted)
  JsonArray ds = doc["d"].as<JsonArray>();
  for (JsonVariant v : ds) {
    if (nDates >= BROWSE_MAX_DATES) break;
    const char *s = v.as<const char *>();
    if (!s) continue;
    browseCopy(dateLabels[nDates], sizeof(dateLabels[0]), s);
    nDates++;
  }

  // venues: "name|district"
  JsonArray vs = doc["v"].as<JsonArray>();
  for (JsonVariant v : vs) {
    if (nVenues >= BROWSE_MAX_VENUES) break;
    const char *s = v.as<const char *>();
    if (!s) continue;
    char buf[64];
    browseCopy(buf, sizeof(buf), s);
    char *bar = strchr(buf, '|');
    if (bar) {
      *bar = 0;
      browseCopy(venueNames[nVenues], sizeof(venueNames[0]), buf);
      browseCopy(venueDists[nVenues], sizeof(venueDists[0]), bar + 1);
    } else {
      browseCopy(venueNames[nVenues], sizeof(venueNames[0]), buf);
      browseCopy(venueDists[nVenues], sizeof(venueDists[0]), "");
    }
    districtIndexOf(venueDists[nVenues]);
    nVenues++;
  }

  // rows
  JsonArray rs = doc["r"].as<JsonArray>();
  for (JsonVariant v : rs) {
    JsonArray r = v.as<JsonArray>();
    if (r.size() < 6) continue;
    if (nRows >= BROWSE_MAX_ROWS) break;
    BRow &b = browses[nRows];
    b.v = (uint8_t)(r[0].as<int>());
    b.k = (uint8_t)(r[1].as<int>());
    b.d = (uint8_t)(r[2].as<int>());
    b.sm = (uint16_t)(r[3].as<int>());
    b.em = (uint16_t)(r[4].as<int>());
    b.courts = (uint16_t)(r[5].as<int>());
    if (b.v >= nVenues) continue;
    if (b.d >= (uint8_t)nDates) continue;
    nRows++;
  }

  doc.clear();
  browseLoaded = true;
  return nRows > 0;
}

static bool browseFetch() {
  if (WiFi.status() != WL_CONNECTED) {
    browseCopy(browseError, sizeof(browseError), "WiFi 未連接");
    return false;
  }
  static String body;
  if (!httpGet(FEED_BROWSE, body)) {
    browseCopy(browseError, sizeof(browseError), "抓取失敗");
    browseLoaded = false;
    return false;
  }
  Serial.printf("[browse] %s -> %u bytes\n", FEED_BROWSE, (unsigned)body.length());
  bool ok = browseParse(body.c_str());
  if (!ok) browseCopy(browseError, sizeof(browseError), "解析失敗");
  return ok;
}

// ---------------- NVS ----------------
static void browseLoadPrefs() {
  browsePrefs.begin("spl", true);
  curDistrict = browsePrefs.getInt("dist", 0);
  curDate = browsePrefs.getInt("date", 0);
  pageSec = browsePrefs.getInt("sec", 5);
  autoPage = browsePrefs.getBool("auto", true);
  browsePrefs.end();
  if (curDistrict >= nDistricts && nDistricts > 0) curDistrict = 0;
  if (curDate > nDates) curDate = 0;
  if (pageSec < 2) pageSec = 2;
  if (pageSec > 30) pageSec = 30;
}

static void browseSavePrefs() {
  browsePrefs.begin("spl", false);
  browsePrefs.putInt("dist", curDistrict);
  browsePrefs.putInt("date", curDate);
  browsePrefs.putInt("sec", pageSec);
  browsePrefs.putBool("auto", autoPage);
  browsePrefs.end();
}

// ---------------- row filtering ----------------
// returns indices into browses[] for the given district+date filter
static int browseFilteredRows(int *out, int maxOut) {
  int n = 0;
  for (int i = 0; i < nRows && n < maxOut; i++) {
    BRow &r = browses[i];
    if (r.v >= nVenues) continue;
    if (strcmp(venueDists[r.v], districts[curDistrict]) != 0) continue;
    if (curDate > 0 && r.d != (uint8_t)(curDate - 1)) continue;
    out[n++] = i;
  }
  return n;
}

// ---------------- navigation ----------------
static void browseStepDistrict(int delta) {
  if (nDistricts <= 0) return;
  int d = curDistrict + delta;
  while (d < 0) d += nDistricts;
  curDistrict = d % nDistricts;
  curPage = 0;
  lastPageAt = millis();
  browseSavePrefs();
}

static void browseCycleDate() {
  curDate = (curDate + 1) % (nDates + 1);
  curPage = 0;
  lastPageAt = millis();
  browseSavePrefs();
}

static void browseCycleSec() {
  if (pageSec == 5) pageSec = 3;
  else if (pageSec == 3) pageSec = 8;
  else if (pageSec == 8) pageSec = 10;
  else pageSec = 5;
  lastPageAt = millis();
  browseSavePrefs();
}

static void browseToggleAuto() {
  autoPage = !autoPage;
  paused = !autoPage;
  lastPageAt = millis();
  browseSavePrefs();
}

static void browseTick() {
  if (!autoPage || paused || nRows == 0) return;
  if (millis() - lastPageAt < (unsigned long)pageSec * 1000UL) return;
  lastPageAt = millis();

  int idx[64];
  int n = browseFilteredRows(idx, 64);
  int totalPages = (n + BROWSE_ROWS_PER_PAGE - 1) / BROWSE_ROWS_PER_PAGE;
  if (totalPages < 1) totalPages = 1;

  if (curPage + 1 < totalPages) {
    curPage++;
  } else {
    // last page -> next district
    curPage = 0;
    browseStepDistrict(1);
  }
}

// ---------------- touch ----------------
// returns true if consumed
static bool browseTouch(int x, int y) {
  (void)x;
  static unsigned long lastTouch = 0;
  if (millis() - lastTouch < 400) return true;
  lastTouch = millis();
  lastPageAt = millis();

  if (y < 100) {
    browseStepDistrict(-1);
  } else if (y > 220) {
    browseStepDistrict(1);
  } else {
    browseCycleDate();
  }
  return true;
}

// ---------------- drawing helpers ----------------
static void browseDrawHeader() {
  tft.fillRect(0, 0, 320, BROWSE_HEADER_H, C_BAR);
  // district name
  if (curDistrict < nDistricts)
    drawUTF8(String(districts[curDistrict]), 6, 6, C_TEXT, C_BAR);
  // date
  const char *dl = (curDate == 0) ? "全部日子" : (curDate <= nDates ? dateLabels[curDate - 1] : "");
  tft.setTextColor(C_DIM, C_BAR);
  tft.setTextDatum(TL_DATUM);
  tft.drawString(dl, 130, 6, 2);
  // auto status
  char as[12];
  snprintf(as, sizeof(as), "%ds%s", pageSec, autoPage ? (paused ? " ⏸" : " ▶") : " ⏸");
  tft.setTextColor(C_DIM, C_BAR);
  tft.drawString(as, 200, 6, 2);
  // clock
  time_t now = time(nullptr);
  struct tm lt;
  localtime_r(&now, &lt);
  if (lt.tm_year + 1900 >= 2024) {
    char buf[8];
    snprintf(buf, sizeof(buf), "%02d:%02d", lt.tm_hour, lt.tm_min);
    tft.setTextColor(C_TEXT, C_BAR);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(buf, 314, 6, 2);
    tft.setTextDatum(TL_DATUM);
  }
  tft.drawFastHLine(0, BROWSE_HEADER_H - 1, 320, C_DIM);
}

static void browseDrawBody() {
  int idx[64];
  int n = browseFilteredRows(idx, 64);
  int totalPages = (n + BROWSE_ROWS_PER_PAGE - 1) / BROWSE_ROWS_PER_PAGE;
  if (totalPages < 1) totalPages = 1;
  if (curPage >= totalPages) curPage = 0;

  int y = BROWSE_HEADER_H;
  if (n == 0) {
    tft.fillRect(0, y, 320, 240 - y - BROWSE_FOOTER_H, C_BG);
    String none = "呢個時段冇場";
    drawUTF8(none, (320 - measureUTF8(none)) / 2, y + 60, C_DIM, C_BG);
    return;
  }

  for (int i = 0; i < BROWSE_ROWS_PER_PAGE; i++) {
    int ri = curPage * BROWSE_ROWS_PER_PAGE + i;
    if (ri >= n) {
      // clear remaining rows
      tft.fillRect(0, y + i * BROWSE_ROW_H, 320, BROWSE_ROW_H, C_BG);
      continue;
    }
    BRow &r = browses[idx[ri]];
    int ry = y + i * BROWSE_ROW_H;

    // row background (alternating)
    tft.fillRect(0, ry, 320, BROWSE_ROW_H, (i % 2 == 0) ? C_BG : C_CARD);

    // sport icon
    if (r.k < nSports) {
      tft.setTextColor(C_ACCENT, (i % 2 == 0) ? C_BG : C_CARD);
      tft.setTextDatum(TL_DATUM);
      tft.drawString(sportIcons[r.k], 6, ry + 4, 4);
    }

    // date label
    if (r.d < nDates) {
      tft.setTextColor(C_DIM, (i % 2 == 0) ? C_BG : C_CARD);
      tft.drawString(dateLabels[r.d], 40, ry + 6, 2);
    }

    // venue name (CJK)
    if (r.v < nVenues) {
      drawUTF8(fitUTF8(String(venueNames[r.v]), 200), 40, ry + 26,
               C_TEXT, (i % 2 == 0) ? C_BG : C_CARD);
      // district (smaller, dimmer)
      drawUTF8(String(venueDists[r.v]), 40, ry + 46,
               C_DIM, (i % 2 == 0) ? C_BG : C_CARD);
    }

    // time + courts (right side)
    char tm[16];
    snprintf(tm, sizeof(tm), "%02d:%02d", r.sm / 60, r.sm % 60);
    tft.setTextColor(C_TEXT, (i % 2 == 0) ? C_BG : C_CARD);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(tm, 314, ry + 6, 2);
    snprintf(tm, sizeof(tm), "%d 場", r.courts);
    tft.setTextColor(C_GOOD, (i % 2 == 0) ? C_BG : C_CARD);
    tft.drawString(tm, 314, ry + 26, 2);
    tft.setTextDatum(TL_DATUM);

    // divider
    tft.drawFastHLine(0, ry + BROWSE_ROW_H - 1, 320, C_BAR);
  }
}

static void browseDrawFooter() {
  int y = 240 - BROWSE_FOOTER_H;
  tft.fillRect(0, y, 320, BROWSE_FOOTER_H, C_BAR);
  tft.setTextColor(C_DIM, C_BAR);
  tft.setTextDatum(TL_DATUM);
  tft.setTextSize(1);
  char buf[48];
  snprintf(buf, sizeof(buf), "%d/%d 區 · 頁 %d/%d",
           curDistrict + 1, nDistricts, curPage + 1,
           (browseFilteredRows(nullptr, 0) + BROWSE_ROWS_PER_PAGE - 1) / BROWSE_ROWS_PER_PAGE + 1);
  // recalc total pages properly
  int idx[64];
  int n = browseFilteredRows(idx, 64);
  int tp = (n + BROWSE_ROWS_PER_PAGE - 1) / BROWSE_ROWS_PER_PAGE;
  if (tp < 1) tp = 1;
  snprintf(buf, sizeof(buf), "%d/%d 區 · 頁 %d/%d", curDistrict + 1, nDistricts, curPage + 1, tp);
  tft.drawString(buf, 6, y + 3, 1);
  if (browseG[0]) {
    tft.setTextDatum(TR_DATUM);
    tft.drawString(browseG, 314, y + 3, 1);
    tft.setTextDatum(TL_DATUM);
  }
}

static void browseDraw() {
  tft.fillScreen(C_BG);
  browseDrawHeader();
  browseDrawBody();
  browseDrawFooter();
}

static void browseDrawCurrent() {
  browseDraw();
}

// ---------------- public API ----------------
static bool browseLoaded2() { return browseLoaded; }
static const char *browseErrorStr() { return browseError; }
static int browseRowCount() { return nRows; }
static int browseDistrictCount() { return nDistricts; }
static int browseDateCount() { return nDates; }

static void browseReset() {
  browseLoadPrefs();
  lastPageAt = millis();
}

static void browseInit() {
  browseLoadPrefs();
  lastPageAt = millis();
}
