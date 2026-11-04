#pragma once
// ===========================================================================
//  Venue browser data layer + UI for the SmartPLAY CYD firmware.
// ===========================================================================
#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <time.h>

#include "cyd_theme.h"

#define BROWSE_ROWS_PER_PAGE 5
#define BROWSE_ROW_H 40
#define BROWSE_HEADER_H 26
#define BROWSE_FOOTER_H 14

#define BROWSE_MAX_VENUES 256
#define BROWSE_MAX_ROWS 2048
#define BROWSE_MAX_DISTRICTS 32
#define BROWSE_MAX_DATES 10
#define BROWSE_MAX_SPORTS 8

#ifndef FEED_BROWSE
#define FEED_BROWSE "https://hkteddychan.github.io/smartplay-live/esp32/browse.json"
#endif

static const char *BR_SPORT_KEYS[]  = {"badminton","basketball","volleyball","tennis","turf-soccer-pitch"};
static const char *BR_SPORT_NAMES[] = {"羽毛球","籃球","排球","網球","草地足球"};
static const char *BR_SPORT_ICONS[] = {"羽","籃","排","網","足"};
static const int BR_N_SPORTS = 5;
static const char *BR_SPORT_TEXT_ICONS[] = {"羽","籃","排","網","足"};

struct BRow { uint8_t v, k, d; uint16_t sm, em, courts; };

static char browseG[24] = "";
static char sportIcons[BROWSE_MAX_SPORTS][8];
static int nSports = 0;
static char dateLabels[BROWSE_MAX_DATES][16];
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
static bool browseSportMode = false;

static Preferences browsePrefs;
static int curDistrict = 0;
static int curDate = 0;
static int curSport = -1;
static int curTimePeriod = 0;
static int pageSec = 5;
static bool autoPage = true;
static bool paused = false;
static int curPage = 0;
static int browseOverlay = 0;

static unsigned long lastPageAt = 0;

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

// 將康文署 18 區歸類為 3 大區域
static int regionOf(const char *d) {
    if (!d || !*d) return 2;
    if (strcmp(d, "中西區") == 0 || strcmp(d, "灣仔區") == 0 ||
        strcmp(d, "東區") == 0 || strcmp(d, "南區") == 0) return 0;       // 香港
    if (strcmp(d, "油尖旺區") == 0 || strcmp(d, "深水埗區") == 0 ||
        strcmp(d, "九龍城區") == 0 || strcmp(d, "觀塘區") == 0) return 1; // 九龍
    return 2;                                                            // 新界
}

bool httpGet(const char *url, String &out);

// ---------------- parse browse.json ----------------
static bool browseParseBrowse(const char *body) {
    nSports = 0; nDates = 0; nVenues = 0; nDistricts = 0; nRows = 0;
    browseLoaded = false;
    browseSportMode = false;
    browseCopy(browseError, sizeof(browseError), "");

    JsonDocument doc;
    DeserializationError _e = deserializeJson(doc, body ? body : "");
    if (_e) {
        Serial.printf("[browse] json err: %s\n", _e.c_str());
        browseCopy(browseError, sizeof(browseError), "JSON 解析失敗");
        doc.clear();
        return false;
    }

    browseCopy(browseG, sizeof(browseG), doc["g"] | "");

    JsonArray ks = doc["k"].as<JsonArray>();
    for (JsonVariant v : ks) {
        if (nSports >= BROWSE_MAX_SPORTS) break;
        const char *s = v.as<const char *>();
        if (!s) continue;
        browseCopy(sportIcons[nSports], sizeof(sportIcons[0]), s);
        nSports++;
    }

    JsonArray ds = doc["d"].as<JsonArray>();
    for (JsonVariant v : ds) {
        if (nDates >= BROWSE_MAX_DATES) break;
        const char *s = v.as<const char *>();
        if (!s) continue;
        browseCopy(dateLabels[nDates], sizeof(dateLabels[0]), s);
        nDates++;
    }

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
        districtIndexOf(venueDists[nVenues]);
        nVenues++;
    }

    // 3 大區域（取代 18 區）
    browseCopy(districts[0], sizeof(districts[0]), "香港");
    browseCopy(districts[1], sizeof(districts[1]), "九龍");
    browseCopy(districts[2], sizeof(districts[2]), "新界");
    nDistricts = 3;

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
        if (b.k >= (uint8_t)nSports) continue;
        nRows++;
    }

    doc.clear();
    browseLoaded = true;
    return nRows > 0;
}

