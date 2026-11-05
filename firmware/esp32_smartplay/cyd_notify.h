#pragma once
// ---------------------------------------------------------------------------
// SmartPLAY CYD — 📜 放場通知歷史頁
//
// UX（設計）：
//   通知頁（PAGE_NOTIFY）右上角有一個「記錄」chip
//     ↓ 撳一下
//   歷史頁（PAGE_HISTORY）：逐個通知批次倒序排列
//     每批 = 一張卡：時間 + 幾多個放場 + 頭幾個場地摘要
//     ↓ 撳某張卡
//   詳情頁：睇晒嗰批全部放場（場地 / 日子 / 時間 / 幾多場）
//     ← 左上 "<" 返回上一頁
//
// 互動：
//   - 上/下滑動 = 翻頁（scroll）
//   - 撳卡片 = 進入詳情
//   - "<" chip = 返回
//
// 數據源：esp32/notif.json
//   { g, n, b: [ { t:"MM-DD HH:MM", n:count, r:[ {s,d,v,l,sm,em,c} ] } ] }
// ---------------------------------------------------------------------------
#include <Arduino.h>
#include <TFT_eSPI.h>
#include <ArduinoJson.h>

#include "cyd_theme.h"
#include "cyd_text.h"

extern TFT_eSPI tft;
extern bool httpGet(const char *url, String &out);

// ---- layout ----
static const int NH_HEADER_H = 26;
static const int NH_CARD_H   = 34;
static const int NH_ROWS     = 5;          // 一頁顯示幾多張卡
static const int NH_CARD_Y0  = NH_HEADER_H + 4;
static const int NH_LIST_H   = NH_ROWS * NH_CARD_H;
static const int NH_FOOT_Y   = NH_CARD_Y0 + NH_LIST_H;

#define NH_MAX_BATCH 12
#define NH_MAX_REL   6

struct NRel {
  char sport[10];
  char date[11];
  char venue[46];
  char loc[10];
  int  sm, em, courts;
};

struct NBatch {
  char t[13];          // "MM-DD HH:MM"
  int  n;              // 放場數
  int  relCount;
  NRel rel[NH_MAX_REL];
};

static NBatch nhBatches[NH_MAX_BATCH];
static int  nhCount = 0;
static bool nhLoaded = false;
static bool nhFetching = false;
static int  nhScroll = 0;          // 歷史頁 scroll offset（批次索引）
static int  nhDetailBatch = -1;    // 詳情頁顯示邊一批
static int  nhDetailScroll = 0;
static unsigned long nhLastFetch = 0;

static const char *NH_FEED = "https://hkteddychan.github.io/smartplay-live/esp32/notif.json";

// 運動 icon（ASCII 版，避免 CJK font 依賴 emoji）
static const char *nhSportIcon(const char *key) {
  if (!key) return "*";
  if (!strcmp(key, "badminton")) return "BAD";
  if (!strcmp(key, "basketball")) return "BK";
  if (!strcmp(key, "volleyball")) return "VB";
  if (!strcmp(key, "tennis")) return "TN";
  if (!strcmp(key, "turf-soccer-pitch")) return "FB";
  return "**";
}

// 中文運動名
static const char *nhSportName(const char *key) {
  if (!key) return "";
  if (!strcmp(key, "badminton")) return "羽毛球";
  if (!strcmp(key, "basketball")) return "籃球";
  if (!strcmp(key, "volleyball")) return "排球";
  if (!strcmp(key, "tennis")) return "網球";
  if (!strcmp(key, "turf-soccer-pitch")) return "足球場";
  return "";
}


