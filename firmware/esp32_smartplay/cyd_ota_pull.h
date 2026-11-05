#ifndef CYD_OTA_PULL_H
#define CYD_OTA_PULL_H
// ============================================================
// SmartPLAY CYD — 自動 OTA Pull（GitHub Release 為 firmware 來源）
// 流程：
//   1. 每 OTA_CHECK_INTERVAL_MS GET esp32/ota.json（version/bin/md5）
//   2. version > 本機 OTA_FW_VERSION → 下載 bin（跟 redirect）
//   3. MD5 驗證 + Update 寫入非 active 分區
//   4. 成功 → ESP.restart()；失敗 → abort，下次再試（連續 3 次失敗停 24 小時）
// ============================================================
#include <HTTPClient.h>
#include <Update.h>
#include <Preferences.h>
#include "ArduinoJson.h"

#ifndef OTA_MANIFEST_URL
#define OTA_MANIFEST_URL "https://hkteddychan.github.io/smartplay-live/esp32/ota.json"
#endif
#ifndef OTA_FW_VERSION
#define OTA_FW_VERSION "1.0"   // 本機韌體版本（跟 platformio.ini build flag 覆蓋）
#endif

static Preferences otaPrefs;
static unsigned long g_lastOtaCheck = 0;
static bool g_otaPaused = false;      // 連續失敗冷靜期
static unsigned long g_otaPauseUntil = 0;

// ---- 屏幕提示（可選 — 由主 ino 提供回調避免循環依賴）----
__attribute__((weak)) void otaScreenMsg(const char* line1, const char* line2) {
  Serial.printf("[OTA-PULL] %s | %s\n", line1, line2);
}

static int versionCmp(const char* a, const char* b) {
  int va = 0, vb = 0;
  const char *pa = a, *pb = b;
  while (*pa || *pb) {
    va = vb = 0;
    while (*pa && *pa != '.') va = va * 10 + (*pa++ - '0');
    while (*pb && *pb != '.') vb = vb * 10 + (*pb++ - '0');
    if (va != vb) return va - vb;
    if (*pa) pa++;
    if (*pb) pb++;
  }
  return 0;
}

// 連續失敗冷靜期管理
static void otaFail() {
  otaPrefs.begin("ota", false);
  int fails = otaPrefs.getInt("fails", 0) + 1;
  otaPrefs.putInt("fails", fails);
  if (fails >= 3) {
    g_otaPaused = true;
    g_otaPauseUntil = millis() + 24UL * 60UL * 60UL * 1000UL;
    Serial.printf("[OTA-PULL] 連續 %d 次失敗 — 暫停 24 小時\n", fails);
  }
  otaPrefs.end();
}
static void otaSuccess() {
  otaPrefs.begin("ota", false);
  otaPrefs.putInt("fails", 0);
  otaPrefs.end();
}

// 下載 + 寫分區（跟 redirect，WiFiClientSecure 不驗證證書 — CYD 無 clock 驗證成本高）
static bool otaDownloadAndFlash(const char* binUrl, const char* expectMd5) {
  HTTPClient http;
  http.setFollowRedirects(HTTPC_STRICT_FOLLOW_REDIRECTS);
  http.setTimeout(30000);
  http.begin(binUrl);
  int code = http.GET();
  if (code != 200) {
    Serial.printf("[OTA-PULL] 下載失敗 HTTP %d\n", code);
    http.end();
    return false;
  }
  int total = http.getSize();          // -1 = chunked
  if (total > 0 && total < 100000) {   // <100KB 明顯唔係 firmware
    Serial.println("[OTA-PULL] bin 太細，唔合理");
    http.end();
    return false;
  }
  if (!Update.begin(total > 0 ? total : UPDATE_SIZE_UNKNOWN)) {
    Serial.printf("[OTA-PULL] Update.begin 失敗: %u\n", Update.getError());
    http.end();
    return false;
  }
  if (expectMd5 && strlen(expectMd5) == 32) Update.setMD5(expectMd5);

  WiFiClient* stream = http.getStreamPtr();
  uint8_t buf[2048];
  size_t written = 0;
  unsigned long last = millis();
  bool ok = true;
  while (http.connected() && (total < 0 || written < (size_t)total)) {
    size_t avail = stream->available();
    if (avail) {
      int n = stream->readBytes(buf, min(avail, sizeof(buf)));
      if (n <= 0) { ok = false; break; }
      if (Update.write(buf, n) != n) { ok = false; break; }
      written += n;
      last = millis();
      static unsigned long lastPct = 0;
      if (total > 0 && written * 100 / total >= lastPct + 10) {
        lastPct = written * 100 / total;
        char l2[24];
        snprintf(l2, sizeof(l2), "下載 %d%%", (int)lastPct);
        otaScreenMsg("⬆️ 自動更新中", l2);
      }
    } else if (millis() - last > 20000) {
      Serial.println("[OTA-PULL] stream 逾時");
      ok = false;
      break;
    } else {
      delay(10);
    }
  }
  http.end();
  if (!ok || (total > 0 && written != (size_t)total)) {
    Serial.printf("[OTA-PULL] 下載唔完整 (%u bytes)\n", written);
    Update.abort();
    return false;
  }
  if (!Update.end(true)) {
    Serial.printf("[OTA-PULL] Update.end/MD5 驗證失敗: %u\n", Update.getError());
    Update.abort();
    return false;
  }
  Serial.printf("[OTA-PULL] ✅ 寫入 %u bytes，重啟切換新韌體\n", written);
  return true;
}

// 主檢查（loop 內定時叫）
static void otaPullCheck(bool force = false) {
  if (g_otaPaused) {
    if (millis() < g_otaPauseUntil) return;
    g_otaPaused = false;  // 冷靜期過
  }
#ifndef OTA_CHECK_INTERVAL_MS
#define OTA_CHECK_INTERVAL_MS (60UL * 60UL * 1000UL)  // 預設每小時
#endif
  static unsigned long interval = OTA_CHECK_INTERVAL_MS;
  if (!force && g_lastOtaCheck && millis() - g_lastOtaCheck < interval) return;
  if (WiFi.status() != WL_CONNECTED) return;
  g_lastOtaCheck = millis();

  HTTPClient http;
  http.setTimeout(15000);
  http.begin(OTA_MANIFEST_URL);
  int code = http.GET();
  if (code != 200) { http.end(); otaFail(); return; }
  String body = http.getString();
  http.end();

  JsonDocument doc;
  if (deserializeJson(doc, body)) { otaFail(); return; }
  const char* ver = doc["version"] | "";
  const char* bin = doc["bin"] | "";
  const char* md5 = doc["md5"] | "";
  if (!ver[0] || !bin[0]) { otaFail(); return; }
  if (versionCmp(ver, OTA_FW_VERSION) <= 0) {
    Serial.printf("[OTA-PULL] 已係最新 (%s)\n", ver);
    otaSuccess();
    return;
  }
  Serial.printf("[OTA-PULL] 有新版 %s（本機 %s）— 開始更新\n", ver, OTA_FW_VERSION);
  otaScreenMsg("⬆️ 自動更新中", "下載韌體...");
  if (otaDownloadAndFlash(bin, md5)) {
    otaSuccess();
    delay(500);
    ESP.restart();  // 唔會返嚟
  }
  otaFail();
}

#endif // CYD_OTA_PULL_H