// ---------------- parse {sport}-7d.json (lightweight) ----------------
static const char *brFindValue(const char *body, const char *key) {
    char pat[24];
    snprintf(pat, sizeof(pat), "\"%s\"", key);
    const char *p = strstr(body, pat);
    if (!p) return NULL;
    p += strlen(pat);
    while (*p == ' ' || *p == '\\t' || *p == '\\n' || *p == '\\r' || *p == ':') p++;
    return p;
}

static int brParseStrArr(const char *p, char out[][16], int maxN) {
    if (!p || *p != '[') return 0;
    p++;
    int n = 0;
    while (*p && *p != ']' && n < maxN) {
        while (*p == ' ' || *p == ',' || *p == '\\n' || *p == '\\r' || *p == '\\t') p++;
        if (*p == ']') break;
        if (*p != '"') { p++; continue; }
        p++;
        int i = 0;
        while (*p && *p != '"') {
            if (i < 15) out[n][i++] = *p;
            p++;
        }
        out[n][i] = 0;
        if (*p == '"') p++;
        n++;
    }
    return n;
}

static int brParseStrArr44(const char *p, char out[][44], int maxN) {
    if (!p || *p != '[') return 0;
    p++;
    int n = 0;
    while (*p && *p != ']' && n < maxN) {
        while (*p == ' ' || *p == ',' || *p == '\\n' || *p == '\\r' || *p == '\\t') p++;
        if (*p == ']') break;
        if (*p != '"') { p++; continue; }
        p++;
        int i = 0;
        while (*p && *p != '"') {
            if (i < 43) out[n][i++] = *p;
            p++;
        }
        out[n][i] = 0;
        if (*p == '"') p++;
        n++;
    }
    return n;
}

