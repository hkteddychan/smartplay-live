# SmartPLAY Live — ESP32 Feed

康文署場地即時餘額嘅 **ESP32-friendly compact feed**，由
[SmartPLAY Live](https://hkteddychan.github.io/smartplay-live/) 嘅 data mirror 衍生。

## 點樣用（ESP32 裝置）

直接 HTTPS GET（Pages 無 WAF，無 API key）：

| 檔案 | 內容 | 大細 |
|------|------|------|
| `esp32/index.json` | manifest（每個 sport 有幾多行 + 7d 檔名） | <1 KB |
| `esp32/today.json` | 全部 5 種運動，今日+聽日有餘額嘅時段 | ~幾十 KB |
| `esp32/{sport}-7d.json` | 單一運動 7 日資料 | 13–80 KB |

```
https://hkteddychan.github.io/smartplay-live/esp32/today.json
https://hkteddychan.github.io/smartplay-live/esp32/badminton-7d.json
```

## JSON 格式（positional arrays，慳 RAM）

```json
{
  "g": "2026-11-04 02:01",            // 生成時間 HKT
  "d": ["2026-11-04", "2026-11-05"],  // 日期陣列（7d 檔有 7 日）
  "sports": {
    "badminton": {
      "v": ["場地名", ...],            // venue index
      "s": ["區名", ...],              // district index
      "r": [[vIdx,dIdx,dateIdx,startMin,endMin,courts], ...]
    }
  }
}
```

`startMin`/`endMin` = 由 00:00 起計分鐘（e.g. 450 = 07:30）。只包含 `Available_Courts > 0` 嘅行。

## 更新頻率

`data/*.json` 由 Cloudflare Worker 每 15 分鐘鏡像 → 每次 push 觸發
`Build ESP32 Feed` workflow → 重新生成 `esp32/*.json` → Pages 同步上線。
所以 feed 最多延遲 ~15 分鐘（同網站一樣）。

## Arduino 範例

見 [`smartplay_live_esp32.ino`](smartplay_live_esp32.ino)：
- 需要 `ArduinoJson` (>=7) library
- 改 `WIFI_SSID` / `WIFI_PASS` 就燒得
- 預設 filter：九龍城/黃大仙/觀塘 + 晚 6 點後 + 至少 1 場（改 sketch 頂部常數）
- Serial Monitor 115200 睇結果；內置 LED 閃 2 下=成功，長閃=失敗

## 重新生成（本地測試）

```bash
python esp32/fetch_esp32.py    # 讀 repo 內 data/*.json，輸出 esp32/*.json
```
