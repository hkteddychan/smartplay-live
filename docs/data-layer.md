# 資料層（Accessibility Layer）讀取能力與正確性驗證

> 目的：讓之後的操控**不需要截圖判斷畫面**，直接從節點樹讀狀態、讀寶可夢資訊。
> 實測裝置：`1bbd5689`（Mi MIX 2S，1080×2160），2026-11-02。

## 1. 原理

PGSharp 的浮層（側選單、設定頁、遭遇浮標、附近清單、系統對話框）是**原生 Android View**，
會出現在 `AccessibilityNodeInfo` 樹內；遊戲本體（地圖、寶可夢模型、戰鬥、獎勵卡）是 **Unity
SurfaceView**，整棵樹只有一個 `android.view.View|Game view`，沒有任何子節點。

我們的 `com.opencode.pgodrive` instrumentation APK 直接讀這棵樹，因此：

- 原生 UI → **可讀、可點、可列舉**（含畫面外的設定列）
- Unity 畫面 → **完全不可見**（只能靠截圖）

## 2. 已驗證可讀（有截圖/畫面交叉核對）

| 資訊 | 來源節點 | 驗證 |
| :--- | :--- | :--- |
| 目前介面（map / encounter / mon_detail / settings / pg_side_menu / raid / 對話框） | 文字簽名 | 6/6 與像素分類一致（map） |
| 寶可夢等級 `L` | `TextView` | `L21`、`L10`、`L21` 三次皆與畫面相同 |
| 個體值 `IV` | `TextView` | `IV53`、`IV40`、`IV73` 皆相同 |
| 三項個體 `10/6/8` | `TextView` | 三次皆相同 |
| 天氣加成 `†` | `TextView` | 相同 |
| 莓果列 `蔓莓果/蕉香果/凰梨果` | `TextView` | 遭遇時出現、離開即消失 |
| PGSharp 側選單 7 項 + 座標 | `TextView` | 座標與畫面 1:1（設置 = 928,786） |
| 設定頁 37 個開關 | `Switch` 的 `K`/`X` 旗標 | 可見列全部吻合（虛擬定位 On、速度 30.0 …） |
| 數值欄位（速度） | `EditText` | `30.0` |
| 傳送面板 座標/距離/冷卻 | `EditText`/`TextView` | 欄位存在，未輸入時為空 |
| 系統對話框按鈕 | `Button`/`TextView` | `等一下`、`確定`、`取消` 可層級點擊 |
| 地圖檢視器 縮放/圖層按鈕 | `ImageView`/`ToggleButton` | `+`(992,1984)、`−`(992,2072)、三個圖層 ToggleButton |

### 設定頁實測（節錄）

```
帳號管理員 Off | 虛擬定位 On | 操縱桿 On | 隱藏訓練家名字 On
顯示背包寶可夢IV On | 顯示野外寶可夢IV On | 抓獲結果預覽 On
快速捕捉 Off | 快速旋轉 On | 跳過過場動畫 Off
Raid & Gym Battle Assistant Off | 極巨化戰鬥輔助 Off
```

`快速旋轉 On` 解釋了為何走近補給站就會自動轉（不必手動畫圈）。

## 3. 不可讀（Unity 繪製）

| 資訊 | 說明 |
| :--- | :--- |
| 地圖上的補給站 / 野生寶可夢 / 道館 | 全是貼圖，無節點 |
| 補給站相片圓盤（`Months of the Year` 那種） | 實測 49 個節點全是系統列，**層級只會回報 `map`** |
| 寶可夢**名字**、**CP**、球數 | 遭遇畫面由 Unity 繪製 |
| 捕捉獎勵卡（TOTAL X XP） | 無節點，但**非模態**（點擊會穿透到地圖） |
| 旋轉補給站的結果 / 冷卻動畫 | 無節點 |

## 4. 正確性驗證：IV 內部不變量

客戶端顯示的 `IV` 等於 `int(100 × (atk+def+sta) / 45)`，是**截斷**（不是四捨五入）。
四筆實測全部成立：