static bool browseParseSport(const char *body, int sportIdx) {
    nSports = 0; nDates = 0; nVenues = 0; nDistricts = 0; nRows = 0;
    browseLoaded = false;
    browseSportMode = true;
    browseCopy(browseError, sizeof(browseError), "");

    if (!body || !*body) { browseCopy(browseError, sizeof(browseError), "空資料"); return false; }

    const char *pg = brFindValue(body, "g");
    if (pg && *pg == '"') {
        pg++;
        int i = 0;
        while (pg[i] && pg[i] != '"' && i < 23) { browseG[i] = pg[i]; i++; }
        browseG[i] = 0;
    }

    const char *ps = brFindValue(body, "s");
    nDistricts = brParseStrArr(ps, districts, BROWSE_MAX_DISTRICTS);

    const char *pd = brFindValue(body, "d");
    nDates = brParseStrArr(pd, dateLabels, BROWSE_MAX_DATES);

    const char *pv = brFindValue(body, "v");
    nVenues = brParseStrArr44(pv, venueNames, BROWSE_MAX_VENUES);
    for (int i = 0; i < nVenues; i++) venueDists[i][0] = 0;

    nSports = 1;
    if (sportIdx >= 0 && sportIdx < BR_N_SPORTS)
        browseCopy(sportIcons[0], sizeof(sportIcons[0]), BR_SPORT_ICONS[sportIdx]);
    else
        browseCopy(sportIcons[0], sizeof(sportIcons[0]), "全");

    const char *pr = brFindValue(body, "r");
    if (!pr || *pr != '[') {
        browseCopy(browseError, sizeof(browseError), "無 r 陣列");
        return false;
    }
    pr++;
    while (*pr) {
        while (*pr == ' ' || *pr == ',' || *pr == '\\n' || *pr == '\\r' || *pr == '\\t') pr++;
        if (*pr == ']') break;
        if (*pr != '[') { pr++; continue; }
        pr++;
        int vals[6] = {0,0,0,0,0,0};
        int vi = 0;
        while (*pr && *pr != ']' && vi < 6) {
            while (*pr == ' ' || *pr == ',') pr++;
            if (*pr == ']') break;
            int sign = 1;
            if (*pr == '-') { sign = -1; pr++; }
            int num = 0;
            int hasDigit = 0;
            while (*pr >= '0' && *pr <= '9') { num = num * 10 + (*pr - '0'); pr++; hasDigit = 1; }
            if (hasDigit) vals[vi++] = num * sign;
        }
        while (*pr && *pr != ']') pr++;
        if (*pr == ']') pr++;

        if (vi >= 6 && nRows < BROWSE_MAX_ROWS) {
            int vIdx = vals[0];
            int distIdx = vals[1];
            int dateIdx = vals[2];
            int sm = vals[3];
            int em = vals[4];
            int courts = vals[5];
            if (vIdx >= 0 && vIdx < nVenues && dateIdx >= 0 && dateIdx < nDates) {
                BRow &b = browses[nRows];
                b.v = (uint8_t)vIdx;
                b.k = 0;
                b.d = (uint8_t)dateIdx;
                b.sm = (uint16_t)sm;
                b.em = (uint16_t)em;
                b.courts = (uint16_t)courts;
                if (distIdx >= 0 && distIdx < nDistricts)
                    browseCopy(venueDists[vIdx], sizeof(venueDists[0]), districts[distIdx]);
                nRows++;
            }
        }
    }

    // 3 大區域（取代 per-sport 18 區）
    browseCopy(districts[0], sizeof(districts[0]), "香港");
    browseCopy(districts[1], sizeof(districts[1]), "九龍");
    browseCopy(districts[2], sizeof(districts[2]), "新界");
    nDistricts = 3;

    browseLoaded = true;
    return nRows > 0;
}

// ---------------- fetch ----------------
static bool browseFetch() {
    if (WiFi.status() != WL_CONNECTED) {
        browseCopy(browseError, sizeof(browseError), "WiFi 未連接");
        return false;
    }
    static String body;
    const char *url = FEED_BROWSE;
    char urlBuf[160];
    if (curSport >= 0 && curSport < BR_N_SPORTS) {
        snprintf(urlBuf, sizeof(urlBuf),
                 "https://hkteddychan.github.io/smartplay-live/esp32/%s-7d.json",
                 BR_SPORT_KEYS[curSport]);
        url = urlBuf;
    }
    if (!httpGet(url, body)) {
        browseCopy(browseError, sizeof(browseError), "抓取失敗");
        browseLoaded = false;
        return false;
    }
    Serial.printf("[browse] %s -> %u bytes\n", url, (unsigned)body.length());
    bool ok;
    if (curSport >= 0) {
        ok = browseParseSport(body.c_str(), curSport);
    } else {
        ok = browseParseBrowse(body.c_str());
    }
    if (!ok) browseCopy(browseError, sizeof(browseError), "解析失敗");
    if (curDistrict >= nDistricts && nDistricts > 0) curDistrict = 0;
    // free body memory
    body = "";
    return ok;
}

// ---------------- NVS ----------------
static void browseLoadPrefs() {
    browsePrefs.begin("spl", true);
    curDistrict = browsePrefs.getInt("dist", 0);
    curDate = browsePrefs.getInt("date", 0);
    curSport = browsePrefs.getInt("sport", -1);
    curTimePeriod = browsePrefs.getInt("tp", 0);
    pageSec = browsePrefs.getInt("sec", 5);
    autoPage = browsePrefs.getBool("auto", true);
    browsePrefs.end();
    paused = !autoPage;
    if (curDistrict >= 3) curDistrict = 0;
    if (curTimePeriod < 0 || curTimePeriod > 2) curTimePeriod = 0;
    if (pageSec < 2) pageSec = 2;
    if (pageSec > 30) pageSec = 30;
}

