# NEON SERPENT 3D — ESP32 240×320 開發板無線控制器

把 **ESP32-2432S028R（CYD，2.8 吋 ILI9341 240×320 + XPT2046 觸控）** 變成 NEON SERPENT 3D 的實體控制器：

- 開機先「打招呼」：TFT 顯示**圖片**（`assets/hello.png` 或 `preview.png`）+ **HELLO TEDDY!** 橫幅 + 背面喇叭播放**問候曲**（GPIO 26 板載擴大機）
- **Wi-Fi 設定入口**：SSID／密碼存在 NVS，沒設定或連不上時自動開啟熱點設定頁
- 內建 **WebSocket server（port 8787）**：遊戲頁主動連入，板子即時顯示戰況
- **觸控方向鍵**：FWD／BACK／LT／RT 平面移動、Y+／Y- 升降、PAUSE 暫停、AUTO 自動駕駛
- **BOOT 按鍵**：短按 = 暫停／恢復；長按 3 秒 = 清除 Wi-Fi 設定重來
- 藍色 LED（GPIO2）：設定模式慢閃、遊戲連結後常亮

## 資料夾結構

```
firmware/esp32_cyd_controller/
├── esp32_cyd_controller.ino   # 韌體主程式
├── splash_data.h              # 開機圖片（240×320 RGB565 RLE，自動產生）
├── platformio.ini             # PlatformIO 設定（含 CYD 接腳）
└── README.md
tools/make-splash.mjs          # preview.png -> splash_data.h 轉檔工具
```

## 燒錄方式

### PlatformIO（建議）

```bash
cd firmware/esp32_cyd_controller
pio run -t upload          # 編譯並燒錄
pio device monitor         # 序列監看（115200）
```

Wi-Fi 可直接寫在 `platformio.ini` 的 `NEON_WIFI_SSID` / `NEON_WIFI_PASS`，或留空用下面的設定入口。

### Arduino IDE

1. 安裝程式庫：**TFT_eSPI**、**WebSockets**（by Markus Sattler）、**ArduinoJson**（7.x）
2. 編輯 `Arduino/libraries/TFT_eSPI/User_Setup.h`（或用 `USER_SETUP_LOADED` 方式），內容：

```c
#define USER_SETUP_LOADED 1
#define ILI9341_2_DRIVER
#define TFT_WIDTH  240
#define TFT_HEIGHT 320
#define TFT_MISO   12
#define TFT_MOSI   13
#define TFT_SCLK   14
#define TFT_CS     15
#define TFT_DC      2
#define TFT_RST    -1
#define TFT_BL     21
#define TFT_BACKLIGHT_ON HIGH
#define TOUCH_CS   33
#define SPI_FREQUENCY  55000000
#define SPI_READ_FREQUENCY  20000000
#define SPI_TOUCH_FREQUENCY  2500000
#define LOAD_GLCD
#define LOAD_FONT2
#define LOAD_FONT4
#define LOAD_FONT7
```

3. 開啟 `esp32_cyd_controller.ino`，選板 **ESP32 Dev Module**，燒錄。

## 首次 Wi-Fi 設定

1. 開機顯示預覽圖後，若沒有 Wi-Fi 設定，板子會開啟熱點：
   - SSID：**NEON-SERPENT-CYD**、密碼：**serpent3d**
2. 手機／電腦連上該熱點，瀏覽器開 **http://192.168.4.1**
3. 輸入家裡 Wi-Fi 名稱與密碼送出 → 板子自動重啟連線
4. 連上後 TFT 狀態列顯示板子 IP（例如 `192.168.1.42`）；要重設定，長按 BOOT 3 秒

## 連上遊戲

遊戲是 WebSocket **client**，板子是 **server**。遊戲頁網址加上參數：

```
https://<你的遊戲網址>/?agentWs=ws://<板子IP>:8787
```

或在遊戲內 **AGENT** 面板的 WebSocket 欄位輸入 `ws://<板子IP>:8787` 按 CONNECT。

連線成功後：

- 板子自動 `join` 一條 Agent 蛇（滿場時替換一個 AI 對手）
- 遊戲每個 tick 傳 `state`，板子顯示分數／長度／速度／排行榜
- 板子觸控按鍵送 `command`（`+x -x +y -y +z -z`，與網頁觸控板同軸向）

## 觸控按鍵對應

| 板子按鍵 | 3D 方向 | 說明 |
| --- | --- | --- |
| FWD | `-z` | 前進（同網頁 ▲） |
| BACK | `+z` | 後退（同網頁 ▼） |
| LT / RT | `-x` / `+x` | 左右移動 |
| Y+ / Y- | `+y` / `-y` | 上升 / 下降 |
| PAUSE | — | 暫停／恢復 |
| AUTO | — | 切換自動駕駛 |

## 更換開機圖片（顯示自己的照片）

```bash
# 1. 把照片存成 PNG 放到 assets/hello.png（手機/電腦都能另存 PNG）
# 2. 重新轉檔 + 燒錄
node tools/make-splash.mjs     # 有 assets/hello.png 就用它，否則用 preview.png
node tools/render-splash-preview.mjs   # 產生 docs/splash-preview.png 預覽裝置畫面
```

圖片會以「cover」方式裁切縮放成 240×320（直向）。

## 開機問候（Hello Teddy）

- 開機順序：顯示圖片 → 畫 `HELLO TEDDY!` 橫幅 → 喇叭播放問候曲（約 2.2 秒，自製旋律）→ 進入 Wi-Fi／控制器模式
- 喇叭接背面 **SPK** 2P JST 座（板載擴大機，訊號在 **GPIO 26**）
- 要靜音：`platformio.ini` 加 `-D HELLO_MELODY_ENABLED=0`
- 圖片下緣會蓋一條 52px 橫幅；不想要可把 `setup()` 裡的 `drawHelloBanner()` 拿掉

## 疑難排解

- **白畫面／黑畫面**：部分 CYD 變體是 ST7789 面板、背光在 GPIO 27。把 `ILI9341_2_DRIVER` 換成 `ST7789_DRIVER`、`TFT_BL=27`，並確認 `TFT_BACKLIGHT_ON=HIGH`。
- **沒有聲音**：確認喇叭接到背面 SPK 座；查 `SPEAKER_PIN=26` 是否符合你的板子變體；或確認 `HELLO_MELODY_ENABLED=1`。
- **觸控位置不準**：調整 `TOUCH_CAL`（`{xMin, xMax, yMin, yMax, rot}`），或參考 CYD 社群校正值。
- **燒錄失敗**：按住 BOOT 再按 RST 進入下載模式。
- **序列除錯**：115200 baud，開機後 `[WS]` 開頭訊息可看到通訊內容。

## 通訊協定

namespace：`neon-serpent-3d/1`

| 方向 | 訊息 | 內容 |
| --- | --- | --- |
| 遊戲→板子 | `hello` | 通訊協定、可用方向 |
| 遊戲→板子 | `state` | 完整競技場快照（每 tick） |
| 板子→遊戲 | `join` | `{name, color}` 加入 Agent 蛇 |
| 板子→遊戲 | `command` | `{direction}` 移動指令 |
| 板子→遊戲 | `autopilot` | `{enabled}` 切換自動駕駛 |
| 板子→遊戲 | `pause` / `resume` | 暫停／恢復 |