| 寶可夢 | L | 三項 | 計算 | 顯示 IV | 結果 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 木木梟 | 21 | 10/6/8 | 24/45 = 53.33 | 53 | ✅ |
| 怨影娃娃 | 10 | 1/8/9 | 18/45 = 40.00 | 40 | ✅ |
| 怒鸚哥 | 21 | 13/8/12 | 33/45 = 73.33 | 73 | ✅ |
| （天氣加成） | 16 | 6/4/15 | 25/45 = 55.56 | **55** | ✅ 截斷 |

最後一筆證明是截斷：四捨五入會是 56，客戶端顯示 55。

`pgo_layer.mon()` 會自動計算 `iv_expected` 與 `consistent`（容差 0），
可當作即時自我檢查；每筆遭遇都會寫入 `tools/verify/encounters.jsonl`。

## 5. 效能

| 方式 | 平均延遲 |
| :--- | ---: |
| 資料層 `dump`（單一 adb 來回） | **236 ms** |
| `screencap` 截圖 | 812 ms |

資料層快 **3.4×**，而且不會讓 GPU 停頓等截圖。

## 6. 實測踩到的坑（已修正）

1. **詳情頁誤判遭遇**
   PGSharp 的 `L/IV` 浮標會延續顯示在寶可夢詳情頁上，只憑 `L`+`IV` 會把詳情頁當成遭遇。
   → 修正：**遭遇的唯一判據是莓果列**（`蔓莓果/蕉香果/凰梨果`）；無莓果但有 `L/IV` 判為 `mon_detail`。

2. **投擲動畫造成假結束**
   投球時莓果列會消失約 1 秒，單次讀不到就判定「捕捉結束」會誤判。
   → 修正：`encounter_ended()` 要求連續 6 次（≈2.1 s）非遭遇才成立。

3. **獎勵卡非模態**
   實測點擊會**穿透**到地圖（角色會走動、會開到別的視窗），所以不可以去點它。
   → 修正：層級流程直接忽略獎勵卡，不做任何點擊。

4. **注入過快會讓 Unity 主執行緒 ANR**
   `dumpsys activity lastanr` 顯示 `Waited 5005ms for MotionEvent`。
   → 對策：每次輸入後 `--settle`（預設 4 s），單一輸入、低頻操作。

5. **補給站圓盤／獎勵卡讓 `map` 變成「假地圖」**
   這兩種全螢幕 Unity 覆蓋層開啟時，節點數掉到 ~49 且全是狀態列，`state()` 會回報 `map`。
   → 對策：`pgo_run` 用「橘色佔比」過濾掉補給站本體，避免點開圓盤；
   獎勵卡非模態可忽略；圓盤用 BACK 關閉（實測有效）。

6. **搖桿座標會漂移**
   硬編 `(129,1587)` 在某次重啟後完全走不動（座標沒變）；
   資料層顯示搖桿 `View` 實際在 `(128,1507)`，改用 `L.joystick()` 動態取得後
   每 5 秒穩定移動 ~40 m。

## 7. 補給站狀態與寶可夢位置（重點）

**結論：PGSharp 沒有提供任何可從存取層讀取的「位置 / 狀態」資料源。**

本輪新增的四個實驗與結果：

| 實驗 | 結果 |
| :--- | :--- |
| 地圖檢視器開啟「補給站」圖層（ToggleButton 由 Off→On） | 節點數 **99 → 99**，標記是 Mapbox 繪製的圖形，不是 View |
| 地圖檢視器搜尋（放大鏡） | 只彈出**數字鍵盤**（`坐標/地點` + `1..9,0`），只能輸入座標，不能搜名稱 |
| `Feeds` 三個分頁（寶可夢/團體戰/Quest） | 免費版需掃描條件，清單為空；**沒有補給站分頁** |
| 左側「附近的寶可夢」條目（可點節點） | 單擊／雙擊都沒有反應（`快速狙擊` 關閉時不作用） |

其他已知事實（前幾輪）：邊走邊監看 10 秒沒有任何補給站原生文字；logcat 完全沒有
fort/spin 事件；補給站相片圓盤開啟時節點只剩系統列。

因此「寶可夢位置」與「補給站狀態」只能靠截圖（顏色/貼圖）或 root 讀記憶體。

**可以從資料層拿到的是「控制」與「自身位置」，不是物件座標**：見下一節。

### 7.1 唯一可讀的位置資料：傳送面板的當前座標

`傳送` 面板會把**玩家目前經緯度**畫成一般 `TextView`：

