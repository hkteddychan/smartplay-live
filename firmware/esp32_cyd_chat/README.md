# AI Math Tutor — ESP32-CYD 觸控聊天玩具

把 **ESP32-2432S028R（CYD，2.8" 320×240 TFT + XPT2046 觸控）** 變成一台
「高智能方程式對答」掌上機：五個難度關卡、螢幕鍵盤、聊天氣泡、離線記憶。

架構參考並改寫自 [kano92-dir/CYD-AI-CHAT](https://github.com/kano92-dir/CYD-AI-CHAT)（MIT）。

---

## 五個測試關卡（下方快捷列）

| 按鈕 | 測什麼 | 題目 |
| :--- | :--- | :--- |
| **ALG** | 代數化簡 | 化簡 `(3x^2 - 12x + 9) / (x - 3)` 並說明 x 的限制 |
| **CALC** | 微積分 | `f(x) = x^2 sin(x)` 的導函數與 `x = π` 的斜率 |
| **PHYS** | 物理建模 | 5 公斤從 20 公尺落下，求落地速度（g = 9.8） |
| **OPT** | 最優化 | 表面積 100 cm² 的密閉盒子，體積最大時的尺寸 |
| **PROOF** | 邏輯證明 | 為什麼勾股定理一定要直角？用餘弦定理解釋 |

---

## 硬體

| 項目 | 值 |
| :--- | :--- |
| 板子 | ESP32-2432S028R（CYD） |
| 螢幕 | ILI9341 240×320，旋轉 1 → 320×240 |
| 觸控 | XPT2046，**獨立 SPI**：CLK 25 / MISO 39 / MOSI 32 / CS 33 / IRQ 36 |
| 背光 | GPIO 21（可調亮度） |
| RGB LED | R 4 / G 16 / B 17（低電位亮） |
| 喇叭 | GPIO 26（本版未使用） |

> **重點**：CYD 的觸控不在螢幕那條 SPI 上，所以程式用 `SPIClass touchSPI(VSPI)`
> 獨立開一條匯流排。這是 CYD 上最穩定的做法。

---

## 燒錄

```bash
cd firmware/esp32_cyd_chat
python -m platformio run -t upload --upload-port COM7
python -m platformio device monitor --port COM7
```

本機已驗證：`[BOOT] screen 320 x 240 (rot 1)`，Flash 65.7%、RAM 15.4%。

---

## 兩種模式

### DEMO（預設，免金鑰）
`platformio.ini` 的 `CHAT_API_KEY` 留空即可。五個關卡會回傳內建標準答案，
其餘問題顯示提示。**現在就能玩。**

### 真 AI（OpenRouter 免費模型）
1. 到 <https://openrouter.ai/keys> 申請金鑰（`sk-or-v1-...`）
2. 編輯 `platformio.ini`：

```ini
-D CHAT_API_KEY='"sk-or-v1-你的金鑰"'
```

3. 重新 `pio run -t upload`

模型清單與自動降級（429 會換下一個）：

```
google/gemma-4-31b-it:free
openai/gpt-oss-120b:free
openai/gpt-oss-20b:free
moonshotai/kimi-k2.6:free
qwen/qwen3-coder:free
```

---

## 操作

| 動作 | 結果 |
| :--- | :--- |
| 開機 | 掃描 WiFi → 點網路 → 螢幕鍵盤輸入密碼 → OK |
| WiFi 頁「Demo」 | 不連網直接進聊天（離線 DEMO） |
| 點下方 5 顆按鈕 | 直接送出該關卡題目 |
| 點輸入列「Write」 | 開螢幕鍵盤（`123` 切數學符號層 `+-*/=<>^_`） |
| 長按 `<-` | 連續刪除 |
| 聊天區上下拖曳 | 捲動歷史 |
| 標題列 `+` | 清空對話 |
| 標題列 `≡` | 設定（WiFi / 模型 / 角色 / 亮度 / 清除） |
| RGB LED | 藍=思考中、綠=成功、紅=錯誤 |
| 喇叭 | 送出=上升兩音、回覆=高音兩音、錯誤=低鳴 |

### 序列埠指令（接電腦時）

```bash
python -m platformio device monitor --port COM7
```

| 輸入 | 作用 |
| :--- | :--- |
| `demo` | 跳到聊天畫面（不用觸控） |
| 任何文字 + Enter | 直接當問題送出 |

問答也會同步印在序列埠：`[YOU] ...` / `[AI] ...` / `[ERR] ...`。

角色（Persona）：`Tutor`（逐步教學）、`Short`（只給答案）、
`Exam`（考試速解）、`Proof`（證明與條件）。

對話會存進 NVS，重開機後自動接續。

---

## 中文顯示（已支援）

內建 **5,905 個 16×16 點陣中文字**（Big5 常用字 + 符號），約 196 KB，放在 flash：

- 產生器：`python tools/make-cjk-font.py`
- 覆蓋檢查：`python tools/check-cjk-coverage.py`
- 字型預覽：`docs/cjk-chat-preview.png`、`docs/font-compare.png`

AI 被要求用**繁體中文**回答、數學式用純 ASCII（不要 LaTeX）。ASCII 走 TFT_eSPI
font 2，中文走點陣字型，兩者混排會自動換行。

## 已知限制 / 下一步

1. **輸入**：螢幕鍵盤只有 ASCII，中文只能由 AI 產生（或用序列埠送 UTF-8）。
2. **字集**：目前 Big5 常用字（level 1）。若要更罕見的字，改 `tools/make-cjk-font.py`
   的範圍到 `0xA1–0xF9`（約 13,000 字，+416 KB）。
3. **觸控校正**：若點擊位置偏移，調整 `TOUCH_MIN_X/MAX_X/MIN_Y/MAX_Y`。
4. **面板變體**：白畫面或顏色相反時，把 `TFT_INVERT` 設 1，或改用 `ST7789_DRIVER`。
5. 語音輸入、OTA 尚未實作。
