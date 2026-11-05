#pragma once
// ---------------------------------------------------------------------------
// cyd_report.h — 主動狀態回報（v1.3 新增）
//
// 之前板子只係「單向 pull」：GET GitHub Pages 嘅 JSON 顯示。
// 所以網站「ESP32 視角」睇到嘅一直係測試殘留，唔係真實狀態。
//
// v1.3 加入 POST report：板子每 5 分鐘將當前狀態 POST 去 Worker
//   POST https://smartplay-live-mirror.teddy-spot.workers.dev/esp/report
//   body: {"id":"cyd-01","fw":"v1.3","rssi":-58,"heap":120000,"up":3600,...}
//
// Worker 收到後寫 esp32/status.json + esp32/status-history.json，
// 網站 ESP32 視角就會顯示真實資料。
//
// ⚠️ RAM 紀律（板子只有 327,680 bytes DRAM）：
//   - payload 用固定大小 char buffer，唔用 ArduinoJson（JSON builder 太耗 RAM）
//   - 唔好加 String 拼接，用 snprintf 直接砌
//   - 一次只送一個 report
// ---------------------------------------------------------------------------
#include <Arduino.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

#include "cyd_text.h"

// 每次 POST 間隔（5 分鐘）— 唔好太密，GitHub API 有 rate limit
#define REPORT_INTERVAL_MS (5UL * 60UL * 1000UL)

// 首次報告延遲（開機 30 秒後先報，等 WiFi + 畫面準備好）
#define REPORT_FIRST_DELAY_MS 30000UL

// payload 上限 — 細啲好，避免 heap 峰值
#define REPORT_MAX_LEN 320

static unsigned long g_lastReportAt = 0;
static int g_reportFails = 0;   // 用 int —— bool ++ 喺 C++17 唔合法

// 版本號 —— 用 platformio.ini build flag（OTA_FW_VERSION），
// 咁樣 OTA manifest 同螢幕顯示嘅版本永遠一致，唔會有人工同步錯誤。
// ⚠️ OTA_FW_VERSION 喺 cyd_ota_pull.h 已經定義（同一個 build flag），
//    所以呢度唔好再 #define，否則 redefinition error。
static char g_reportFw[16] = "v" OTA_FW_VERSION;

// 板子識別
static const char *REPORT_BOARD_ID = "cyd-01";

// Worker endpoint（POST /esp/report）
static const char *REPORT_URL =
    "https://smartplay-live-mirror.teddy-spot.workers.dev/esp/report";

// ---------------------------------------------------------------------------
// 狀態 getter —— 由 smartplay.ino 提供（避免頭文件循環依賴）
// 呢幾個函式喺 smartplay.ino 入面實作。
// ---------------------------------------------------------------------------
struct ReportState {
  const char *district;   // 當前區（瀏覽頁 / 通知頁）
  const char *date;       // 當前日期 label
  int page;               // 當前頁
  int pages;              // 總頁數
  int rows;               // 當前列數
  const char *line;       // 第一行顯示內容
};

// 由 smartplay.ino 填入（見 smartplay.ino::collectReportState）
void reportCollectState(ReportState &st);

// ---------------------------------------------------------------------------
// POST report
// ---------------------------------------------------------------------------
// ⚠️ WiFiClientSecure 一定要 static —— local 變數會喺 stack 開 ~5KB，
//    ESP32 stack 只有 8KB，會 overflow。
static WiFiClientSecure g_repSec;

static bool httpPostReport(const char *url, const char *body, size_t len) {
  if (WiFi.status() != WL_CONNECTED) return false;
  g_repSec.setInsecure();
  HTTPClient http;
  if (!http.begin(g_repSec, url)) return false;
  http.setTimeout(15000);
  http.setUserAgent("SmartPlayLive-ESP32/3.1");
  http.addHeader("Content-Type", "application/json");
  int code = http.POST((uint8_t *)body, len);
  if (code != 200) {
    Serial.printf("[REPORT] POST -> %d\n", code);
    http.end();
    return false;
  }
  http.end();
  return true;
}

// ---------------------------------------------------------------------------
// 組裝 payload + 送出
// ---------------------------------------------------------------------------
static void reportSendNow() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[REPORT] wifi down, skip");
    g_reportFails++;
    return;
  }

  ReportState st;
  reportCollectState(st);

  char body[REPORT_MAX_LEN];
  int n = snprintf(body, sizeof(body),
                   "{\"id\":\"%s\",\"fw\":\"%s\","
                   "\"district\":\"%s\",\"date\":\"%s\","
                   "\"page\":%d,\"pages\":%d,\"rows\":%d,"
                   "\"line\":\"%s\","
                   "\"rssi\":%d,\"heap\":%lu,\"up\":%lu}",
                   REPORT_BOARD_ID, g_reportFw,
                   st.district ? st.district : "",
                   st.date ? st.date : "",
                   st.page, st.pages, st.rows,
                   st.line ? st.line : "",
                   (int)WiFi.RSSI(),
                   (unsigned long)ESP.getFreeHeap(),
                   (unsigned long)(millis() / 1000UL));
  if (n <= 0 || n >= (int)sizeof(body)) {
    Serial.println("[REPORT] payload overflow");
    g_reportFails++;
    return;
  }

  bool ok = httpPostReport(REPORT_URL, body, (size_t)n);
  if (ok) {
    g_reportFails = 0;
    Serial.printf("[REPORT] sent %d bytes, up=%lus\n", n, millis() / 1000UL);
  } else {
    g_reportFails++;
    Serial.printf("[REPORT] failed (fails=%d)\n", g_reportFails);
  }
  g_lastReportAt = millis();
}

// ---------------------------------------------------------------------------
// loop() 內調用 — 檢查係咪夠鐘要報
// ---------------------------------------------------------------------------
static void reportTick() {
  unsigned long now = millis();
  if (now < REPORT_FIRST_DELAY_MS) return;
  if (now - g_lastReportAt < REPORT_INTERVAL_MS) return;
  reportSendNow();
}

// 開機時初始化（setup() 調用）
static void reportInit() {
  g_lastReportAt = 0;
  g_reportFails = 0;
}