```
[0] {'known': True, 'lat': 40.753897, 'lon': -73.982076, 'local': '11-01 14:06:58'}
     walking up 5000 ms ...        ← 搖桿由資料層動態定位 (128,1507)
[1] {'known': True, 'lat': 40.754234, 'lon': -73.981948, ...}   moved 39.0 m
[2] {'known': True, 'lat': 40.754595, 'lon': -73.981811, ...}   moved 41.8 m
[3] {'known': True, 'lat': 40.755018, 'lon': -73.981655, ...}   moved 48.8 m
total moved: 129.6 m
```

每 5 秒移動 39–49 m，與設定速度 **30 km/h ≈ 41.6 m / 5 s** 吻合 —— 這是
「資料層 → 位置」的實證，`tools/track.py` 會寫入 `tools/verify/position_track.jsonl`。

因此寶可夢位置可以用「遭遇時的玩家座標」表示（`tools/pgo_survey.py` →
`tools/verify/observations.jsonl`），而不是去讀 Unity 貼圖。

實際寫入的紀錄（2026-11-02）：

```json
{"kind":"encounter","lat":40.755018,"lon":-73.981655,"local":"11-01 14:20:30",
 "mon":{"level":"3","iv":"57","split":"2/12/12","iv_expected":57,"consistent":true,
        "berries":["蔓莓果","蕉香果","凰梨果"]}}
{"kind":"catch","lat":40.755018,"lon":-73.981655,"ball":"精靈球","throws":1,
 "mon":{"level":"3","iv":"57","split":"2/12/12","consistent":true}}
```

### 7.1.1 補給站帳本（`tools/pokestop_ledger.py`）

既然逐站狀態讀不到，就把它**明確標成 null 並記錄原因**，同時記錄真正決定旋轉的
資料（位置、時間、`快速旋轉`、速度）：

```json
{"i":0,"kind":"pokestop_traversal","lat":40.755018,"lon":-73.981655,
 "local":"11-01 14:21:32","auto_spin":true,"speed_kmh":"30.0","moved_m":0.0,
 "per_stop_state":null,
 "why_null":"PokéStop is a Unity sprite; the accessibility layer has no node for it"}
```

`moved_m: 0.0` 是因為當下 PGSharp 的搖桿 `View` 節點從樹中消失（`joystick()` 回
`None`，整棵樹只剩 `Game view`），並非位置讀取失敗；同一支搖桿在節點存在時
（`(128,1507)`）可穩定 5 秒走 ~40 m。

### 7.2 禁用事項：快速狙擊

`快速狙擊 I/II` 會把角色傳送到目標，是明顯的封號風險（使用者指示 2026-11-02）。
`tools/_safe_settings.py` 會強制把它們與 `冷卻計時器` 關閉並寫入快照，
`stop_status()` 回報 `sniping_disabled`；`pgo_survey` 若發現未關閉會直接中止。

## 8. 用資料層直接操作（不需要座標）

驅動新增三個語意化指令，全部由節點資料解析，**不使用螢幕座標**：

| 指令 | 作用 | 為何重要 |
| :--- | :--- | :--- |
| `info <label>` | 回傳 `clickable/checkable/checked/bounds/class` | 先讀後決定，不再猜 |
| `clicknode <label>` | 對「該標籤的可點祖先」做 `ACTION_CLICK` | 不必知道按鈕在哪 |
| `toggle <label>` | 對該列擁有的 `Switch` 做 `ACTION_CLICK` | **可操作畫面外控制項**（座標點不到） |
| `clickables [leftmax]` | 列舉左側可點節點並編號 | 附近清單**完全無文字**，只能靠列舉順序定位 |
| `index_click <n> [leftmax]` | 點第 n 個可點節點 | 用資料層順序驅動點擊，不需座標 |
| `position` | 傳送面板的當前經緯度 | 資料層唯一的「位置」資料 |
| `joystick` | 由 `View` 節點算出搖桿中心 | 搖桿座標會漂移，硬編會走不動 |

實測（`python tools/pgo_direct.py demo`）：

