# ESP32 CYD — 完整功能介紹

> 對應機器可讀版本：`docs/esp32-manifest.json`（任何軟件都可以 load）
> 更新日期：2026-11-04

---

## 一、硬件總覽

**板子：ESP32-2432S028R（暱稱 CYD / Cheap Yellow Display）**

| 項目 | 內容 |
| :-- | :-- |
| 主控 | ESP32-WROOM-32（傳統版，Xtensa LX6 雙核 240 MHz） |
| Flash | 4 MB |
| PSRAM | **無** ← 影響所有記憶體設計 |
| SRAM / ROM | 520 KB / 448 KB |
| USB 序列埠 | CH340（`USB\VID_1A86&PID_7523`）→ COM 號由 Windows 分配（見過 COM7、COM8） |
| 工具鏈 | Arduino core 3.3.12 / PlatformIO 6.2.0 / espressif32 8.0.0 / Python 3.13.5 |

### 外設一覽

| 外設 | 狀態 | 詳情 |
| :-- | :-- | :-- |
| **螢幕** | ✅ | 2.8" ILI9341，240×320 → **橫向 320×240**（rotation 1），TFT_eSPI 2.5.43，HSPI：MISO 12 / MOSI 13 / SCLK 14 / CS 15 / DC 2 / BL 21 |
| **觸控** | ✅ | XPT2046 電阻觸控，**獨立 VSPI**：CLK 25 / MISO 39 / MOSI 32 / CS 33 / IRQ 36（校準 200–3900） |
| **RGB LED** | ✅ | R 4 / G 16 / B 17，低電位觸發 |
| **喇叭** | ⚠️ | 板載擴大機 → **GPIO26**，但**喇叭係選配**，冇插就冇聲 |
| **SD 卡** | ✅（未用） | CS 5，VSPI：SCK 18 / MISO 19 / MOSI 23（與觸控共用匯流排） |
| **光敏電阻** | ✅（部分版本） | GPIO 34 |
| **按鍵** | ✅ | BOOT = GPIO 0（`INPUT_PULLUP`，LOW=按下）、EN/Reset |
| **麥克風** | ❌ | **板上一個都冇** —— 語音輸入要外接 INMP441 I2S 麥克風 |

### 喇叭接腳（2026-11-04 釐清，之前一直有矛盾）

社群 pin map 講「IO26 接擴大機」，但同一個 community example 又叫人用
`i2s_set_dac_mode()`。答案藏喺 Arduino core 入面 legacy 嘅
`driver/i2s_types_legacy.h`：

```c
I2S_DAC_CHANNEL_RIGHT_EN = 1,  // DAC channel 0 -> GPIO25
I2S_DAC_CHANNEL_LEFT_EN  = 2,  // DAC channel 1 -> GPIO26  ← 擴大機喺呢度
```

即係話：**I2S 內置 DAC 模式嘅兩個輸出係 GPIO25 / GPIO26**（唔係一般文獻講嘅
DAC1=25 / DAC2=27）。CYD 用 `I2S_DAC_CHANNEL_LEFT_EN` → GPIO26，同 pin map 完全
對得上。GPIO25 係另一個 DAC 通道，同時又係觸控時脈，所以唔用。

> 必須用 legacy `driver/i2s.h`（已 deprecated，但 core 3.3.12 仲有）。新 API
> `driver/i2s_std.h` **完全冇** DAC 模式。

喇叭插座：**P4**，2Pin 1.25mm Molex PicoBlade，背面印「SPEAK」。

### 空閒 GPIO（想做嘢時用呢啲）

`1, 3, 6, 7, 8, 9, 10, 11, 22, 27, 35, 38`
（GPIO 35 / 38 只可以做輸入、冇內部上拉；22 同 27 有引出到 Molex 座）

---

## 二、而家板上燒住嘅韌體：SmartPLAY Live 放場通知器 v3.0

**位置**：`firmware/esp32_smartplay/`　**狀態**：✅ **正燒住喺板上**

一句話：**夜晚場次一有新餘額，就 beep 一聲 + 螢幕顯示詳情。淨係做呢一件事。**

```
ESP32 ──WiFi/TLS──> hkteddychan.github.io/smartplay-live/esp32/
   │                   └─ changes-eve.json  每 1 分鐘  → 放場偵測（後備）
   │
   └─ 主動出連 VM:9000 ──► VM 一見 feed 有更新即刻推落嚟（≈ 0 秒）
```

### 兩條路，去重，唔會響兩聲

| 路徑 | 做法 | 延遲 | 依賴 |
| :-- | :-- | :-- | :-- |
| **PUSH** | 板子主動出連 VM（打穿 NAT，唔使 port forward），VM 即刻推 | ≈ 0 秒 | VM 行 daemon + SG 開 9000 |
| **POLL** | 自己 HTTPS GET，每 **60 秒** | ≤ 1 分鐘 | 淨係要 WiFi |

同一個事件兩邊都見到 → 16 個 key 嘅 ring buffer 去重 → **只響一次**。
VM 唔喺度就自動退返 poll，唔會漏報。

