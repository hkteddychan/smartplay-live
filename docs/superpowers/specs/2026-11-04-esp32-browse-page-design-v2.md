# ESP32 CYD — 場地瀏覽器 v2 提案（對齊 upstream browse.json）

> 日期：2026-11-04　狀態：**增強提案，等批准後實作**
> 基於：BUILD_HANDOFF.md v3.0 段 + upstream `smartplay_live_cyd.ino` + 我哋現有 v3.0 韌體

---

## 1. 重要發現（BUILD_HANDOFF v3.0）

我研究咗你俾嘅 BUILD_HANDOFF.md 同 upstream 個 CYD sketch，發現：

**Upstream 已經有齊晒：**
- ✅ `browse.json` feed（`https://.../esp32/browse.json`，~6KB，已經 live）
- ✅ 完整 CYD sketch（`smartplay_live_cyd.ino`，Arduino IDE 版）
- ✅ TFT_eSPI CYD pin map（build flags 方式）
- ✅ 3 個 Library（ArduinoJson, TFT_eSPI, XPT2046）

**我之前嘅 `evening-7d.json` patch 係多餘嘅** — upstream 已經有 `browse.json` 做同樣嘅事，而且 schema 更好（sport icons、pre-formatted dates、venue|district 合併）。

**結論：唔好再搞 source patch。直接用 upstream 嘅 `browse.json`。**

---

## 2. 兩個設計嘅對比

| 項目 | 我之前嘅提案（evening-7d.json） | Upstream v3.0（browse.json） | 增強方案 |
| :-- | :-- | :-- | :-- |
| Feed 檔名 | `evening-7d.json` | `browse.json` ✅ 已存在 | **用 `browse.json`** |
| Feed schema | `[districtIdx, venueIdx, sportIdx, dateIdx, start, end, courts]` | `[vIdx, sportIdx, dateIdx, start, end, courts]` | **用 upstream schema** |
| 運動名 | 文字 key | emoji icon (🏸🏀🏐🎾⚽) | **用 emoji** |
| 日期 | `YYYY-MM-DD` | `11-04 三` pre-formatted | **用 pre-formatted** |
| 場地/區 | 分開兩張表 | `venue|district` 合併 | **用合併** |
| 瀏覽單位 | 區份 carousel（18 區） | 區份 carousel（由 venue 推導） | **相同** |
| 觸控 | 日期 tabs + footer + overlay | 上部=上一區 / 下部=下一區 / 中部=換日期 | **用 upstream 觸控** |
| 自動翻頁 | 8 秒/區（hardcoded） | 5 秒/頁（NVS 可調） | **5 秒 + NVS** |
| 設定持久化 | 冇 | Preferences (NVS) | **加 NVS** |
| 通知模式 | alert card 蓋住所有頁 | purple line 頂部閃一下 | **用 purple line（輕量）** |
| Poll 頻率 | 1 分鐘 | 3 分鐘 | **保留 1 分鐘（更密）** |
| Push channel | port 9000 ✅ | 冇 | **保留（我哋有）** |
| 螢幕方向 | Landscape 320×240 | Landscape 320×240 | **相同** |

---

## 3. 增強方案詳細設計

### 3.1 Feed — 直接用 `browse.json`

唔使 source patch。Feed 已經 live：
```
https://hkteddychan.github.io/smartplay-live/esp32/browse.json
```

Schema（upstream 定義）：
```json
{
  "g": "2026-11-04 09:33",
  "k": ["🏸","🏀","🏐","🎾","⚽"],
  "d": ["11-04 三","11-05 四",...],
  "v": ["坪洲體育館|離島區", "香港單車館|九龍城區", ...],
  "r": [[vIdx, sportIdx, dateIdx, startMin, endMin, courts], ...]
}
```

解析成：
- `sportIcons[6]` — emoji
- `dateLabels[8]` — pre-formatted
- `venueNames[200]` / `venueDists[200]` — 從 `v` split on "|"
- `districts[24]` — 自動由 venueDists 收集（dedup）
- `browses[400]` — packed rows

### 3.2 畫面設計

```
┌────────────────────────────────────────┐  320×240 landscape
│ 離島區          全部日子     5s ▶     │  header 26px
├────────────────────────────────────────┤
│ 🏸 11-04 三                            │  row 0 (64px)
│ 坪洲體育館                             │
│ 18:00  4 場                            │
├────────────────────────────────────────┤
│ 🏀 11-05 四                            │  row 1
│ 香港單車館                             │
│ 19:00  1 場                            │
├────────────────────────────────────────┤
│ 🏐 11-04 三                            │  row 2
│ ...                                    │
├────────────────────────────────────────┤
│ 🎾 11-05 四                            │  row 3
│ ...                                    │
├────────────────────────────────────────┤
│ 3/18 區 · 頁 1/3          09:33       │  footer
└────────────────────────────────────────┘
```

每頁 4 行，自動翻頁（5 秒/頁）。4 行 × 64px = 256px + header 26 + footer 24 = 306px（剛好）。

### 3.3 觸控區域

| 區域 | Y 範圍 | 動作 |
| :-- | :-- | :-- |
| 上部 | y < 100 | 上一區 |
| 中部 | 100 ≤ y ≤ 220 | 換日期（全部→11-04→...→全部） |
| 下部 | y > 220 | 下一區 |

撳任何位置重置自動翻頁計時。Debounce 400ms。

