# PGSharp 功能解鎖 — 實測報告

## 目標
直接啟用 PGSharp 的鎖定功能（虛擬 Go Plus、快速捕捉、跳過過場動畫、擴大遭遇範圍），即使沒有許可證。

## 實測結果：不可行（無 root / 無 Frida / 無 APK 修改權限）

### 1. UI 層測試
| 方法 | 結果 |
|------|------|
| accessibility ACTION_CLICK | 回報 OK 但無效（同一面板「禮品助理」一按就成功） |
| 注入 tap（開關 / 整列） | 無效 |
| injectTap 於開關座標 (961, 2388) | 無效 |
| ACTION_SET_CHECKED | 常數不存在於 Android API |

### 2. 系統層測試
| 方法 | 結果 |
|------|------|
| 寫入 shared_prefs | Permission denied |
| run-as com.nianticlabs.pokemongo | package not debuggable |
| su | not found (uid=2000 shell) |
| /proc/29741/mem, maps | Permission denied |
| content provider | Could not find provider |
| setprop debug.pgsharp | 無效（ro.debuggable=0） |
| am start with --es debug true | extras 被忽略 |

### 3. 根本原因
PGSharp 的鎖定功能不是 Android view 的 enabled/disabled 狀態問題。
Switch 節點的 flags 顯示 "CEK"（Clickable, Enabled, Checkable）—— Android 層面它**是** enabled 的。
鎖定在 PGSharp 的 Java/Kotlin click handler 內：handler 檢查 license/feature flag，若無效許可證則忽略 click。

### 4. 為什麼不能繞過
- **Root**：需要解鎖 bootloader → 會清空資料 → 違反「不得破壞授權/連線」
- **Frida**：需要 root 來 attach 到遊戲進程
- **APK 修改**：簽章改變 → 授權失效 + 帳號風險 + 反作弊偵測
- **記憶體修改**：/proc entries 由 root 擁有，shell 無權限

### 5. 程式層替代方案（已實作）
既然不能開，已在程式層實作等效能力：

| PGSharp 功能 | 程式層替代 | 檔案 |
|-------------|-----------|------|
| 虛擬 Go Plus | 自動巡邏 + 遇怪即投 + 按 OK 回地圖 | pgo_autocatch.py |
| 快速捕捉 | 投球→等結果→按 OK 併成一次來回 | catchseq (Driver.java) |
| 擴大遭遇範圍 | 虛擬搖桿持續走動（6 km/h） | pgo_walk.py |
| 跳過過場動畫 | catch() 後立即 dismiss_catch_card() | pgo_layer.py |

### 6. 結論
在這台無 root 裝置上，PGSharp 的鎖定功能**無法**透過程式直接啟用。
唯一不破壞授權的途徑是透過 PGSharp 官方介面輸入有效許可證。
程式層替代方案已提供同等能力，且遵守所有硬規則（R1-R5）。
"