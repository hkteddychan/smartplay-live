# SmartPLAY Live — 開發 & 版本管理守則

## ⚠️ 背景
`main` 每 2 分鐘被 mirror worker 自動 commit 數據（🔄 開頭）— git 歷史以數據為主。
**人手開發 commit 隨時會被數據洗開**，所以版本紀律靠 tags + releases + feature branches。

## 版本規則

### Tag / Release（必須）
- 每個**功能里程碑**（新 tab、新 feed schema、firmware 大改、UX 大改）→ 打 `vX.Y` tag + GitHub Release
- firmware 有變 → release asset 附 `cyd-firmware-vX.Y.bin`（OTA 直下載）
- patch（bug fix 級）→ `vX.Y.Z`
- 現有：`v1.0`（2026-11-05 baseline）

### Branch 工作流
- 大改動（新頁面 / feed schema 改 / firmware 重構）→ `feature/<name>` branch
- 完成驗證後 merge main + 打 tag
- 現有：`feature/browse-page`（CYD 瀏覽頁 + OTA）
- **唔好直接改 `esp32/*.json` 或 `data/*.json`** — mirror 2 分鐘內會覆寫

### 咩嘢唔好 tag
- 純數據 commit（🔄 開頭）— worker 自動，冇版本意義
- 文案微調 — 攞最新 main 就得

## 部署鏈（自動）
```
LCSD API → CF Worker (*/2 cron) → commit main
                                ├─ Telegram 通知（放場 dedupe）
                                └─ 每 10 分鐘 → GitHub Pages rebuild
```
- Worker 部署版本由 wrangler 管理（`wrangler versions list`）
- 網站 = `main` HEAD 自動（Pages）
- ESP32 = `esp32/*.json` @ main HEAD（CYD 每 poll 拉最新）

## Firmware OTA 流程
1. 改 firmware → `pio run -d firmware/esp32_smartplay`
2. 測試 → OTA push（espota.py / ota_update.py）
3. 穩定 → tag + release 附 bin
4. 板子 hostname `smartplay-cyd`，密碼 `smartplay`，port 3232