// UTF-8 安全複製：唔會切爛中文字（如果會切，就截到上一個完整字元邊界）
static void nhCopyUtf8(char *dst, size_t cap, const char *src) {
  if (!src || !dst || cap == 0) { if (dst && cap) dst[0] = 0; return; }
  size_t len = strlen(src);
  if (len < cap) { memcpy(dst, src, len + 1); return; }
  // 需要截斷 → 搵最後一個完整 UTF-8 邊界
  size_t cut = cap - 1;
  while (cut > 0 && ((unsigned char)src[cut] & 0xC0) == 0x80) cut--;
  // src[cut] 應該係起始 byte；若係續 byte 再退
  while (cut > 0 && ((unsigned char)src[cut] & 0xC0) == 0x80) cut--;
  memcpy(dst, src, cut);
  dst[cut] = 0;
}

// ---- fetch + parse ----
static bool nhFetch() {
  if (WiFi.status() != WL_CONNECTED) return false;
  nhFetching = true;
  static String body;
  if (!httpGet(NH_FEED, body)) {
    Serial.println("[notif] fetch FAILED");
    nhFetching = false;
    return false;
  }
  Serial.printf("[notif] %u bytes\n", (unsigned)body.length());
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, body);
  if (err) {
    Serial.printf("[notif] parse error: %s\n", err.c_str());
    doc.clear();
    nhFetching = false;
    return false;
  }
  JsonArray batches = doc["b"].as<JsonArray>();
  int i = 0;
  for (JsonVariant bv : batches) {
    if (i >= NH_MAX_BATCH) break;
    JsonObject bo = bv.as<JsonObject>();
    NBatch &b = nhBatches[i];
    memset(&b, 0, sizeof(b));
    const char *t = bo["t"] | "";
    nhCopyUtf8(b.t, sizeof(b.t), t);
    b.n = bo["n"] | 0;
    JsonArray rels = bo["r"].as<JsonArray>();
    int rc = 0;
    for (JsonVariant rv : rels) {
      if (rc >= NH_MAX_REL) break;
      JsonObject ro = rv.as<JsonObject>();
      NRel &r = b.rel[rc];
      nhCopyUtf8(r.sport, sizeof(r.sport), (const char *)(ro["s"] | ""));
      nhCopyUtf8(r.date, sizeof(r.date), (const char *)(ro["d"] | ""));
      nhCopyUtf8(r.venue, sizeof(r.venue), (const char *)(ro["v"] | ""));
      nhCopyUtf8(r.loc, sizeof(r.loc), (const char *)(ro["l"] | ""));
      r.sm = ro["sm"] | 0;
      r.em = ro["em"] | 0;
      r.courts = ro["c"] | 0;
      rc++;
    }
    b.relCount = rc;
    i++;
  }
  nhCount = i;
  doc.clear();
  body = "";
  nhFetching = false;
  nhLoaded = true;
  nhLastFetch = millis();
  Serial.printf("[notif] %d batches, %d rels in first\n", nhCount, nhCount ? nhBatches[0].relCount : 0);
  return true;
}

// ---- 畫面 ----
static void nhDrawHeader(const char *title) {
  tft.fillRect(0, 0, SCR_W, NH_HEADER_H, C_BAR);
  // 返回 chip
  tft.fillRect(2, 2, 22, 22, C_CARD);
  tft.drawRect(2, 2, 22, 22, C_DIM);
  tft.setTextColor(C_TEXT, C_CARD);
  tft.setTextDatum(TL_DATUM);
  tft.drawString("<", 8, 6, 2);
  drawUTF8(String(title), 30, 5, C_TEXT, C_BAR);
  tft.drawFastHLine(0, NH_HEADER_H - 1, SCR_W, C_DIM);
}

static void nhDrawFooter(const String &right) {
  tft.fillRect(0, NH_FOOT_Y, SCR_W, SCR_H - NH_FOOT_Y, C_BAR);
  tft.setTextColor(C_DIM, C_BAR);
  tft.setTextDatum(TL_DATUM);
  tft.setTextSize(1);
  tft.drawString("< back   swipe scroll", 6, NH_FOOT_Y + 6, 1);
  tft.setTextSize(2);
  int w = measureUTF8(right);
  drawUTF8(right, SCR_W - 6 - w, NH_FOOT_Y + 6, C_DIM, C_BAR);
}