### 已實測通過

| 項目 | 結果 |
| :-- | :-- |
| 開機 / WiFi | `REDACTED` → 192.168.31.34，RSSI −46…−48 dBm |
| 首輪唔誤嗶 | `[eve] first run - baseline only` ✅ |
| PUSH 協定 | 本機 end-to-end 測試通過（`tools/cyd_push_test.py`）：握手 → 版本變 → `RELEASE` 行到達，場地 + 區名都啱 ✅ |
| POLL 路徑 | ✅ |
| beep 路徑 | `AUDIO_PATH_AMP`（I2S DAC 左聲道 → GPIO26） |
| beep 有冇聲 | **❓要人耳確認** |

### 放場判定

- 🔔 ** beep**：`kind == "chg" && new > old`（餘額增加）或 `kind == "new"`（新時段）
- 🔇 **唔 beep**：`kind == "gone"`（消失）、`chg` 而 `new < old`（畀人訂走）

### 顯示

主畫面（等待放場）：上次檢查 / 下次檢查 / feed 版本 / 開機至今收到幾多個 / push 連線狀態
警報畫面：運動 · 區 · 場地 · 時間 · 設施 · 舊→新場數，綠色橫幅 + RGB LED 綠閃

**區名由 VM 補上** —— `today.json` 只包含「而家仲有位」嘅場地，啱啱放出嚟嘅新場地
未必喺入面，所以 VM 用新嘅 `index.json` manifest 搵 7 日檔一齊掃，覆蓋率先夠。
板子本身唔使再拉 28–36 KB 嘅 session feed。

### ⚠️ 仲差 VM 嗰邊

`13.236.188.205:9000` 而家由外面連唔到（Oracle Cloud Security Group 未開 9000），
所以板子 log 會見到 `[push] dial ... FAIL`，行緊 1 分鐘 poll 嘅後備路徑（正常運作）。

要開 push：

```bash
# Oracle Cloud Security Group 加 inbound TCP 9000（來源限你屋企 IP）
# VM 上
scp tools/cyd_relay.py ubuntu@13.236.188.205:/opt/cyd/
ssh ubuntu@13.236.188.205 'sudo systemctl stop cyd-relay && \
  sudo python3 /opt/cyd/cyd_relay.py --pool 9000 --front 1080 --bind 127.0.0.1 --watch 30 -v'
```

`cyd_relay.py` 而家一個 port 兩用：`CYD RELAY 1` = SOCKS 管道、`CYD PUSH 1` = 推送通道。

### 已知限制

- **冇插喇叭就靜音**（但畫面 + LED 一樣 work）
- 真正嘅延遲瓶頸係**上游 LCSD 鏡像每 15 分鐘一次**，唔係板子。PUSH 慳嗰 1 分鐘。
- 未做 OTA（`huge_app.csv` → 冇 OTA 分區）

---

## 三、倉庫裡面另外三個韌體（隨時可以燒返）

### A. `esp32_socks5_proxy` — SOCKS5 代理 + 反向隧道

用住宅 IP 出外網；同時板子主動出連 VM，所以 VM 唔使 port forwarding 就連到屋企。

- SOCKS5 + RFC 1929 用戶名/密碼認證（slot=4），port 1080，4 個並發 session
- **反向 relay**：板子每 5 秒主動連 VM :9000，握手 `CYD RELAY 1`
- 硬化：pipeline 殘留處理、per-ATYP 長度檢查、120 s idle timeout、WiFi 重連後
  重新 `server.begin()`、`WiFi.setSleep(false)`
- LED：綠=準備好、藍閃=使用中、紅=冇 WiFi
- **實測**：`0502` greeting → `0100` auth → `05 00 00 01` CONNECT → HTTP 200；
  錯密碼 `0101` 拒絕；curl HTTP 200 (0.27 s) / HTTPS 200 (0.36 s)

### B. `esp32_cyd_chat` — AI 數學家教（觸控聊天玩具）

- 狀態機：WiFi 清單 → 鍵盤 → 連線中 → 聊天 → 設定 → 模型
- 分層螢幕鍵盤（大小寫／符號層 `+-*/=<>^_`）、氣泡式對話、自動換行、拖曳捲動
- NVS 記憶（namespace `cydmath`）：最後 10 句對話，重開機仍在（上限 ~3900 B）
- OpenRouter 免費模型，429 自動 fallback，401 即停；`max_tokens=320`，帶最近 6 句
- 角色：Tutor / Short / Exam / Proof；RGB LED 狀態、`tone()` 提示音
- CJK 字型：Big5 Level 1 + 符號，**5,905 字 / 196 KB**
- 冇 API key 都玩得（demo mode）
- 容量：1.50 MB / 1.9 MB（76.2%），RAM 15.4%

### C. `esp32_cyd_controller` — NEON SERPENT 3D 無線控制器