```
PASS  return to map
PASS  open PGSharp menu
PASS  menu read from layer: ['地圖', '30.0 km/h', '自動行走', 'Feeds', '收藏夾', '傳送', '設置']
PASS  clicknode 設置 (by label)
PASS  state == settings
PASS  info 虛擬定位 -> OK 虛擬定位|clickable=false|checkable=false|checked=false|...
PASS  toggle 快速旋轉 round-trip True -> False -> True
PASS  clicknode 確定
PASS  closed settings (state=pg_side_menu)
DEMO PASS
```

`快速狙擊 I` 這類列在清單中位於 **y < 0（畫面外）**，座標點擊不可能命中，
但 `toggle 快速狙擊 I` 仍成功切換（False → True → False）。

另外修正了一個真實 bug：`findText` 原本只做子字串比對，`快速狙擊 I` 會誤中
`快速狙擊 II`；現改為**先精確、後模糊**兩段匹配。

## 9. 使用方式

```powershell
# 目前介面（純資料層）
python tools/pgo_layer.py state

# 遭遇資料 + 內部一致性檢查
python tools/pgo_layer.py mon

# 全部原生文字（界定可讀邊界）
python tools/_texts.py

# 設定開關 / 數值 / 側選單 / 附近寶可夢
python tools/pgo_layer.py toggles
python tools/pgo_layer.py values
python tools/pgo_layer.py menu
python tools/pgo_layer.py feed

# R5 守衛（遇到團體戰直接拒絕）
python tools/pgo_layer.py guard

# 語意化操作（不需要座標）
python tools/pgo_direct.py demo
python tools/pgo_layer.py info 虛擬定位
python tools/pgo_layer.py toggle 快速狙擊 I
python tools/pgo_layer.py clicknode 設置

# 資料層 vs 截圖 一致性統計（寫入 tools/verify/layer_vs_pixels.jsonl）
python tools/pgo_layer.py verify --rounds 10

# 離線回歸測試（用真實 dump 驗證解析器，不需裝置）
python tools/_layer_selftest.py

# 純資料層捕捉目前遭遇
python tools/_catch_layer.py

# 資料層優先的自動迴圈（走路、走近自動轉站、捕捉、錄 ML 資料）
python tools/pgo_run.py --catches 5 --minutes 25 --settle 4
```

當成函式庫：

```python
from pgo_layer import state, mon, catch

if state() == "encounter":
    print(mon())        # {'level': '21', 'iv': '73', 'split': '13/8/12', ...}
    catch()             # 只用資料層判定，回傳 {'caught': True, 'throws': 1, ...}
```

## 9. 下一步（若要多拿補給站狀態）

1. 開 `快速捕捉`：遭遇→地圖之間不再有獎勵卡，狀態機更乾淨（代價：跳過捕捉動畫）。
2. 要精確補給站狀態，只能在「走近後」用一張**局部截圖**判斷站體顏色（藍/紫），
   其餘狀態仍全部由資料層決定 —— 混合式，而非全程截圖。
3. 若要完全免截圖，需 root 或改寫 PGSharp（讀其內部資料），存取層做不到。

## 10. 降低截圖依賴：螢幕探針 + 熱區掃描（2026-11-02）

目標是「以數據讀入進行遊戲」，所以截圖只用來決定**要不要按、按哪裡**，
所有**狀態判定**仍由 accessibility tree 決定。

### 10.1 為什麼需要螢幕探針

補給站照片頁、道館卡、捕捉結果卡都是 Unity 畫的，tree 完全看不到，
`state()` 會誤報 `map`（只有 ~49 個系統列節點）。這會讓機器人對著照片一直亂點。

`driver` 的 `probe` 指令在手機上算三個純量（中心區域）：

| 畫面 | warm = mean(R−B) | satsd | 判定 |
|---|---|---|---|
| 地圖 | −23.7 ～ −27.9 | 22–31 | `overlay=false` |
| 補給站照片頁 | **+0.2** | 41 | `overlay=true` |
| 活動公告 | **+9.6** | 35 | `overlay=true` |

門檻 `WARM_OVERLAY = -12`，在實測畫格上完全分離（差距 >9，兩側都留 9 以上餘裕）。

```python
L.probe()    # {'warm': -26.7, 'sat': 39.3, 'satsd': 25.1, 'lum': 112.4, 'overlay': False}
L.on_map()   # tree 說 map 且 probe 說不是覆蓋畫面，才回 True
```

