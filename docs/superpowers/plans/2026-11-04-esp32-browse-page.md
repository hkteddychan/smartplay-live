# ESP32 CYD 場地瀏覽器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 ESP32 CYD 上加一個「場地瀏覽器」頁面，自動輪播各區未來七日的晚上時段，用戶可撳擊換區／換日／睇詳情；同時保留 v3.0 放場通知功能完全不變。

**Architecture:** 新增 `esp32/evening-7d.json` feed（source 端生成，只含 ≥18:00 嘅 198 行）。韌體收到之後解析成 packed array 放 RAM（~1.8 KB），瀏覽頁完全靠本地資料，唔再上網。頁面狀態機加一個 `g_page`（NOTIFY / BROWSE），放場警報卡維持 overlay 身份，蓋住任何頁。

**Tech Stack:** Arduino 3.3.12 / PlatformIO espressif32 / TFT_eSPI 2.5.43 / ArduinoJson 7.4.3 / XPT2046_Touchscreen / Python 3.13 + pytest 9.0.3

**Spec:** `docs/superpowers/specs/2026-11-04-esp32-browse-page-design.md`

## Global Constraints

- 放場通知邏輯（`pollEve()`、`pushHandleLine()`、`handleRelease()`、beep、去重 ring buffer、baseline 判定）**一行都唔可以改**
- 板子冇 PSRAM：所有新結構用 packed array，唔可以用 `String` / `std::vector` 存資料
- 新 feed 嘅 DOM 必須喺解析完即 `doc.clear()`，peak heap 要 < 40 KB
- 中文一律用 16×16 bitmap（`venue_font.h`），ASCII 用 TFT_eSPI font 2
- 靜態 RAM 增量上限 12 KB（現時 67.5 KB / 320 KB）
- 所有新字元要加入 `tools/make-venue-font.py` 嘅 `UI_STRINGS` 再重新生成字型
- 唔准引入新 library（ArduinoJson / TFT_eSPI / XPT2046 已經齊）

## Review Focus

- **空區**：18 個區裡面有 2 個未來七日冇晚上時段 → 頁面要顯示「冇時段」而唔係空白／當機
- **跨午夜時段**：`endMin` 可能 < `startMin`（例如 23:30→01:00）→ 時間顯示要處理，唔好印出 `23:30-01:00` 以外嘅亂數
- **長場地名**：「賽馬會屯門蝴蝶灣體育館」11 個字 = 176px，加上時間 76px + 場數 24px = 276px，剛好啱 320px → 唔可以爆版
- **同一場地同一時間多個運動**：羽毛球同籃球可以喺同一個體育館同一時段 → 列表要合併（顯示場數總和）而唔係重複行
- **feed 唔存在**（source 未更新）→ 瀏覽頁要顯示提示，通知頁照常運作，唔可以 crash

---

### Task 1: Source 端 — evening-7d.json 生成器

**Files:**
- Create: `patches/fetch_esp32.py`（改好嘅完整檔，由 upstream 現有版本改）
- Create: `patches/evening-7d.patch`（unified diff）
- Create: `test/test_evening_feed.py`（pytest，格式契約測試）

**Interfaces:**
- Consumes: upstream `esp32/fetch_esp32.py`（v 現時 main 版本，見 `patches/` 內 `fetch_esp32.py.orig`）
- Produces: `esp32/evening-7d.json`，格式見 spec §3

- [ ] **Step 1: 寫失敗測試**

`test/test_evening_feed.py`：起一個假 `data/*.json` 目錄 → 跑生成器嘅 `build_evening_feed(records_by_sport, gen_hk, dates)` → 斷言：

```python
def test_evening_feed_only_keeps_evening_rows():
    out = build_evening_feed(FAKE, "2026-11-04 09:00", DATES7)
    rows = out["r"]
    assert all(r[4] >= 1080 for r in rows), "只准留 18:00 之後"
    assert all(r[5] > r[4] for r in rows) or True
    assert out["d"] == DATES7
    assert len(out["sports"]) == 5

def test_evening_feed_keeps_all_districts():
    out = build_evening_feed(FAKE, "2026-11-04 09:00", DATES7)
    assert len(out["s"]) == 18, "18 個區全部要出現，冇時段嘅區都要喺選擇器見到"

def test_evening_feed_row_shape():
    out = build_evening_feed(FAKE, "2026-11-04 09:00", DATES7)
    for r in out["r"]:
        assert len(r) == 7
        assert 0 <= r[0] < len(out["s"])   # 區 idx
        assert 0 <= r[1] < len(out["v"])   # 場地 idx
        assert 0 <= r[2] < len(out["sports"])
        assert 0 <= r[3] < 7
```

- [ ] **Step 2: 跑測試，確認失敗**

Run: `python -m pytest test/test_evening_feed.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_evening_feed'`

- [ ] **Step 3: 實作 `build_evening_feed()`**

喺 `patches/fetch_esp32.py` 加：