- WebSocket **伺服器** port 8787，遊戲頁做 client
- 觸控方向盤（FWD/BACK/LT/RT、Y+/Y−、PAUSE、AUTO）＋ BOOT 快捷鍵
- 開機 splash（RLE）＋「HELLO TEDDY!」橫幅＋ GPIO 26 問候旋律
- RGB LED：藍慢閃=設定中、恆亮=已連線
- WiFi captive portal（AP `NEON-SERPENT-CYD` / `serpent3d` / 192.168.4.1），
  憑證存 NVS，長按 BOOT 3 秒可重設
- 協定：板→遊戲 `join/autopilot/command/pause/resume`；遊戲→板 `hello/state/response`

---

## 四、主機端工具

| 檔案 | 用途 |
| :-- | :-- |
| `esp32_port.py` | **自動搵 CH340 埠號**（PnP id 對唔對就唔開）；優先序：明文參數 > `ESP32_PORT` 環境變數 > 自動偵測 |
| `test/test_esp32_port.py` | pytest：12 個測試（邏輯 + 真機），0.35 s 跑完 |
| `esp32_probe.py` | reset pulse + 捉 ROM banner |
| `esp32_monitor.py` | 序列埠 monitor（自動 reset） |
| `esp32_socks_watch.py` | 捉 SOCKS 開機 log + WiFi/IP |
| `esp32_socks_log.py` | 唔 reset 咁讀 log + 打一個 SOCKS request |
| `esp32_watch_raw.py` | 長時間 raw 監看 |
| `esp32_chat_test.py` / `esp32_cjk_test.py` | 聊天／中文渲染自動測試 |
| `tools/test-socks5.py` | SOCKS5 協定測試（greeting/auth/connect/HTTP/錯密碼） |
| `tools/cyd_relay.py` | VM 側反向 relay（pool :9000 / front :1080） |
| `tools/make-cjk-font.py` | 5,905 字完整 CJK 字型 |
| `tools/make-venue-font.py` | 由 feed 抽字出 316 字 subset |
| `tools/check-cjk-coverage.py` | 檢查用咗嘅字有冇蓋到 |

Node 測試：`test/esp32-deep-test.mjs`、`test/esp32-device-simulator.mjs`、
`test/cdp-driver.mjs`、`test/syntax-check.mjs`

---

## 五、呢塊板做得到 / 做唔到嘅嘢

### 板子自己就搞得掂（完全獨立，唔使 PC）

WiFi STA + TLS client、JSON 解析、320×240 觸控圖形介面、電阻觸控輸入、RGB LED、
經板載擴大機出聲、NVS 儲存、NTP 校時。

### 要加硬件

| 想做 | 需要 |
| :-- | :-- |
| 語音**輸入** | INMP441 I2S 麥克風（3 個空 GPIO） |
| 板端喚醒詞 | ESP32-S3（ESP-SR 要向量指令） |
| 好啲嘅 TTS 音色 | MAX98357A I2S 擴大機（板載係 analog，較悶） |

### 呢塊板做唔到

- 板端 ASR（Whisper 級要 ~100 MB + 向量指令）
- 板端高質素 TTS
- 傳統 ESP32 上嘅真·免喚醒（冇 S3 就冇 ESP-SR）
- 用現有分區表做 OTA

---

## 六、語音互動路線（已同你傾過嘅方案）

**建議：Mode A — 觸控按壓說話，PC（或雲端）做大腦**

理由：反向 relay 已經提供咗「板子主動出連」嘅音訊上／下行通道；ESP32 只需要做
I2S 收音、PCM 傳輸、畫面 UI 同播放，腦交俾 PC（已經接好 OpenRouter）。

| 階段 | 內容 | 需新硬件 |
| :-- | :-- | :-- |
| 0 | 安靜音訊探測（`p` 指令）—— 確認到底有冇喇叭 | — |
| 1 | TTS 回放：PC 傳 PCM → 板子播放 + 顯示文字 | — |
| 2 | 加 INMP441 → 串流到 PC → whisper → 字幕上屏 | INMP441 |
| 3 | 完整迴圈 + 喚醒詞（喺 PC 跑） | INMP441 |

其他模式：**B** 免喚醒（喚醒詞放 PC，麥克風常駐）｜**C** 板端喚醒詞（要 S3）｜
**D** 只有語音輸出（唔使麥克風，最快見效）｜**E** 完全獨立唔靠 PC（板子直接叫
雲端 STT/TTS）

---

## 七、注意事項

- `pio` 唔喺 PATH —— 用 `python -m platformio`
- 開 CH340 埠時如果 DTR/RTS 被拉低，ESP32 會即刻 reset（工具腳本係故意 pulse RTS）
- 呢部機嘅 COM3–COM6 係**藍牙虛擬埠**（decoy），永遠唔可以揀
- 板子 IP 由 DHCP 派，會變 ——睇返 serial log
- 呢部機上 COM7 已經俾咗其他裝置，所以當時啲腳本寫死 COM7 好危險（會寫入
  唔相干嘅裝置），而家已經改成自動偵測
- AWS VM 要經住宅 IP 出外網時，要燒返 `esp32_socks5_proxy`