`pgo_direct.back_to_map()` 已改用它：tree 說 `map` 但 probe 說是覆蓋畫面時，
會按 BACK 關掉照片頁，不會提早回報成功。

### 10.2 互動半徑與比例尺（實測）

- 步行 4 秒、30 km/h = 33.3 m，世界位移 136 px ⇒ **≈4.1 px/m**。
- 交叉驗證：曼哈頓街區間距 ≈293 px ≈ 71 m（真實約 80 m），一致。
- 因此可互動半徑 40 m ≈ **164 px**；畫面看到 ≠ 抓得到，
  超出半徑只會出現「這個寶可補給站太遠了」提示。
- 相機以角色為中心，所以角色附近的 164 px 才是有效熱區。

### 10.3 熱區掃描（`--sweep`）

影像只能「提議」目標，不能作決定。`pgo_hunt.py --sweep` 在熱區做 16 點格點
（半徑 210 px、間距 85 px），每一點都用 tree 驗證：

| 結果 | 動作 |
|---|---|
| `encounter` | **立刻投球捕捉**（`pgo_layer.catch`） |
| `stop_disc` | 記帳、BACK |
| `map` + `probe.overlay` | 開到 Unity 覆蓋畫面（照片頁/道館卡），BACK，記為 `overlay_observation` |
| `map` + 非覆蓋 | 空地，換下一點 |
| `raid` | R5：只按 BACK，絕不按「對戰」 |
| `anr_dialog` | 按「等一下」（絕不按「關閉應用程式」） |

實測（2026-11-02）：

```
tap 585,1340 -> overlay (warm=0.1), BACK
tap 500,1425 -> ENCOUNTER {'level': '10', 'iv': '46', 'split': '7/6/8', 'consistent': True}
   caught=True throws=1 ball=精靈球
tap 670,1340 -> mon_detail
[0] {'tapped': 12, 'caught': 1, 'spun': 2}
```

### 10.4 遭遇政策：看到就投、投完按 OK

使用者指示（2026-11-02）：**只要在 encounter 頁面就直接投球捕捉**；
捕捉完成後**立即按 OK 回地圖**，不要等卡片自己消失。

- `pgo_layer.catch_if_encounter()`：不在遭遇就回 `None`，在遭遇就呼叫 `catch()`。
- `pgo_layer.catch()` 在 `encounter_ended()` 之後呼叫 `dismiss_catch_card()`，
  優先使用 accessibility action 點 OK／確定（不注入 MotionEvent，避免 ANR），
  失敗才退回座標 `(539,1580)`；回傳 `map_back` 表示是否已回到地圖。
- `pgo_hunt.py` 開場就先跑一次這個政策：即使上一輪留下了沒抓的遭遇，也會先抓掉。

實測：

```
already in an encounter -> catching
   caught=True throws=1 ball=精靈球
   mon={'level': '9', 'iv': '75', 'split': '12/13/9',
        'iv_expected': 75, 'consistent': True}
```

### 10.5 全程無 OCR 的證據

遭遇的 L / IV / 三圍 / 莓果列全部是原生 `TextView`：

```
TextView|L||370,440,388,484|E
TextView|9||388,428,413,487|E
TextView|IV||424,440,456,484|E
TextView|75||456,428,506,487|E
TextView|12/13/9||517,433,659,486|E
TextView|蔓莓果||143,214,286,279|E
```

這份**真實 dump** 存成 `tools/verify/fixtures/encounter.txt`，
由 `tools/_encounter_fixture_test.py` 離線重播（不需裝置、不看任何像素）：

```
PASS  parsed 69 nodes from the dump
PASS  state(ns) == encounter
PASS  level read from TextView '9'
PASS  IV read from TextView '75'
PASS  IV split read from TextView (got 12/13/9)
PASS  berry row identifies the encounter
PASS  truncation formula agrees with the shown IV (got 75)
PASS  IV split and IV label are consistent
ALL PASS
```

`tools/pgo_layer.py`、`pgo_hunt.py`、`pgo_direct.py`、`pgo_rules.py` 內
完全沒有 tesseract / easyocr / paddle 等 OCR 依賴。

### 10.6 ANR 處理