// 歷史頁：批次卡列表
static void nhDrawList() {
  tft.fillScreen(C_BG);
  nhDrawHeader("放場記錄");

  if (!nhLoaded) {
    drawUTF8(nhFetching ? "載入中…" : "冇記錄", 110, 100, C_DIM, C_BG);
    nhDrawFooter("");
    return;
  }
  if (nhCount == 0) {
    drawUTF8("暫時冇放場記錄", 80, 100, C_DIM, C_BG);
    nhDrawFooter("0 批");
    return;
  }

  for (int i = 0; i < NH_ROWS; i++) {
    int idx = nhScroll + i;
    if (idx >= nhCount) break;
    NBatch &b = nhBatches[idx];
    int y = NH_CARD_Y0 + i * NH_CARD_H;
    bool hot = (idx == nhDetailBatch);
    uint16_t bg = hot ? C_CARD_HOT : C_CARD;
    tft.fillRect(2, y, SCR_W - 4, NH_CARD_H - 3, bg);
    tft.drawRect(2, y, SCR_W - 4, NH_CARD_H - 3, C_DIM);

    // 時間 + 數量
    tft.setTextColor(C_ACCENT, bg);
    tft.setTextDatum(TL_DATUM);
    tft.drawString(b.t, 8, y + 3, 2);
    char cnt[16];
    snprintf(cnt, sizeof(cnt), "%d", b.n);
    int cw = tft.textWidth(cnt, 2);
    tft.setTextColor(C_GOOD, bg);
    tft.setTextDatum(TR_DATUM);
    tft.drawString(cnt, SCR_W - 10, y + 3, 2);
    tft.setTextDatum(TL_DATUM);

    // 摘要：頭兩個放場
    String summary;
    for (int j = 0; j < b.relCount && j < 2; j++) {
      if (j) summary += "  ";
      summary += fitUTF8(String(b.rel[j].venue), 110);
    }
    tft.setTextColor(C_DIM, bg);
    tft.setTextSize(1);
    tft.drawString(summary.c_str(), 8, y + 21, 1);
    tft.setTextSize(2);
  }

  // 分頁指示
  int totalPages = (nhCount + NH_ROWS - 1) / NH_ROWS;
  int curPage = nhScroll / NH_ROWS + 1;
  char page[32];
  snprintf(page, sizeof(page), "%d/%d  (%d)", curPage, totalPages, nhCount);
  nhDrawFooter(String(page));
}

