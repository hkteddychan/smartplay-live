# SmartPLAY Live × ESP32-CYD

**放場通知器** —— 夜晚場次一有新餘額，就 beep 一聲 + 螢幕顯示詳情。
板子自己上網，唔使 PC、唔使手機開住 app。

原始需求同 sketch：`https://hkteddychan.github.io/smartplay-live/esp32/BUILD_HANDOFF.md`
（generic DevKit 版 v2.1；呢個係 CYD 專用版本 —— 螢幕 + 板載喇叭自己處理）

---

## 快速開始

```bash
# 1. 生成中文字型（由 live feed 抽出真實用到的字，~10 KB）
python tools/make-venue-font.py

# 2. 編譯
python -m platformio run -d firmware/esp32_smartplay

# 3. 燒錄（埠號會變；scripts 已經自動偵測，呢度用 PlatformIO 就手動指定）
python -m platformio run -d firmware/esp32_smartplay -t upload --upload-port COM8

# 4. 看 log
python esp32_monitor.py        # 自動搵埠號
```

---

## 兩條路收到放場通知（邊條都行，唔會重複）

| | 做法 | 延遲 | 依賴 |
| :-- | :-- | :-- | :-- |
| **PUSH** | 板子**主動出連** VM（打穿 NAT，唔使 port forward），VM 一見到 feed 有更新即刻推落嚟 | ≈ 0 秒（feed 一更新就響） | VM 要行 daemon + Security Group 開 9000 |
| **POLL** | 板子自己 HTTPS GET `changes-eve.json`，**每 1 分鐘**一次 | ≤ 1 分鐘 | 淨係要 WiFi |

兩條路同時行、去重（16 個 key 嘅 ring buffer），所以**同一個放場事件只會響一次**。
VM 唔喺度／推送斷咗 → 自動退返 poll，唔會漏報。

> 真正嘅延遲瓶頸係**上游 LCSD 鏡像每 15 分鐘一次**，唔係板子。PUSH 慳嗰 1 分鐘。

---

## Push 協定（行式，方便 debug）

```
板子 → VM : "CYD PUSH 1\r\n"
VM    → 板子: "OK\r\n"
VM    → 板子: "RELEASE {json}\r\n"
```

`RELEASE` 一行一個 JSON：

```json
{"sport":"羽毛球","district":"九龍城區","venue":"香港單車館","facility":"主場",
 "date":"2026-11-05","start":1080,"end":1140,"old":1,"new":3}
```

板子收到就：beep 一聲 + 跳去警報卡 + RGB LED 綠閃 + 記數。

### VM 端部署

`tools/cyd_relay.py` 已經加咗 push 功能（**同一個 port 9000**，用唔同 greeting 分流：
`CYD RELAY 1` = SOCKS 管道、`CYD PUSH 1` = 推送通道），所以淨係一個 service、唔使加 port。

```bash
# AWS VM 上
scp tools/cyd_relay.py ubuntu@13.236.188.205:/opt/cyd/
ssh ubuntu@13.236.188.205
sudo systemctl stop cyd-relay
sudo python3 /opt/cyd/cyd_relay.py --pool 9000 --front 1080 --bind 127.0.0.1 --watch 30 -v
```

要改 systemd 就用 `tools/cyd_relay.service`（加 `--watch 30`）。

**Oracle Cloud Security Group 要開 TCP 9000**（來源限你屋企 IP）。
而家 `13.236.188.205:9000` 由外面連唔到（Security Group 未開），所以板子 log 會見到
`[push] dial ... FAIL` —— poll 照樣正常運作。

### 本機測試（唔使 VM）

```bash
python tools/cyd_push_test.py
```

會起一個假 feed + 起 daemon + 扮板子連線，睇到 `RELEASE` 行到達為止。

---

## 硬體（ESP32-2432S028R / CYD）

| | |
| :-- | :-- |
| 螢幕 | ILI9341 240×320，`ILI9341_2_DRIVER` + rotation 1 → 320×240 橫向 |
| 顯示 SPI | MISO 12 / MOSI 13 / SCLK 14 / CS 15 / DC 2 / BL 21（HSPI） |
| 觸控 | XPT2046 獨立 VSPI：CS 33 / IRQ 36 / CLK 25 / MOSI 32 / MISO 39 |
| 喇叭 | 板載擴大機 → **GPIO26**，`SPEAK` 2Pin Molex PicoBlade（喇叭係選配） |
| RGB LED | 4 / 16 / 17，低電位觸發（放場時綠色閃） |
| 記憶體 | 4 MB flash / 無 PSRAM / app 分區 3 MB（`huge_app.csv`） |

### 喇叭接腳（2026-11-04 實測釐清）

社群 pin map 講「IO26 接擴大機」，但同時叫人用 `i2s_set_dac_mode()`。答案喺
Arduino core 3.x 內置嘅 legacy `driver/i2s_types_legacy.h`：

```c
I2S_DAC_CHANNEL_RIGHT_EN = 1,  // DAC channel 0 -> GPIO25
I2S_DAC_CHANNEL_LEFT_EN  = 2,  // DAC channel 1 -> GPIO26  ← 擴大機喺呢度
```

