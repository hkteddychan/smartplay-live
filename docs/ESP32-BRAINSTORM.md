# ESP32 CYD SmartPLAY — Feature & UI/UX Brainstorm

> Generated 2026-11-04 by OpenCode Agent after implementing WiFi Plan A + browse enhancements.
> Status: proposals only — nothing implemented yet unless marked ✅.

## 已完成（本輪）
- ✅ Push 功能完全移除（淨係 poll）
- ✅ WiFi Plan A 多網絡自動偵測
- ✅ 瀏覽：自選地區 overlay、早/午/晚 時段過濾、運動選擇、Play/Pause
- ✅ 輕量 JSON parser（per-sport 7d 全日檔案）

## 提議功能（Functional）

### 1. 收藏場地（Favorites）
- 每行長按或撳 ⭐ 標記收藏；NVS 儲存場地 index list
- 過濾器「只看收藏」；放場通知時收藏場地優先 beep（不同音高）
- 價值：Teddy Sir 最關心嘅場地，唔使每次揀區

### 2. 通知歷史（Release History）
- 螢幕上保留最近 20 個放場事件（sport/venue/time/old→new + 時間戳）
- 新頁面「歷史」可翻查；tap 一條 → 顯示詳情 card
- 價值：錯過 beep 都可以回看

### 3. 「即將開始」快速過濾
- 顯示未來 2 小時內開始嘅 session（now filter）
- 用 NTP clock 計算；自動刷新

### 4. 場數門檻過濾
- 只顯示 courts ≥ N 嘅行（設定 1/2/3+）
- 針對「要 2 場以上先值得去」

### 5. 場地詳情頁
- tap 一行 → 全螢幕詳情：完整時間、場數、運動、區份、日期
- 可選：顯示預訂 URL 文字（QR code 需要額外庫）

### 6. 設定頁（Settings）
- Beep 開關 / 音量（DAC amplitude）/ 音高
- 自動翻頁秒數（2–30s）滑桿
- 背光亮度（PWM）
- 睡眠超時（N 分鐘無觸控 → dim/off）
- WiFi 網絡優先次序管理（新增/刪除 SSID）
- 語言（繁中/英文）

### 7. 背光自動調暗 / 睡眠
- 無觸控 60s → 背光 30%；5min → 關屏；撳一下喚醒
- 省電，延長板壽命

### 8. 離線快取（SPIFFS/LittleFS）
- 上次成功 fetch 嘅 browse.json 儲落 flash
- WiFi 斷線時仍可瀏覽舊資料 + 顯示「離線」banner

### 9. 遠端設定（Feature flags via feed）
- feed 加 `"cfg"` 物件（beep 預設、poll 間隔），板子讀入 NVS
- 免燒錄更新行為

### 10. 多運動同時顯示（All-sports timeline）
- 「時間軸」視圖：按時間排序所有運動，唔分區
- 方便搵「今晚 7 點有咩場」

## UI/UX 增強

### A. 底部 Tab 導航
- Notify / Browse / History / Settings 四個 tab
- 取代「撳一下入瀏覽」嘅隱藏手勢，降低學習成本

### B. 觸控回饋
- 每次撳有效區域時短促 click beep（可關）
- 按下時按鈕反白 100ms

### C. 載入狀態
- Fetch 期間顯示 spinner + 「載入中…」
- 失敗時顯示重試按鈕（tap 重 fetch）

### D. 空狀態
- 「呢個條件冇場」加上建議（例如：試下其他區/時段）

### E. 色彩語義
- 綠 = 可訂（courts > 0），灰 = 已滿，橙 = 即將開始（&lt;30min）
- 運動 icon 顏色跟運動類型

### F. 字體大小選項
- 小/中/大 三檔，適應視力

### G. Swipe 手勢
- 左右 swipe 翻頁、上下 swipe 揀區
- 補足觸控分區唔夠精準

### H. 狀態列
- 頂部顯示 WiFi RSSI、時間、free heap（debug mode）

### I. 首次使用引導
- 第一次開機顯示 3 步 tutorial overlay

### J. 高對比 / Dark mode
- 夜晚用暗色主題，減光害

## 唔做得（明確排除）
- ESP32 直接訂場（LCSD WAF + 禁 bot）
- OTA（huge_app partition 無 OTA 位）
- 語音輸入（classic ESP32 無 ASR）

## 優先排序建議
1. 收藏場地 + 通知優先（高價值、低成本）
2. 設定頁（beep/亮度/睡眠）
3. 通知歷史
4. 背光自動調暗
5. 底部 Tab 導航（需較大重構）
6. 離線快取
7. 其餘 UI polish
