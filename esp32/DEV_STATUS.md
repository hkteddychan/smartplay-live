# ESP32 開發狀態 — SmartPLAY Live（單一資料源）

> 🤖 **俾 AI agent 睇嘅文件**（Hermes Agent + OpenCode）。
> 開工前必讀。做完嘢要更新呢份文件 — 加 entry 落「最新開發」，唔好刪人哋寫嘅嘢。
> 最後更新：2026-11-04（HKT）by Hermes Agent

---

## 🎯 專案係乜

Teddy Sir 嘅 SmartPLAY Live（康文署場地即時餘額鏡像）嘅 ESP32 端：

1. **🔔 通知模式**（已上線 v2.1）— 偵測「晚上場次有人放（📈餘額增加/🆕新時段）」就 buzzer beep
2. **📺 瀏覽模式**（已上線 v3.0）— CYD 觸屏自動翻頁顯示未來 6 日（可預訂）晚上場次，觸屏揀區份/日期

**兩個模式並行**，同一部 ESP32-CYD。

---

## 🔗 關鍵資源

| 嘢 | URL |
|---|---|
| 網站 | https://hkteddychan.github.io/smartplay-live/ |
| Repo | https://github.com/hkteddychan/smartplay-live |
| 數據鏡像 | repo `data/{sport}.json`（Cloudflare Worker 每 15min） |
| Deploy workflow | GitHub Actions workflow **id 390903074「Deploy Pages」**（手動 dispatch：`POST /actions/workflows/390903074/dispatches {"ref":"main"}`；bot push 唔會自動觸發） |
| ESP32 feed 生成 | GitHub Actions workflow **id 406044800「Build ESP32 Feed」**（push + 15min cron） |

### Live feeds（GitHub Pages，無 WAF，ESP32 直接 GET）

| Feed | 大細 | 內容 | 誰食 |
|---|---|---|---|
| `esp32/browse.json` | ~6KB | 5 運動合併、可預訂日（今日..+5）、晚上 ≥18:00 場次 | CYD 瀏覽模式 |
| `esp32/changes-eve.json` | ~1KB | 晚上放場 diff（`new`/`gone`/`chg`），排除未開賣 day-7 | 通知模式 |
| `esp32/today.json` | ~35KB | 今日+聽日全日場次 | （舊 v2.0，已棄用但仲生成） |
| `esp32/{sport}-7d.json` | 12–31KB | 個別運動 7 日全日 | （備用） |
| `esp32/changes.json` | <1KB | 全日 diff | 網站「最新改變」tab |
| `esp32/index.json` | <1KB | manifest | 參考 |

### Feed 格式

```jsonc
// browse.json
{
  "g": "2026-11-04 09:00",                    // 生成時間 HKT（版本指紋）
  "k": ["🏸","🏀","🏐","🎾","⚽"],             // 運動 icons（index = sportIdx）
  "d": ["11-04 三", "11-05 四", ...],          // 6 個可預訂日
  "v": ["香港單車館|九龍城區", ...],            // 場地|區
  "r": [[vIdx, sportIdx, dateIdx, startMin, endMin, courts], ...]  // 淨係 courts>0
}

// changes-eve.json
{
  "g": "2026-11-04 09:00",
  "prev": {"badminton": "2026-11-04 08:45"},
  "sports": {"badminton": [["2026-11-05","香港單車館","主場",1080,1140,"chg",1,3], ...]}
  // kind: "chg"=餘額變動 / "new"=新時段 / "gone"=消失
  // beep 條件: (kind=="chg" && new>old) || kind=="new"
}
```

---

## 📁 檔案地圖（repo 內）

| 檔案 | 用途 |
|---|---|
| `esp32/fetch_esp32.py` | feed 生成器（GitHub Actions 跑；讀 `data/*.json` + git history diff） |
| `esp32/smartplay_live_cyd.ino` | **v3.0 CYD 觸屏瀏覽器**（瀏覽+通知雙模式） |
| `esp32/smartplay_live_esp32.ino` | v2.1 純通知器（冇屏版；兩者 keep 同步 notify 邏輯） |
| `esp32/BUILD_HANDOFF.md` | 硬件接線 + 燒錄 + TFT_eSPI 設定（俾人讀） |
| `esp32/README.md` | feed API 文件 |
| `index.html` | 網站 SPA（有「🤖 ESP32 視角」tab = 對照工具） |

---

## 🔧 硬件（Teddy Sir 嗰邊）

