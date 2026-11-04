# PGO 自動捕捉工具鏈（Mix2S `1bbd5689`）

全部工具都係「視覺判斷 → adb 動作」，**每個決策都會寫入 ML dataset**，
之後可以直接用 `pgo_replay.py` 跳過視覺、全速重播。

## 流程

```
adb screencap ──► 狀態分類器 ──► 動作 ──► 記錄 (frame + action)
                     │
                     ├─ encounter ─► 快速上甩 (swipe 540,1990 → 540,1000, 120ms)
                     ├─ result    ─► BACK 返地圖
                     ├─ map       ─► 網格掃描 tap 搵野生怪
                     ├─ stop      ─► tap X 關閉 PokéStop 相片圓盤
                     └─ other     ─► 等（投擲動畫 / 轉場）
```

## 指令

```powershell
# 自動捕捉 10 隻（同時錄 dataset）
python tools/pgo_auto.py --catches 10 --minutes 25

# 只錄不操作（校準用）
python tools/pgo_auto.py --catches 10 --dry-run

# 分析某次 session
python tools/pgo_review.py tools/pgo_sessions/<ts> --sheet

# 全速重播（無視覺，純 adb）
python tools/pgo_replay.py tools/pgo_sessions/<ts> --speed 2

# 地圖手勢練習（旋轉 / 俯仰 / 放大），12 回合
python tools/pgo_practice.py --rounds 12
```

## 狀態分類門檻（1080×2160，實機量測）

| 狀態 | 判別方式 | 實測值 |
| :--- | :--- | :--- |
| `encounter` | 莓果按鈕 NCC > 0.65 | 0.999（其他畫面 ≤ 0.44） |
| `result` | 下半部白像素比例 > 0.60 | 0.906（地圖 0.03） |
| `stop` | 底部紅色像素 > 40000 | 93108（相片圓盤） |
| `map` | 底部紅色像素 > 4500 | 4785–6694（底部中央精靈球） |
| `other` | 其餘 | 投擲動畫、轉場 |

## 已確認嘅裝置事實

- 螢幕 1080×2160；`adb` 身份係 `shell`（uid 2000），**無 root**
- `sendevent /dev/input/event2` 被 SELinux 擋 → **冇 multi-touch pinch**
  （所以放大只有 double-tap，縮細做唔到）
- 截圖必須用 `cmd /c "adb ... exec-out screencap -p > file"`，PowerShell `>` 會毀壞 PNG
- 屏幕保持開啟 + 亮度 0（`svc power stayon true`）→ 睇落似熄 mon 但遊戲照跑
- 投擲手勢：由球中心 `(540,1990)` 快速上甩到 `(540,1000)`，**120ms**
  （慢過 ~250ms 會變成打開精靈球抽屜，唔會擲出）

## Dataset 格式

`tools/pgo_sessions/<ts>/`

```
frames/000000.png        全解析度畫面
frames_small/000000.png  1/2 解析度（訓練輸入）
events.jsonl             每行一個決策
meta.json                裝置 / 政策 / 門檻
```

```json
{"i": 42, "t": 1730400000.12, "frame": "frames/000042.png",
 "frame_small": "frames_small/000042.png", "screen": "encounter",
 "action": {"type": "swipe", "x1": 540, "y1": 1990, "x2": 540, "y2": 1000, "ms": 120},
 "score": 1.0}
```

## 檔案

| 檔案 | 用途 |
| :--- | :--- |
| `pgo_auto.py` | 自動捕捉狀態機（含錄製） |
| `pgo_record.py` | Session 寫入器（frames + events.jsonl） |
| `pgo_replay.py` | adb 全速重播 |
| `pgo_review.py` | session 統計 + contact sheet |
| `pgo_practice.py` | 地圖手勢練習（錄製） |
| `pgo_throw.py` | NCC 模板匹配引擎 |
| `templates/tpl_berry.png` | encounter 判別模板 |
| `templates/tpl_encounter_throw.png` | 擲球按鈕模板 |

## 資料層（免截圖）

見 [`docs/data-layer.md`](../docs/data-layer.md)。核心：PGSharp 浮層是原生 View，可讀可點；
遊戲本體是 Unity，完全看不到。

```powershell
python tools/pgo_layer.py state      # map / encounter / mon_detail / settings / raid ...
python tools/pgo_layer.py mon        # L / IV / 三項 + 內部一致性檢查
python tools/pgo_layer.py toggles    # 37 個設定開關
python tools/pgo_layer.py guard      # R5：遇到團體戰直接拒絕
python tools/pgo_layer.py verify     # 資料層 vs 截圖 一致性統計
python tools/pgo_run.py --catches 5  # 資料層優先自動迴圈（走路/轉站/捕捉/錄資料）
python tools/pgo_collect.py --target 3   # 繞角色探測取遭遇樣本 + 捕捉（全程不截圖）

# 語意化操作（不用座標，可操作畫面外的控制項）
python tools/pgo_direct.py demo
python tools/pgo_layer.py info 虛擬定位
python tools/pgo_layer.py toggle 快速狙擊 I
python tools/pgo_layer.py clicknode 設置
python tools/pgo_layer.py clickables --leftmax 130
python tools/pgo_layer.py index_click 5

# 位置（資料層讀傳送面板）與空間觀測帳本
python tools/pgo_layer.py position
python tools/pgo_layer.py joystick
python tools/track.py --samples 4 --walk 5000     # -> tools/verify/position_track.jsonl
python tools/pgo_survey.py --minutes 6            # -> tools/verify/observations.jsonl
python tools/pgo_log_catch.py --tap 600 1735      # 單次遭遇：位置+IV+捕捉入帳
python tools/pokestop_ledger.py --samples 3       # -> tools/verify/pokestop_ledger.jsonl
python tools/_grid.py <screenshot.png>            # 畫座標網格，讀真實像素座標

# 安全檢查：強制關閉快速狙擊並寫 settings 快照
python tools/_safe_settings.py
```

延遲：資料層 **236 ms** vs 截圖 **812 ms**（快 3.4×）。
遭遇樣本累積於 `tools/verify/encounters.jsonl`。

## 規則（`pgo_rules.py`）

| 編號 | 規則 |
| :--- | :--- |
| R1 | 禁用 超級球（Great Ball） |
| R2 | 禁用 金色提子（Golden Razz） |
| R3 | 只用 精靈球 / 高級球，預設 精靈球 |
| R4 | 自動投食只用 蔓莓果/蕉香果/凰梨果，不做手動餵食 |
| R5 | **絕不進入/參與任何團體戰**（對戰 / 極巨化 / Raid） |