static void browseSavePrefs() {
    browsePrefs.begin("spl", false);
    browsePrefs.putInt("dist", curDistrict);
    browsePrefs.putInt("date", curDate);
    browsePrefs.putInt("sport", curSport);
    browsePrefs.putInt("tp", curTimePeriod);
    browsePrefs.putInt("sec", pageSec);
    browsePrefs.putBool("auto", autoPage);
    browsePrefs.end();
}

static int timePeriodOf(uint16_t sm) {
    if (sm < 720) return 0;
    if (sm < 1080) return 1;
    return 2;
}

static int browseFilteredRows(int *out, int maxOut) {
    int n = 0;
    for (int i = 0; i < nRows && n < maxOut; i++) {
        BRow &r = browses[i];
        if (r.v >= nVenues) continue;
        if (nDistricts > 0 && regionOf(venueDists[r.v]) != curDistrict) continue;
        if (timePeriodOf(r.sm) != curTimePeriod) continue;
        out[n++] = i;
    }
    return n;
}

static void browseStepDistrict(int delta) {
    if (nDistricts <= 0) return;
    int d = curDistrict + delta;
    while (d < 0) d += nDistricts;
    curDistrict = d % 3;
    curPage = 0;
    lastPageAt = millis();
    browseSavePrefs();
}