| 項目 | 詳情 |
|---|---|
| Board | ESP32-2432S028R「CYD」（2.8" ILI9341 + XPT2046 觸控一體） |
| Buzzer | 被動，GPIO25(+)/GND(−) |
| LED | 內置 GPIO2 |
| TFT_eSPI pins | MISO=12 MOSI=13 SCLK=14 CS=15 DC=2 BL=21 TOUCH_CS=33 |
| 觸控校準 | sketch `map(p.x, 200, 3800, ...)` 可能要實機微調 |
| Libraries | ArduinoJson≥7、TFT_eSPI、XPT2046_Touchscreen |

**⚠️ CYD 未開箱測試** — sketch 未經實機驗證，Teddy Sir 燒錄時可能會搵到 bug。

---

## ✅ 已完成

| 日期 | 嘢 | 狀態 |
|---|---|---|
| 11-03 | compact feed 管道（fetch_esp32.py + workflow + cron safety net） | ✅ live |
| 11-03 | 網站「最新改變」tab（server-side git diff） | ✅ live |
| 11-03 | 日期多選/range + 時段 pills + HKT 修正 | ✅ live |
| 11-03 | 新數據通知 banner（poll meta.json 每 2min） | ✅ live |
| 11-04 | changes-eve.json（晚上 only + 排除 day-7） | ✅ live |
| 11-04 | ESP32 v2.1 純放場通知器 | ✅ live，未實機測 |
| 11-04 | 網站「ESP32 視角」tab（放場對照） | ✅ live |
| 11-04 | Filter 狀態 localStorage 保存（reload 唔重設） | ✅ live |
| 11-04 | browse.json + CYD 觸屏瀏覽器 v3.0 + 網站瀏覽模擬器 | ✅ live，**未實機測** |

---

## 🐛 已知問題 / 待驗證

1. **CYD sketch 未實機測** — 觸控校準、TFT_eSPI User_Setup pin match、ILI9341 SPI speed 都可能要調
2. **browse.json 冇 district index 欄** — CYD 要用 `v[]` 字串 split '|' 收集區份（已喺 sketch 做，但多一次 pass）
3. **延遲 5–20 分鐘**（mirror 15min + poll 3min）— 執雞夠用，秒殺級搶場唔適用（LCSD WAF，唔可以再密）
4. **today.json 已棄用但仍生成** — 可以慳位停咗佢
5. **changes-eve 冇 district 欄位** — 通知係全區；想限區要 backend 加

---

## 💡 Idea pool（未排期）

- OLED 屏幕另加（如果 CYD 冇貨）
- 限區 beep（只通知 3 個區）
- beep 模式選擇（長鳴/雙響）
- NTP 時間同步 → 屏上時鐘
- Deep sleep 慳電（通知 only 模式）
- 畫面 theme（dark/light）
- 多頁觸控手勢（swipe 翻頁）
- ESP32 直接訂場（❌ 唔做得 — LCSD WAF + 禁 bot，只可以 mirror）

---

## 📝 最新開發（append-only log，新 entry 放最上）

### 2026-11-04 — Hermes Agent
- v3.0 CYD 觸屏瀏覽器上線：browse.json（4.2KB）+ smartplay_live_cyd.ino + 網站瀏覽模擬器
- Filter persistence 上線（localStorage，reload 唔重設）
- ESP32 v2.1 收窄做純放場通知器（移除 today.json 場次清單）
- ⏳ 等待：Teddy Sir CYD 實機測試

### 2026-11-03 — Hermes Agent
- changes-eve.json evening feed + v2.1 sketch
- 網站「最新改變」+ ESP32 視角 tab + 日期多選 + 時段 pills + filter UI 三輪迭代
- 新數據 banner（poll meta.json）

---

## 🤝 Agent 協作守則

1. **開工前**：讀呢份文件 + `git log --oneline -10` 睇最新 commit
2. **改 sketch/feed 前**：睇「已知問題」同「Idea pool」避免重複造輪
3. **做完嘢**：append 一條 log entry + 更新「已完成」table + push
4. **發現 bug**：寫入「已知問題」，唔好默默修咗就算
5. **改 production 網站**（index.html）：先 GET 完整現有版本，細改直接做，大改加 proposal section 等 Teddy Sir 批
6. **Push 方法**：GitHub Contents API（`PUT /contents/{path}`，要舊 sha）；bot push 唔觸發 workflow — 記得手動 dispatch Deploy Pages（id 390903074）
7. **唔好做**：直接打 LCSD API（WAF）、用 `/opt/data/home/.git-credentials` 舊 PAT（已死 401）