// 詳情頁：單一批次全部放場
static void nhDrawDetail() {
  tft.fillScreen(C_BG);
  nhDrawHeader("放場詳情");
  if (nhDetailBatch < 0 || nhDetailBatch >= nhCount) {
    drawUTF8("冇資料", 130, 100, C_DIM, C_BG);
    nhDrawFooter("");
    return;
  }
  NBatch &b = nhBatches[nhDetailBatch];
  tft.setTextColor(C_ACCENT, C_BG);
  tft.setTextDatum(TL_DATUM);
  tft.drawString(b.t, 8, NH_HEADER_H + 4, 2);
  char head[64];
  snprintf(head, sizeof(head), "共 %d 個放場", b.n);
  tft.setTextColor(C_GOOD, C_BG);
  tft.drawString(head, SCR_W - 8, NH_HEADER_H + 4, 2);

  int y0 = NH_HEADER_H + 26;
  int rowH = 26;
  int maxRows = (NH_FOOT_Y - y0) / rowH;
  if (maxRows < 1) maxRows = 1;

  for (int i = 0; i < maxRows; i++) {
    int idx = nhDetailScroll + i;
    if (idx >= b.relCount) break;
    NRel &r = b.rel[idx];
    int y = y0 + i * rowH;
    uint16_t bg = (i % 2 == 0) ? C_BG : C_CARD;
    tft.fillRect(0, y, SCR_W, rowH, bg);

    // 行 1：運動 + 場地（去掉括號部分，loc 獨立顯示）
    String venue = String(r.venue);
    int par = venue.indexOf('（');
    if (par < 0) par = venue.indexOf('(');
    if (par > 0) venue = venue.substring(0, par);
    String l1 = String(nhSportIcon(r.sport)) + " " + fitUTF8(venue, 170);
    drawUTF8(l1, 6, y + 2, C_TEXT, bg);
    // 場地名（細字，右上）
    if (r.loc[0]) {
      tft.setTextColor(C_DIM, bg);
      tft.setTextSize(1);
      tft.setTextDatum(TR_DATUM);
      tft.drawString(r.loc, SCR_W - 6, y + 4, 1);
      tft.setTextDatum(TL_DATUM);
      tft.setTextSize(2);
    }
    // 行 2：日期 + 時間 + 場數
    char l2[80];
    const char *ds = r.date;
    if (strlen(r.date) >= 10) ds = r.date + 5;   // "2026-11-06" -> "11-06"
    snprintf(l2, sizeof(l2), "%s %02d:%02d-%02d:%02d  %d場",
             ds, r.sm / 60, r.sm % 60, r.em / 60, r.em % 60, r.courts);
    tft.setTextColor(C_DIM, bg);
    tft.setTextDatum(TL_DATUM);
    tft.setTextSize(1);
    tft.drawString(l2, 8, y + 17, 1);
    tft.setTextSize(2);
    tft.drawFastHLine(0, y + rowH - 1, SCR_W, C_BAR);
  }

  int totalPages = (b.relCount + maxRows - 1) / maxRows;
  int curPage = nhDetailScroll / maxRows + 1;
  char page[32];
  snprintf(page, sizeof(page), "%d/%d  (%d)", curPage, totalPages, b.relCount);
  nhDrawFooter(String(page));
}

// ---- touch ----
// 令 ino 知道「要返通知頁」
static bool nhWantExit = false;

static void nhTouch(int x, int y) {
  nhWantExit = false;
  // "<" 返回
  if (x < 26 && y < NH_HEADER_H) {
    if (nhDetailBatch >= 0) {
      nhDetailBatch = -1;          // 詳情 → 列表
    } else {
      nhWantExit = true;           // 列表 → 返通知頁
    }
    return;
  }
  if (nhDetailBatch >= 0) {
    // 詳情頁：點下面 = 返回列表
    if (y >= NH_FOOT_Y) { nhDetailBatch = -1; return; }
    return;
  }
  // 列表頁：撳卡片 → 詳情
  if (y >= NH_CARD_Y0 && y < NH_CARD_Y0 + NH_LIST_H) {
    int i = (y - NH_CARD_Y0) / NH_CARD_H;
    int idx = nhScroll + i;
    if (idx < nhCount) {
      nhDetailBatch = idx;
      nhDetailScroll = 0;
    }
  }
}

static void nhSwipe(int dx, int dy) {
  if (nhDetailBatch >= 0) {
    if (nhDetailBatch >= nhCount) return;
    int y0 = NH_HEADER_H + 26;
    int rowH = 26;
    int maxRows = (NH_FOOT_Y - y0) / rowH;
    if (maxRows < 1) maxRows = 1;
    int totalPages = (nhBatches[nhDetailBatch].relCount + maxRows - 1) / maxRows;
    int total = totalPages * maxRows;
    if (dy < 0) {
      nhDetailScroll += 2;
      if (nhDetailScroll > total - maxRows) nhDetailScroll = total - maxRows;
      if (nhDetailScroll < 0) nhDetailScroll = 0;
    } else {
      nhDetailScroll -= 2;
      if (nhDetailScroll < 0) nhDetailScroll = 0;
    }
    return;
  }
  if (dy < 0) {
    nhScroll += 2;
    int maxScroll = nhCount - NH_ROWS;
    if (maxScroll < 0) maxScroll = 0;
    if (nhScroll > maxScroll) nhScroll = maxScroll;
  } else {
    nhScroll -= 2;
    if (nhScroll < 0) nhScroll = 0;
  }
}