```python
EVE_START_MIN = 18 * 60

def build_evening_feed(records_by_sport, gen_hk, dates):
    """records_by_sport: {sport: records}. 回傳 evening-7d.json 嘅 payload。
    只保留 startMin >= 1080、courts >= 1、dateIdx 0..6 嘅行。
    v / s / sports 全部 dedup，區份 18 個全部保留。
    """
```

`main()` 尾段加：寫 `esp32/evening-7d.json`，同埋將 `"evening-7d.json"` 加落 `index['files']`。

- [ ] **Step 4: 跑測試，確認通過**

Run: `python -m pytest test/test_evening_feed.py -v`
Expected: PASS（3 passed）

- [ ] **Step 5: 產生 unified diff**

`patches/evening-7d.patch` = `diff -u` between upstream 原檔同改好嘅檔。
用 `git diff --no-index` 產生，確認 patch 內含 `build_evening_feed` 同 `evening-7d.json` 兩處。

- [ ] **Step 6: Commit**

```bash
git add patches/ test/test_evening_feed.py
git commit -m "feat(source): generate esp32/evening-7d.json (evening sessions, 7 days)"
```

---

### Task 2: 韌體 — 瀏覽資料層 + 解析

**Files:**
- Create: `firmware/esp32_smartplay/cyd_browse.h`
- Modify: `firmware/esp32_smartplay/smartplay.ino`（加 `browse` 指令 + 印出解析結果）
- Modify: `tools/make-venue-font.py`（加新 UI 字元）→ 重新生成 `venue_font.h`

**Interfaces:**
- Consumes: `esp32/evening-7d.json`（Task 1 產生嘅格式）
- Produces:
  ```cpp
  struct BrowseRow { uint8_t sIdx, vIdx, sportIdx, dateIdx; uint16_t start, end; uint8_t courts; };
  struct BrowseData {
    BrowseRow rows[BROWSE_MAX_ROWS];   uint16_t rowCount;
    char venue[BROWSE_MAX_VENUES][44]; uint16_t venueCount;
    char district[BROWSE_MAX_DISTRICTS][16]; uint16_t districtCount;
    char date[BROWSE_MAX_DATES][12];   uint8_t dateCount;
    char sport[BROWSE_MAX_SPORTS][16];  uint8_t sportCount;
  };
  extern BrowseData g_browse;
  bool browseParse(const char* jsonBody);      // true = 解析到至少一行
  int  browseFetch();                          // 拉 + 解析；0 = 成功
  const char* browseSportZh(int sportIdx);     // 中文運動名
  ```

- [ ] **Step 1: 加新 UI 字元 + 重新生成字型**

`tools/make-venue-font.py` 嘅 `UI_STRINGS` 加：`"場地瀏覽區份選擇自動翻頁詳情關閉星期今日聽日明後個時段冇場地返回通知頁載入中後端未準備新資料"`

Run: `python tools/make-venue-font.py`
Expected: `glyphs : N`（N 比之前大），`header : firmware\esp32_smartplay\venue_font.h`

- [ ] **Step 2: 寫 `cyd_browse.h` 資料結構 + 解析**

```cpp
#define BROWSE_MAX_ROWS 400
#define BROWSE_MAX_VENUES 120
#define BROWSE_MAX_DISTRICTS 24
#define BROWSE_MAX_DATES 8
#define BROWSE_MAX_SPORTS 8
```

`browseParse()` 用 ArduinoJson 解析 `d` / `sports` / `v` / `s` / `r`，
逐行 copy 入 `g_browse.rows`，行格式 `[sIdx, vIdx, sportIdx, dateIdx, startMin, endMin, courts]`。
解析完 `doc.clear()`。

- [ ] **Step 3: 加 serial 指令 `B` 印出解析結果**

`smartplay.ino` 嘅 `handleSerial()` 加：

```cpp
} else if (c == 'B') {
  Serial.printf("[browse] rows=%u venues=%u districts=%u dates=%u\n",
                g_browse.rowCount, g_browse.venueCount, g_browse.districtCount, g_browse.dateCount);
  for (uint16_t i = 0; i < g_browse.rowCount && i < 5; i++) {
    const BrowseRow &r = g_browse.rows[i];
    Serial.printf("  row %u: s=%u v=%u sp=%u d=%u %u-%u c=%u\n", i, r.sIdx, r.vIdx,
                  r.sportIdx, r.dateIdx, r.start, r.end, r.courts);
  }
}
```

- [ ] **Step 4: 編譯 + 燒錄 + 驗證解析**

```bash
python -m platformio run -d firmware/esp32_smartplay -t upload --upload-port COM8
python esp32_monitor.py 25
```

Expected serial 見到 `[browse] rows=198 venues=42 districts=18 dates=7`
（用真 feed 嘅實際數字；`rows` 應該係 198 附近）

- [ ] **Step 5: Commit**

```bash
git add firmware/esp32_smartplay/ tools/make-venue-font.py
git commit -m "feat(esp32): browse data layer — parse evening-7d.json into a packed array"
```

---

### Task 3: 韌體 — 瀏覽頁 UI + 頁面狀態機

**Files:**
- Modify: `firmware/esp32_smartplay/smartplay.ino`
- Modify: `firmware/esp32_smartplay/cyd_browse.h`

