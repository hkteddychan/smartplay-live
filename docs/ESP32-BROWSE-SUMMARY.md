# ESP32 CYD — SmartPLAY Live 場地瀏覽器：實作摘要

> 日期：2026-11-04
> 板子：ESP32-2432S028R (CYD) "Cheap Yellow Display"
> 韌體版本：v3.0 + 瀏覽頁（browse.json-based）

---

## 1. 已完成嘅工作

### 1.1 韌體（firmware/esp32_smartplay/）

| 檔案 | 動作 | 說明 |
| :-- | :-- | :-- |
| `smartplay.ino` | 修改 | 頁面狀態機（NOTIFY ↔ BROWSE）、觸控分派、loop() 整合 |
| `cyd_browse.h` | 重寫 | browse.json 解析 + UI + NVS + 觸控 + 自動翻頁 |
| `cyd_theme.h` | 新增 | 共享顏色/幾何常數 |
| `platformio.ini` | 修改 | FEED_BROWSE → browse.json URL |
| `cyd_audio.h` | 保留 | I2S DAC GPIO26 beep（未改動） |
| `cyd_text.h` | 保留 | CJK helpers（未改動） |
| `venue_font.h` | 保留 | 323-glyph CJK subset（未改動） |

### 1.2 編譯結果

- RAM: 27.1% (88,844 / 327,680 bytes)
- Flash: 40.5% (1,272,551 / 3,145,728 bytes)
- Build: SUCCESS
- Flash: SUCCESS (COM8)

### 1.3 功能清單

**通知模式（保留）：**
- changes-eve.json poll（1 分鐘間隔）
- Push channel（port 9000，VM 端）
- Beep on release（I2S DAC GPIO26, quiet）
- 去重 ring buffer（16-entry）
- Baseline 判定（第一輪唔 beep）
- Venue map（today.json → 區份名）

**瀏覽模式（新增）：**
- browse.json feed（~6KB，upstream 提供，唔使 source patch）
- 4 行/頁，每行：sport icon + date + venue name + district + time + courts
- 觸控：上部=上一區 / 中部=換日期 / 下部=下一區
- 自動翻頁：5 秒/頁（NVS 可調 3/5/8/10 秒）
- NVS 持久化（district, date, sec, auto）
- 區份自動收集（從 venue|district split）
- 左上角撳 → 返通知頁
- 通知頁 footer → "按一下瀏覽場地" → 撳任何位置 → 瀏覽頁

### 1.4 Serial Commands

| 指令 | 功能 |
| :-- | :-- |
| `b` | Beep 測試 |
| `p` | Audio probe（3 路徑 × 3 頻率） |
| `r` | 重新載入 venue map + poll eve + fetch browse |
| `u` | UI 狀態（page, district, date, auto, paused, loaded, rows） |
| `g` | 切去瀏覽頁 |
| `n` | 切去通知頁 |
| `B` | Browse 資料 dump（rows, venues, districts, dates, sports） |
| `a` | 觸發 alert card |
| `h` | Help |

### 1.5 已刪除嘅檔案（過時）

- `patches/fetch_esp32.py`、`patches/evening_feed.py`、`patches/evening-7d.patch`（evening-7d.json patch 多餘）
- `tools/build_local_evening_feed.py`（唔再需要本地 feed 重建）
- `test/test_evening_feed.py`、`test/test_fetch_esp32_run.py`（測試過時嘅 module）

### 1.6 保留嘅檔案

- `esp32_port.py` + `test/test_esp32_port.py`（12 tests, 0.35s）
- `tools/cyd_relay.py`（SOCKS + push notifier + venue→district map）
- `tools/cyd_push_test.py`（push end-to-end test）
- `tools/make-venue-font.py`（CJK subset generator）
- `docs/esp32-manifest.json`、`docs/esp32-capabilities.md`、`docs/esp32-progress.md`

---

## 2. 已知問題

### 2.1 WiFi 連接失敗

板子喺測試時無法連接 "REDACTED" WiFi。PC 連接嘅係 "REDACTED"。可能係：
- "REDACTED" router 離板子太遠或已關閉
- 板子需要重新設定 WiFi credentials

**影響**：WiFi 失敗 → browse.json 同 changes-eve 都拉唔到 → 瀏覽頁顯示 "冇時段"，通知頁顯示 poll 失敗。

**解決**：確認 "REDACTED" router 開著，或修改 `platformio.ini` 嘅 `WIFI_SSID`/`WIFI_PASS`。

### 2.2 喇叭冇聲

Beep 代碼使用 I2S DAC (GPIO26)。測試時未確認有聲。可能原因：
- Speaker 未插喺 SPEAK socket
- I2S DAC mode 喺呢塊板可能唔 work
- 振幅 (4000) 太低

**測試方法**：Serial 送 `b`（beep 測試）或 `p`（audio probe，3 路徑 × 3 頻率）。

### 2.3 Push channel 未驗證 live

Oracle Cloud Security Group 關閉 TCP 9000，SSH key 認證失敗。VM 端 daemon 未部署。

---

## 3. Git History

```
577d8df chore: baseline snapshot of the ESP32 CYD workspace
5801148 feat(source): generate esp32/evening-7d.json (evening sessions, 7 days)  [已過時， evening-7d.json 已刪除]
bd46aef feat(esp32): browse data layer — parse evening-7d.json into a packed array  [已過時]
<new>   feat(esp32): browse page v2 — browse.json-based, NVS, auto-page, alert card
```

---

## 4. 下一步

1. **WiFi**：確認 "REDACTED" router 開著，或改 WiFi credentials
2. **喇叭**：插 speaker 入 SPEAK socket，送 `b` / `p` 測試
3. **Push**：開 Oracle Cloud TCP 9000，部署 VM daemon
4. **UX**：根據實機測試調整 UI（字體大小、行距、觸控靈敏度）

---

## 5. 檔案清單（最終）

```
firmware/esp32_smartplay/
├── smartplay.ino          # 主程式（通知 + 瀏覽頁面狀態機）
├── cyd_browse.h           # 瀏覽頁（browse.json 解析 + UI + NVS + 觸控）
├── cyd_theme.h            # 共享顏色/幾何
├── cyd_audio.h            # Beep（I2S DAC / PWM）
├── cyd_text.h             # CJK draw/measure/wrap
├── venue_font.h           # 323-glyph CJK subset
├── platformio.ini         # Build flags
└── README.md              # 韌體說明

tools/
├── esp32_port.py          # COM port auto-detect
├── make-venue-font.py     # CJK subset generator
├── cyd_relay.py           # VM-side SOCKS + push notifier
└── cyd_push_test.py       # Push end-to-end test

test/
└── test_esp32_port.py     # 12 tests

docs/
├── esp32-manifest.json
├── esp32-capabilities.md
└── esp32-progress.md

patches/
├── README.md              # 說明 browse.json 已由 upstream 提供
└── fetch_esp32.py.orig    # pristine upstream generator（參考）
```
