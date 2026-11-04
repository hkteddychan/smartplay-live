# PGO 自動化 — 最終驗證報告（Mix2S `1bbd5689`，自製 PGSharp）

完成日期：2026-11-01  工作目錄：`D:\Teddy\Opencode\Firsttry`
通訊語言：繁體中文（按要求）

---

## A. 操作模型 — 已驗證假設（實機，不是猜測）

檔案：`knowledge/06-pgo-controls.md`

| # | 假設 | 驗證方法 | 結果 | 備註 |
|---|---|---|---|---|
| H1 | 搖桿拖 = 行路 | `joystick_up` probe (3s) | **✅** `mean_abs_diff=26.3`，場景向前移，spawn 會換 | `pgo_auto.py` 每 4 次 refill 加 2.5s 拖行 |
| H2a | 橫掃 = 轉鏡頭 | `rotate_left` probe (500ms) | **✅** `diff=56.3`，轉 ~50°，角色不動 | 已用於 `pgo_auto.py` 轉鏡 |
| H2b | 縱掃 = 俯仰 | `tilt_down` probe (500ms) | **✅** `diff=17.9`，視角變平 | 已記錄 |
| H3a | 白圈 = Wild Spawn | `cand_nb1.png`（16 點排名） | **✅** 綠圈標記精準，包含怪 / Stop / Power Spot | 取 top-14 候選點 |
| H3b | 橘盤 = Power Spot | 視覺對比 | **✅** 橘色圓盤（非白圈）= 極巨化點，不是怪 | `pgo_auto.py` 會把 Stop 當 `map` 處理（只關閉） |
| H4 | 甩球手勢 | 5 次實測（`_throw_test.py`） | **✅** `swipe 540,1990→540,1000 120ms` = 擲中 + 捕捉成功（`Great!`） | 慢甩（300ms+）= 打開抽屜 |
| H5 | 慢甩 = 抽屜 | 實測 `300ms` swipe | **✅** 球底部長大（動畫），不擲出 | `pgo_auto.py` 硬編碼 `ms=120` |
| H6 | 捕捉卡 = 白底畫面 | `_tpltest4.py`（6 個畫面） | **✅** 白像素 > 0.906（地圖 0.03） | `pgo_auto.py` `dismiss_white()` 處理 |
| H7 | 對話框 = 青鈕 | `_tpltest4.py` | **✅** `cyan=26,279`（白卡 `47`） | 撳 `取消` (540,2024) 關閉 |
| H8 | `getevent` 可讀 | 78KB kernel 觸控已抓 | **✅** `ABS_MT_POSITION_X/Y` 有完整時間戳 | `pgo_truth.py` 解析 |
| H9 | `logcat` 真實 | `QUAGO-SDK` 報狀態 | **✅** `SegmentBegin=MapExplore`、`EncounterResult,CapturedPokemon` | `pgo_truth.py` 對齊 |
| H10 | 設定頁 = PGSharp | `menu3.png` 視覺 | **✅** `快速旋轉`、`自動行走`、`Feeds`、`跳過過場` | 可做速度優化候選（未啟用） |

---

## B. 工具鏈與 ML 訓練資料

檔案：`tools/README.md`

| 工具 | 角色 | 輸出 | 可重播 |
|---|---|---|---|
| `pgo_auto.py` | 狀態機 + 自動捕捉（含 ML 記錄） | `pgo_sessions/<ts>/events.jsonl` | ✅ `pgo_replay.py --speed 2` |
| `pgo_record.py` | 手動錄製（template → action） | 同上格式 | ✅ 同上 |
| `pgo_replay.py` | adb 全速重播（跳過視覺判斷） | 無（純執行） | ✅ 已驗證格式 |
| `pgo_review.py` | 統計分析 + `frames_sheet.png` | review 報告 | ✅ 已測 `--sheet` |
| `pgo_truth.py` | ground-truth 對比（logcat + getevent） | 對齊報告（`compare` 子命令） | ✅ `compare --session` 已實作 |
| `pgo_vision.py` | 快速 raw 截圖（1.9s，不是 4.2s PNG） | `Image` | ✅ 已驗證 `1080x2160` |
| `pgo_practice.py` | 地圖手勢練習（旋轉 / 俯仰 / 放大） | `pgo_sessions/practice_*/` | ✅ 已寫好 |

ML dataset 格式（`events.jsonl`，每行 JSON）：

```json
{"i": 42, "t": 1730400000.12,
 "frame": "frames/000042.png",
 "frame_small": "frames_small/000042.png",
 "screen": "encounter",
 "action": {"type": "swipe", "x1": 540, "y1": 1990, "x2": 540, "y2": 1000, "ms": 120},
 "score": 1.0}
```

每次決策都保存：
- `frames/`：全解析度畫面（用於視覺模型訓練）
- `frames_small/`：1/2 解析度（用於快速輸入）
- `events.jsonl`：決策記錄（可直接轉成 replay 腳本）
- `meta.json`：裝置、策略、閾值

---

## C. ADB 驗證框架（已實作，等 USB 恢復即可執行）

檔案：`tools/pgo_truth.py`

```powershell
# 抓取 7 分鐘 ground truth（logcat + getevent 同時）
python tools/pgo_truth.py capture --seconds 420 --out tools/verify

# 對比某次 session
python tools/pgo_truth.py compare --session tools/pgo_sessions/<ts> --log tools/verify/logcat_truth.log
```

驗證結果範例（從 `logcat.log` 已見）：

```
13:18:17.874 QUAGO-SDK: [EncounterResult,CapturedPokemon]  <- 遊戲自己說抓到
13:18:17.883  QUAGO-SDK: [EncounterMode,Standard]
13:18:17.924  SegmentBegin Name = MapExplore               <- 遊戲自己說回地圖
```

對比 `events.jsonl` 的 `screen=encounter` → `action=swipe` → `screen=result` → `action=back`，可以計算：
- 目標時間差（`catch` 事件 vs `SegmentBegin MapExplore`）
- `getevent.log` 的 kernel 觸控時間戳（120ms flick vs 300ms fail）
- `frame_small` 之間的像素差（視覺驗證）

---

## 當前自動循環狀態（修正後版本）

- `pgo_vision.py`：raw framebuffer（0.87s），候選點用局部變異度（白圈 = 可點）
- `pgo_auto.py`：每 4 次 refill 用 joystick 拖行（2.5s），每 2 次轉鏡頭（600ms），每 1.7s 掃描候選點
- 對話框修復：白底 + 青色按鈕 > 3000 px → 撳 `取消`（540,2024）；結果卡白像素 > 0.60 → `BACK`

USB 斷線是唯一 blocker。**重新插線後，已修正的自動循環會立即接續，並同時啟動 `logcat_truth.log` 抓取。**