static void browseSetDistrict(int idx) {
    if (idx < 0 || idx >= 3) return;
    curDistrict = idx;
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

static void browseCycleTimePeriod() {
    curTimePeriod = (curTimePeriod + 1) % 3;
    curPage = 0;
    lastPageAt = millis();
    browseSavePrefs();
}

static void browseSetSport(int sport) {
    if (sport != -1 && (sport < 0 || sport >= BR_N_SPORTS)) return;
    if (sport == curSport) { browseOverlay = 0; return; }
    curSport = sport;
    curDistrict = 0;
    curDate = 0;
    curPage = 0;
    browseOverlay = 0;
    lastPageAt = millis();
    browseSavePrefs();
    browseFetch();
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

static void browseTogglePaused() {
    paused = !paused;
    if (!paused) autoPage = true;
    else autoPage = false;
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
        curPage = 0;
        browseStepDistrict(1);
    }
}

static bool browseTouch(int x, int y) {
    Serial.printf("[touch] x=%d y=%d overlay=%d\n", x, y, browseOverlay);
    static unsigned long lastTouch = 0;
    if (millis() - lastTouch < 300) return true;
    lastTouch = millis();
    lastPageAt = millis();

    if (browseOverlay == 1) {
        if (x < 40 || x > 280 || y < 60 || y > 180) { browseOverlay = 0; return true; }
        int idx = (y - 88) / 32;
        if (idx >= 0 && idx < 3) browseSetDistrict(idx);
        browseOverlay = 0;
        return true;
    }
    if (browseOverlay == 2) {
        if (x < 60 || x > 260 || y < 40 || y > 220) { browseOverlay = 0; return true; }
        // visual layout: "全部運動" at y=62, sports at y=84+i*22
        if (y >= 52 && y < 84) {
            browseSetSport(-1);
        } else {
            int i = (y - 84) / 22;
            if (i >= 0 && i < BR_N_SPORTS) browseSetSport(i);
            else browseOverlay = 0;
        }
        return true;
    }

    if (y < BROWSE_HEADER_H) {
        // back button handled in smartplay.ino (x<20 && y<20)
        if (x >= 24 && x < 96) { browseOverlay = 1; return true; }   // district chip
        if (x >= 98 && x < 146) { browseOverlay = 2; return true; }  // sport chip
        if (x >= 148 && x < 186) { browseCycleTimePeriod(); return true; } // time chip
        if (x >= 188 && x < 226) { browseTogglePaused(); return true; }   // play/pause chip
        return true;
    }

    int idx[64];
    int n = browseFilteredRows(idx, 64);
    int totalPages = (n + BROWSE_ROWS_PER_PAGE - 1) / BROWSE_ROWS_PER_PAGE;
    if (totalPages < 1) totalPages = 1;
    if (x < 106) {
        if (curPage > 0) curPage--;
        else if (nDistricts > 0) browseStepDistrict(-1);
    } else if (x > 213) {
        if (curPage + 1 < totalPages) curPage++;
        else { curPage = 0; browseStepDistrict(1); }
    } else {
        browseCycleDate();
    }
    return true;
}

static const char *timePeriodLabel(int tp) {
    if (tp == 0) return "早";
    if (tp == 1) return "午";
    return "晚";
}

static const char *sportIconOf(int sport) {
    if (sport < 0) return "全";
    if (sport < BR_N_SPORTS) return BR_SPORT_TEXT_ICONS[sport];
    return "?";
}

static void browseDrawHeader() {
    tft.fillRect(0, 0, 320, BROWSE_HEADER_H, C_BAR);
    tft.setTextColor(C_DIM, C_BAR);
    tft.setTextDatum(TL_DATUM);
    tft.drawString("<", 4, 6, 2);

    // helper: draw a chip at (x,y,w) with label like "區香港"
    // district chip
    tft.fillRect(24, 2, 72, 22, C_CARD);
    tft.drawRect(24, 2, 72, 22, C_DIM);
    const char *dv = (curDistrict >= 0 && curDistrict < nDistricts && districts[curDistrict][0])
                     ? districts[curDistrict] : "全部";
    drawUTF8(String("區 ") + String(dv), 28, 6, C_TEXT, C_CARD);

    // sport chip
    tft.fillRect(98, 2, 48, 22, C_CARD);
    tft.drawRect(98, 2, 48, 22, C_DIM);
    drawUTF8(String("運 ") + String(sportIconOf(curSport)), 100, 6, C_ACCENT, C_CARD);

    // time chip (colour by period)
    uint16_t tcol = (curTimePeriod == 0) ? C_ACCENT : (curTimePeriod == 1) ? C_WARN : C_GOOD;
    tft.fillRect(148, 2, 38, 22, C_CARD);
    tft.drawRect(148, 2, 38, 22, C_DIM);
    drawUTF8(String("時 ") + String(timePeriodLabel(curTimePeriod)), 150, 6, tcol, C_CARD);

    // play/pause chip
    tft.fillRect(188, 2, 38, 22, C_CARD);
    tft.drawRect(188, 2, 38, 22, C_DIM);
    drawUTF8(paused ? String("⏸") : String("▶"), 200, 6, paused ? C_WARN : C_GOOD, C_CARD);

    // static hint
    tft.setTextColor(C_DIM, C_BAR);
    tft.setTextDatum(TL_DATUM);
    drawUTF8(String("全部日子"), 232, 6, C_DIM, C_BAR);

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
        String none = "呢個條件暫時冇可訂場地";
        drawUTF8(none, (320 - measureUTF8(none)) / 2, y + 80, C_DIM, C_BG);
        return;
    }

    for (int i = 0; i < BROWSE_ROWS_PER_PAGE; i++) {
        int ri = curPage * BROWSE_ROWS_PER_PAGE + i;
        if (ri >= n) {
            tft.fillRect(0, y + i * BROWSE_ROW_H, 320, BROWSE_ROW_H, C_BG);
            continue;
        }
        BRow &r = browses[idx[ri]];
        int ry = y + i * BROWSE_ROW_H;

        tft.fillRect(0, ry, 320, BROWSE_ROW_H, (i % 2 == 0) ? C_BG : C_CARD);

        String line1 = "";
        if (r.d < nDates) line1 += String(dateLabels[r.d]) + " ";
        line1 += String(venueDists[r.v]) + " ";
        if (r.v < nVenues) line1 += String(venueNames[r.v]);
        // available marker (filled circle, no font dependency)
        tft.fillCircle(10, ry + 10, 4, C_GOOD);
        drawUTF8(fitUTF8(line1, 296), 20, ry + 2, C_TEXT, (i % 2 == 0) ? C_BG : C_CARD);

        char tm[24];
        snprintf(tm, sizeof(tm), "%02d:%02d-%02d:%02d  %d場",
                 r.sm / 60, r.sm % 60, r.em / 60, r.em % 60, r.courts);
        if (r.k < nSports && r.k < BR_N_SPORTS) {
            tft.setTextColor(C_ACCENT, (i % 2 == 0) ? C_BG : C_CARD);
            tft.setTextDatum(TL_DATUM);
            tft.drawString(BR_SPORT_TEXT_ICONS[r.k], 4, ry + 22, 2);
        }
        tft.setTextColor(C_GOOD, (i % 2 == 0) ? C_BG : C_CARD);
        tft.setTextDatum(TL_DATUM);
        tft.drawString(tm, 24, ry + 22, 2);

        tft.drawFastHLine(0, ry + BROWSE_ROW_H - 1, 320, C_BAR);
    }
}