### 3.4 自動翻頁

- 每頁顯示 4 行場次，翻頁到下一頁
- 到最後一頁 → 跳去下一區嘅第一頁
- 設定：5 秒/頁（NVS 存，可調 3/5/8/10 秒）
- 撳屏 = 暫停自動翻頁 3 秒
- NVS keys: `dist`, `date`, `sec`, `auto`

### 3.5 通知模式（並行）

- changes-eve poll 30 秒 → 1 分鐘（我哋改密咗）
- 有放場 → beep + 頂部閃紫線 2 秒（唔用全屏 alert card，避免打斷瀏覽）
- Push channel port 9000 保留（我哋有，upstream 冇）
- 通知唔會打斷瀏覽頁面，只喺頂部閃一下

### 3.6 NVS 持久化

```cpp
Preferences prefs;
// keys: "dist" (int), "date" (int), "sec" (int), "auto" (bool)
```

斷電後設定保留。開機時 loadPrefs()。

### 3.7 記憶體预算

| 項目 | 大細 |
| :-- | :-- |
| sportIcons[6] | ~0.1 KB |
| dateLabels[8] | ~0.3 KB |
| venueNames[200] + venueDists[200] | ~16 KB |
| districts[24] | ~0.6 KB |
| browses[400] × 12 B | ~4.8 KB |
| JSON 解析峰值 | ~20 KB |
| **總加** | **~42 KB**（現時 77 KB → ~119 KB / 320 KB） |

### 3.8 與現有功能嘅整合

| 現有功能 | 處理 |
| :-- | :-- |
| v3.0 poll (1 min) | **保留**，poll 頻率改 1 分鐘（現有已改） |
| Push channel (port 9000) | **保留** |
| Beep (I2S DAC GPIO26) | **保留** |
| 去重 ring buffer | **保留** |
| Baseline 判定 | **保留** |
| COM port auto-detect | **保留** |
| Venue map (today.json) | **保留**（通知模式用） |
| cyd_text.h CJK helpers | **保留**（browse 用 emoji + ASCII font 2） |
| venue_font.h (323 glyphs) | **保留**（通知模式用） |

---

## 4. 需要刪除 / 修改嘅檔案

| 檔案 | 動作 | 原因 |
| :-- | :-- | :-- |
| `patches/fetch_esp32.py` | **刪除** | evening-7d.json patch 多餘，browse.json 已存在 |
| `patches/evening_feed.py` | **刪除** | 同上 |
| `patches/evening-7d.patch` | **刪除** | 同上 |
| `patches/README.md` | **更新** | 改為說明 browse.json 已由 upstream 提供 |
| `tools/build_local_evening_feed.py` | **刪除** | 唔再需要本地 feed 重建 |
| `test/test_evening_feed.py` | **刪除** | 測試 evening_feed.py，已過時 |
| `test/test_fetch_esp32_run.py` | **刪除** | 同上 |
| `firmware/esp32_smartplay/cyd_browse.h` | **重寫** | 適配 browse.json schema + upstream UI |
| `firmware/esp32_smartplay/cyd_theme.h` | **保留** | 顏色常數仍然用 |

---

## 5. 實作計劃（分 4 個 step）

### Step 1 — 清理過時檔案
- 刪除 evening-7d 相關嘅 patches/tests/tools
- 更新 patches/README.md

### Step 2 — 重寫 cyd_browse.h
- browse.json schema 解析
- 區份收集（從 venue|district）
- 4 行/頁 UI
- 觸控區域（上/中/下）
- NVS 持久化
- 自動翻頁（5 秒/頁，可調）

### Step 3 — 整合到 smartplay.ino
- 頁面狀態機（NOTIFY ↔ BROWSE）
- 通知模式：changes-eve poll + purple line（唔用 alert card）
- Push channel 保留
- Serial commands: `g` (go browse), `n` (go notify), `u` (ui state)

### Step 4 — 驗證
- 編譯 + 燒錄
- Serial 驗證 browse.json 解析（rows, districts, dates）
- 觸控驗證（上/中/下區域）
- 自動翻頁驗證
- NVS 驗證（斷電後設定保留）

---

## 6. 開放問題

1. **通知模式 UI**：upstream 用「頂部閃紫線 2 秒」，我之前用「全屏 alert card」。你想要邊個？
   - 提案：**用 purple line**（輕量，唔打斷瀏覽），但保留 beep + serial 明細。
2. **自動翻頁速度**：upstream 預設 5 秒/頁。你想要 3/5/8/10？
   - 提案：**5 秒**（upstream 預設），NVS 可調。
3. **通知 poll 頻率**：我哋之前改咗 1 分鐘，upstream 用 3 分鐘。保留 1 分鐘？
   - 提案：**保留 1 分鐘**（更密，對搶場更有用）。
4. **Push channel**：保留 port 9000？
   - 提案：**保留**（已有，唔浪費）。

---

## 7. 唔會做嘅嘢

- **唔會**再搞 source patch（browse.json 已存在）
- **唔會**改動通知邏輯（poll 頻率、push 協定、beep、去重、baseline）
- **唔會**喺板子起 HTTP 伺服器
- **唔會**喺板子存 7 日全時段（只存 browse.json 嘅 ~200 行晚上場次）
","path":"D:\\Teddy\\Opencode\\ESP32\\docs\\superpowers\\specs\\2026-11-04-esp32-browse-page-design-v2.md"}