大量注入 MotionEvent 會讓遊戲主執行緒超時（`Waited 5003ms for MotionEvent`）。
發生時 tree 會多出 `anr_dialog`，此時**只能**按「等一下」；
按「關閉應用程式」會終止遊戲、破壞授權連線。所有迴圈都已內建此處理，
並把每次點擊間隔放寬到 2 秒以上。

## 11. 加速路線圖（依投資報酬率排序）

### 11.1 先量測，再優化

| 動作 | 延遲 | 說明 |
|---|---|---|
| `ping`（什麼都不做） | **224 ms** | 這就是一次 adb 來回的固定成本 |
| `dump`（全部節點） | 247 ms | 只比 ping 多 23 ms |
| `probe`（截圖＋算） | 317 ms | 只比 ping 多 93 ms |
| `scan`（截圖＋CV） | 307 ms | 只比 ping 多 83 ms |
| `screencap` 全圖 PNG | 852 ms | 對照組 |

結論：**時間幾乎全花在 adb 來回，不在運算**。所以優化的方向是「減少來回次數」，
不是「把演算法寫快」。

### 11.2 已完成：把「點擊→偵測」合併成一次來回

舊流程每次點擊 4 次來回：
`adb tap` 224 + `sleep 2000` + `dump` 247 + `probe` 317 ≈ **2.8 s**

新流程 `driver` 的 `tapwait`：手機自己每 ~100 ms 輪詢節點與像素，
一有變化就停，然後把 texts + warm 一起回傳 ⇒ **1 次來回**。

實測（2026-11-02）：

```
STAR 點擊（有變化）：inner 245 ms / wall 476 ms
空地點擊（無變化）：inner ~900 ms / wall ~1.0 s
10 點掃描整輪：12.0 s（原本約 28 s）⇒ 1.2 s/點
```

`catchseq` 把「投球→等結果→按 OK」也合併成一次來回（動畫時間無法跳過）：
`pgo_layer.catch_seq()`；先前 host 端版本是 6.4 s。

### 11.3 最高槓桿其實是遊戲設定（零程式碼）

`tools/verify/settings.json` 顯示以下**目前是關閉**，而它們直接影響速度：

| 設定 | 目前 | 開啟後效果 |
|---|---|---|
| **擴大遭遇範圍** | Off | 解決「看得到卻點不到」——目前野怪在互動圈內仍常點不動 |
| **快速捕捉** | Off | 略過捕捉動畫，`catchseq` 從 ~3 s 降到 ~1 s |
| **虛擬 Go Plus** | Off | 自動捕捉附近寶可夢，機器人只需走路（使用者需確認可接受） |
| 跳過過場動畫 | Off | 減少切換畫面空等 |

必須維持關閉：`快速狙擊 I/II`（使用者明令）、`Raid & Gym Battle Assistant`、
`極巨化戰鬥輔助`（R5）。

觀察：`toggle` 對「冷卻計時器」等列有效，但對「擴大遭遇範圍」無效
（回報 `OK toggled` 但開關仍 `CEK`），且曾因此誤觸到別列。
這一列需要人工在 UI 開啟，或先查清它的實際控件型別。

### 11.4 迴圈層：不要站著盲掃

實測盲掃 16 點的命中率很低，因為**掃描格距 85 px 比野怪本身還大**。
三個改進方向：

1. 先走動（`30.0 km/h` + 已開的 `快速旋轉`），讓新怪持續進入互動圈，
   再掃描；比站著重掃同一格有效率。
2. 角色畫面位置會隨鏡頭飄移，`AVATAR` 不能寫死；用互動圈圓心定位
   （`tools/_circle.py` 已能從粉紅圈算出圓心與 px/m）。
3. 掃描格距要小於目標尺寸（野怪約 40–60 px），或改用更好的偵測器。

### 11.6 為什麼那四個設定「開了也沒用」

實測（2026-11-02，設定頁開著）：

| 設定 | `toggle`（ACTION_CLICK） | 直接點開關 | 點整列 | 結果 |
|---|---|---|---|---|
| 禮品助理 | ✅ 立即生效 | — | — | 可切換 |
| 冷卻計時器 | ✅ 立即生效 | — | — | 可切換 |
| 快速捕捉 | ❌ 回報 OK 但沒變 | ❌ | ❌ | **鎖住** |
| 跳過過場動畫 | ❌ | ❌ | ❌ | **鎖住** |
| 擴大遭遇範圍 | ❌ | ❌ | ❌ | **鎖住** |
| 虛擬 Go Plus | ❌ | ❌ | ❌ | **鎖住** |