即係話 I2S 內置 DAC 模式嗰兩個輸出係 **GPIO25 / GPIO26**。CYD 用
`I2S_DAC_CHANNEL_LEFT_EN` → GPIO26，同 pin map 完全對得上。GPIO25 係另一個 DAC 通道，
同時又係觸控時脈，所以唔用。

> ⚠️ 要用 legacy `driver/i2s.h`（已 deprecated 但仲喺 3.3.12 入面）。新 API
> `driver/i2s_std.h` **冇** DAC 模式，唔支援呢個玩法。

---

## 網絡

| | |
| :-- | :-- |
| Feed | `https://hkteddychan.github.io/smartplay-live/esp32/` |
| changes-eve.json | <1 KB，放場通知用（淨係晚上 ≥18:00 + 淨係可預訂日） |
| index.json | manifest（每個 sport 有幾多行 + 7d 檔名） |
| today.json | 28–36 KB —— **板子唔再拉**，淨係 VM 用嚟查 venue→district |
| TLS | `WiFiClientSecure::setInsecure()` |
| 憑證 | `platformio.ini` build flags 燒入 flash |

## 行為

| 事件 | 動作 |
| :-- | :-- |
| 開機 | 拉一次 changes-eve.json（**第一輪 = baseline，唔 beep**）+ 嘗試連 push |
| 每 1 分鐘 | 拉 changes-eve.json，`"g"` 版本冇變就靜靜哋算 |
| push 收到 `RELEASE` | **beep 一聲** + 跳去警報畫面 + RGB LED 綠閃 3 下 |
| 放場判定 | `(kind=="chg" && new>old)` 或 `kind=="new"`；被訂走／消失**唔 beep** |
| push 收到同一事件 | 去重，唔會響第二次 |
| 按一下畫面 | 關閉警報畫面，返主畫面 |
| 120 秒冇人理 | 自動返主畫面 |

## 畫面

**主畫面（等待放場）**

```
┌──────────────────────────────────────┐
│ 放場通知器              ● push 19:23  │
├──────────────────────────────────────┤
│                                      │
│             等待放場中                 │
│     晚上 6 點後 · 餘額增加或新時段        │
│                                      │
│  last poll          19:23:04          │
│  next poll          00:42             │
│  feed               2026-11-04 08:03  │
│  releases           3                 │
├──────────────────────────────────────┤
│ push 未連線                  poll 失敗  │
└──────────────────────────────────────┘
```

**警報畫面**

```
┌──────────────────────────────────────┐
│ 放場 AVAILABLE 19:23  │  ← 綠色橫幅
├──────────────────────────────────────┤
│ ▌羽毛球 · 九龍城區          1 → 3 場  │
│ ▌18:00-19:00 · 主場                   │
│ ▌香港單車館                            │
└──────────────────────────────────────┘
   按一下畫面關閉              共 1 個新時段
```

## 中文字型

`tools/make-venue-font.py` 會拉真實 feed，抽出所有可能出現嘅場地名 / 區名 /
UI 字，出一份 16×16 1-bit subset（而家 323 字，10 KB）。

| | 聊天玩具 | 呢個 project |
| :-- | :-- | :-- |
| 字數 | 5,905 | 323 |
| flash | 196 KB | 10 KB |

ASCII 用 TFT_eSPI font 2（16 px 高、3–9 px 闊），CJK 用 bitmap，兩者同一 baseline。

## Serial 指令（115200）

| 指令 | 作用 |
| :-- | :-- |
| `b` | 即刻 beep 一次（試聲） |
| `p` | 逐條試聲：880 Hz = I2S DAC 左（GPIO26，擴大機）、1174 Hz = DAC 右（GPIO25）、1567 Hz = PWM（GPIO26） |
| `r` | 即刻重拉 feed |
| `a` | 跳去警報畫面（睇效果） |
| `h` | 返主畫面 |
| `l` | serial 印出開機至今收到嘅放場 |
| `v` | 印 venue→district 對照表狀態 |

## 已知限制 / 下一步

- **冇插喇叭就冇聲**：板載擴大機要 `SPEAK` 插座有喇叭先會出聲。警報畫面同
  RGB LED 燈照樣 work。
- push 要 VM 上面行 daemon + Security Group 開 9000（而家未通，所以板子行緊
  1 分鐘 poll 嘅後備路徑）。
- changes-eve.json 冇 district → 區名由 VM 查 venue→district 補上（用
  today.json + 7 日檔，用 index.json manifest 搵檔名）。
- 未做 OTA（`huge_app.csv` 冇 OTA 分區）。
- 冇 NTP 就冇時鐘；有 NTP（`configTime` → HKT）。

## 檔案

| 檔案 | 用途 |
| :-- | :-- |
| `smartplay.ino` | 主程式：WiFi / push client / poll / 兩個畫面 |
| `cyd_text.h` | UTF-8 + CJK 繪製、量度、截斷 |
| `cyd_audio.h` | beep 驅動（I2S DAC / PWM，音量刻意細 + 淡入淡出） |
| `venue_font.h` | 自動生成嘅 CJK subset（唔好手改） |
| `tools/make-venue-font.py` | 字型生成器 |
| `tools/cyd_relay.py` | VM 端：SOCKS reverse relay **+ 放場推送** |
| `tools/cyd_push_test.py` | 本機 end-to-end 測試（假 feed + 假板子） |