static void browseDrawFooter() {
    int y = 240 - BROWSE_FOOTER_H;
    tft.fillRect(0, y, 320, BROWSE_FOOTER_H, C_BAR);
    tft.setTextColor(C_DIM, C_BAR);
    tft.setTextDatum(TL_DATUM);
    tft.setTextSize(1);
    int idx[64];
    int n = browseFilteredRows(idx, 64);
    int tp = (n + BROWSE_ROWS_PER_PAGE - 1) / BROWSE_ROWS_PER_PAGE;
    if (tp < 1) tp = 1;
    char buf[64];
    snprintf(buf, sizeof(buf), "%d/%d區 · 頁%d/%d · %d行",
             curDistrict + 1, nDistricts, curPage + 1, tp, n);
    tft.drawString(buf, 6, y + 3, 1);
    tft.setTextDatum(TR_DATUM);
    tft.drawString("可訂 地區/運動/時段/播放", 314, y + 3, 1);
    tft.setTextDatum(TL_DATUM);
}

static void browseDrawOverlay() {
    if (browseOverlay == 0) return;
    tft.fillRect(0, 0, 320, 240, C_BG);
    if (browseOverlay == 1) {
        tft.fillRect(40, 60, 240, 120, C_CARD);
        tft.drawRect(40, 60, 240, 120, C_DIM);
        drawUTF8(String("選擇地區"), 48, 64, C_TEXT, C_CARD);
        const char *regions[] = {"香港", "九龍", "新界"};
        for (int i = 0; i < 3; i++) {
            tft.fillRect(48, 88 + i * 32, 224, 28, (i == curDistrict) ? C_ACCENT : C_BAR);
            drawUTF8(String(regions[i]), 56, 92 + i * 32, C_TEXT, (i == curDistrict) ? C_ACCENT : C_BAR);
        }
    } else if (browseOverlay == 2) {
        tft.fillRect(60, 36, 200, 170, C_CARD);
        tft.drawRect(60, 36, 200, 170, C_DIM);
        drawUTF8(String("選擇運動"), 68, 40, C_TEXT, C_CARD);
        uint16_t fg0 = (curSport == -1) ? C_ACCENT : C_TEXT;
        drawUTF8(String("全部運動"), 68, 62, fg0, C_CARD);
        for (int i = 0; i < BR_N_SPORTS; i++) {
            uint16_t fg = (curSport == i) ? C_ACCENT : C_TEXT;
            String lbl = String(BR_SPORT_TEXT_ICONS[i]) + " " + String(BR_SPORT_NAMES[i]);
            drawUTF8(lbl, 68, 84 + i * 22, fg, C_CARD);
        }
    }
}

static void browseDraw() {
    tft.fillScreen(C_BG);
    browseDrawHeader();
    browseDrawBody();
    browseDrawFooter();
    if (browseOverlay) browseDrawOverlay();
}

static void browseDrawCurrent() {
    browseDraw();
}

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