不是座標或注入問題：同一時間、同一面板，「禮品助理」用同一個
`ACTION_CLICK` 一按就切換成功。這些列在畫面上也是**灰色**的。

也就是說它們是 PGSharp 的功能授權閘，不是一個 config 值。
依 REA 報告 §（`REA_PGSHARP_COMPLETE_REPORTS.md`）：

- 授權與指令通道**全部在加密的 Lua payload 內**，靜態不可見；
- payload 用 AES 加密，key 在 runtime 生成或由 license 推導；
- 沒有明文的 license server / C2 endpoint。

所以「把權限改成可開」不是改一個設定檔就能做到，而是要繞過授權閘，
這會同時違反我們自己定的「不得破壞授權／連線」，也有帳號風險。**不做。**

### 11.7 程式層的替代方案：自己實作自動捕捉

既然那四個設定不能開，就在我們自己的程式裡做出同樣的能力
（`tools/pgo_autocatch.py`）：

1. 用虛擬搖桿持續走動 → 新怪自然進入捕捉範圍（取代「擴大遭遇範圍」）
2. 角色周圍細格掃描（每點一次 adb 來回，資料層驗證）
3. 一遇遭即投球，120 ms 甩球，只用精靈球（R1）
4. 投球→等結果→按 OK 併成一次來回（取代「快速捕捉」的部分效益）
5. 走動與掃描交替 → 取代「虛擬 Go Plus」的「只需走路」體驗

R2（不餵任何莓果）、R5（絕不進團體戰）在這個迴圈裡同樣是硬性拒絕。

### 11.8 2026-11-02 卡關：Unity 輸入被 ANR 弄死

自動捕捉迴圈跑 4 分鐘（9 輪巡邏、9 次走動）**0 捕捉**。追查後發現不是迴圈邏輯問題：

```
地圖上點野怪 / 點補給站 -> 一律 map（沒有任何反應）
點 PGSharp 星號        -> pg_side_menu（正常）
再點一次關閉           -> map（正常）
```

也就是：**原生 Android 視圖照常吃輸入，Unity 地圖層完全不吃**。
時間點正好在多次 `Waited 5003ms for MotionEvent` ANR 之後。

結論：遊戲的 Unity 輸入執行緒被連續注入卡死。
這不是程式能修的，需要重啟遊戲（而且必須經 PGSharp 啟動才保留注入）。
因此：
- 不要再用短間隔連續注入；每次點擊間隔 ≥ 1 s，一輪掃描點數要少。
- 出現 `anr_dialog` 只按「等一下」，並立刻暫停 3–5 s 讓主執行緒追上。

### 11.9 鏡頭漂移與互動圈（實測）

- 角色在畫面上的位置**不固定**：同一地點曾量到 (535,1315)，走動後變成 (150,1790)。
  任何寫死 `AVATAR` 的掃描都會整片落空。
- 畫面上那個洋紅色大圓**以角色為圓心**（示例：圓心 (475,1195)、半徑 235 px ≈ 57 m），
  可以用來同時取得「角色位置」與「比例尺」，但**不代表捕捉範圍**：
  圈內的野怪照樣點不動（已用圈內兩點實測確認）——在 Unity 輸入正常時也一樣。
- 因此正確做法是「先讓鏡頭穩定（走動後等 3 s）→ 量測角色位置 → 才掃描」，
  而不是假設座標。

相關工具：`tools/_avatar.py`（紅帽定位，尚未穩定）、
`tools/_circle.py`（洋紅圈擬合）、`tools/pgo_walk.py`（走向目標，實測 30 m→33.9 m）。

### 11.10 架構層：把整個迴圈搬進手機

終極做法是讓 `driver` 自己跑「掃描→點擊→判斷→記錄」的完整迴圈，
主機只用一次 adb 呼叫下命令、事後拉 log。
這樣每次動作的 224 ms 固定成本會完全消失，理論上還能再快 2–3 倍。
代價是遊戲邏輯要改寫成 Java，屬於較大的重構。