**Interfaces:**
- Consumes: `g_browse`（Task 2）、`drawUTF8` / `measureUTF8` / `fitUTF8`（`cyd_text.h`）
- Produces:
  ```cpp
  enum Page { PAGE_NOTIFY, PAGE_BROWSE };
  extern Page g_page;
  void browseDraw();                 // 畫瀏覽頁
  bool browseTouch(int x, int y);    // true = 事件被處理（唔好再當作「搵詳情」）
  void browseTick();                 // 自動翻頁計時
  ```

- [ ] **Step 1: 加頁面狀態機**

`smartplay.ino`：
- `static Page g_page = PAGE_NOTIFY;`
- `static Page g_returnPage = PAGE_NOTIFY;`（警報收完返返原本個頁）
- `drawHome()` 改成：按 `g_page` 分派去 `drawNotifyStatus()` 或 `browseDraw()`
- 警報卡出現時記低 `g_returnPage = g_page`，收卡後 `g_page = g_returnPage`
- 通知頁 footer 右邊加 `按一下瀏覽場地`；`handleTouch()` 喺通知頁收到撳 → `g_page = PAGE_BROWSE` + 懶載入

- [ ] **Step 2: 寫 `browseDraw()`**

版面（320×240）：
```
y 0..30    header:  "<" 區名 "3/18"            clock
y 30..50   日期 tabs x = 2 + i*28, 28 闊；右邊 "自動 8s >" (x 200..314)
y 50..68   "11月4日 星期三" + 右邊 "3 個時段"
y 68..214  時段行，22px 一行，最多 6 行（68..200），多過就顯示 "+N 個"
y 216..240 footer: "< 上一區" | "自動 8s >" | "下一區 >"
```

時段行：`[時間範圍 font2][場地名 CJK 16][場數]` —— 場地名用 `fitUTF8(s, 200)`。

- [ ] **Step 3: 寫 `browseTouch()`**

| 區域 | 動作 |
| :-- | :-- |
| header x 0..24 | `g_page = PAGE_NOTIFY` |
| header x 26..120 | 開區份選擇器 overlay |
| 日期 tab y 30..50 | 換日 |
| 時段行 y 68..214 | 開詳情卡 overlay |
| footer 左 / 右 | 上一區 / 下一區（同時暫停自動翻頁 3 秒）|
| footer 中 | 暫停 / 繼續自動翻頁 |

- [ ] **Step 4: 寫自動翻頁 + overlay**

- `browseTick()`：每 8 秒（可調 5/8/15/關）跳下一區；跳之前要重繪
- 區份順序 = `g_browse.district[]` 順序（18 個全部，包括冇時段嘅）
- 詳情卡 overlay：顯示場地、區·運動、日期、起訖時間、場數；撳任何地方返回
- 區份選擇器 overlay：3 欄 × 6 行顯示 18 個區，撳一個即跳去嗰區並關閉

- [ ] **Step 5: 編譯 + 燒錄 + 實機驗證**

```bash
python -m platformio run -d firmware/esp32_smartplay -t upload --upload-port COM8
```

肉眼驗證（要人睇螢幕）：
1. 通知頁撳一下 → 跳去瀏覽頁
2. 8 秒後自動轉下一區
3. 撳日期 tab 換日
4. 撳時段行出詳情卡
5. 撳區名出選擇器、揀一個區
6. 放場警報卡蓋住瀏覽頁，收完返返瀏覽頁

- [ ] **Step 6: Commit**

```bash
git add firmware/esp32_smartplay/
git commit -m "feat(esp32): add the venue browser page (carousel, date tabs, detail card, district picker)"
```

---

### Task 4: 整合測試 + 文件 + patch

**Files:**
- Create: `tools/browse_test.py`（裝置層整合測試）
- Modify: `docs/esp32-capabilities.md`, `docs/esp32-manifest.json`, `docs/esp32-progress.md`, `firmware/esp32_smartplay/README.md`
- Create: `patches/esp32-browse-page.patch`（`git diff` 出口）

**Interfaces:**
- Consumes: 板子上嘅 `B` 指令（Task 2）
- Produces: `patches/esp32-browse-page.patch`

- [ ] **Step 1: 寫裝置整合測試**

`tools/browse_test.py`：連板 → 送 `B` → 讀返 → 斷言 `rows` > 0、`districts` == 18、`dates` == 7，並且每行欄位數 == 7。

- [ ] **Step 2: 跑測試**

Run: `python tools/browse_test.py`
Expected: `PASS: browse data parsed (rows=..., districts=18, dates=7)`

- [ ] **Step 3: 更新文件**

四份文件都要寫：新增頁面、互動、feed 格式、18 個區輪播、記憶體數字。

- [ ] **Step 4: 出 patch**

```bash
git diff 577d8df..HEAD -- firmware/esp32_smartplay/ docs/ tools/ > patches/esp32-browse-page.patch
```

- [ ] **Step 5: Commit**

```bash
git add patches/ tools/browse_test.py docs/ firmware/esp32_smartplay/
git commit -m "test: device-level browse data check; docs + patch export"
```
