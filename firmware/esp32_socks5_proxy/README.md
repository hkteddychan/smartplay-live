# SOCKS5 Proxy Node（ESP32 CYD）

將 ESP32-2432S028R 變成 **SOCKS5 代理**：遠端機（AWS VM 等）經這台機的住宅 IP 出去。

## 現況（已驗證）

| 項目 | 值 |
| :--- | :--- |
| 裝置 IP | `192.168.31.34`（DHCP；建議喺 router 做 reservation） |
| Port | `1080` |
| Auth | RFC 1929 username/password：`teddy` / `pogo-teddy-2026` |
| WiFi | 從 NVS `cydmath` 讀（chat 韌體存過），build flag 可 override |
| 分割區 | `huge_app.csv`（佔 ~32% of 3 MB） |
| 屏幕 | 狀態屏：SSID/IP/port/session 數/總連線數/最後 target |

已通過嘅測試：

```
[1] greeting  -> 0502 (user/pass) OK
[2] auth      -> 0100 OK
[3] CONNECT   -> 05 00 00 01 ... OK
[4] HTTP      -> HTTP/1.1 200 OK OK
[6] bad auth  -> 0101 rejected OK
curl --proxy socks5://...@192.168.31.34:1080  http://example.com  -> 200 (0.2 s)
curl --proxy socks5h://...@192.168.31.34:1080 https://example.com -> 200 (0.45 s)
[+] slot 0 client 192.168.31.103:53647
[slot] auth ok (user len 5)
[0->] example.com:80 -> OK (39 ms)
[-] slot 0 closed (client EOF)
```

## 用法

```bash
# build + 燒錄
python -m platformio run -d firmware/esp32_socks5_proxy -t upload --upload-port COM7

# 自訂 SOCKS5 client 測試（greeting -> auth -> CONNECT -> HTTP）
python tools/test-socks5.py 192.168.31.34 1080 teddy pogo-teddy-2026

# 標準 client
curl --proxy "socks5://teddy:pogo-teddy-2026@192.168.31.34:1080" http://example.com
```

任何支援 SOCKS5 + RFC 1929 嘅軟件都可以直接用（PuTTY、proxychains、
Python `socks`、手機 App 等），唔需要自訂握手。

## Configuration（platformio.ini build flags）

| Flag | 預設 | 說明 |
| :--- | :--- | :--- |
| `SOCKS_PORT` | 1080 | 監聽 port |
| `MAX_SESSIONS` | 4 | 並行 session 數 |
| `SOCKS_USER` / `SOCKS_PASS` | `teddy` / `pogo-teddy-2026` | RFC 1929 憑證 |
| `ALLOW_NO_AUTH` | 0 | 設 1 就容許無密碼（唔建議） |
| `WIFI_SSID` / `WIFI_PASS` | 空 | 留空就自動用 NVS `cydmath` |
| `SOCKS_NO_SCREEN` | 未設 | 設 1 完全唔用屏幕（慳少少 RAM/flash） |
| `HANDSHAKE_TIMEOUT_MS` | 20000 | 握手逾時 |
| `IDLE_TIMEOUT_MS` | 120000 | Relay 閒置逾時 |

## 實作要點（專案設計 vs 原始 sketch）

| 原始 sketch（另一個 AI 畀嘅） | 呢個版本 |
| :--- | :--- |
| 自訂「第一行送 ACCESS_KEY」 | 標準 RFC 1929 — 任何 client 用得 |
| 方法選擇固定 0x00 | 揀 client 提議嘅 0x02/0x00，憑證錯 → `0x01 0x01` 拒絕 |
| 手寫單一 read buffer，pipelining 會跌 data | per-session buffer + memmove shift，greeting/auth/request/payload 一齊嚟都處理到 |
| 無逾時 | handshake 20 s、idle 120 s、EOF 雙向偵測 |
| IPv4/domain build 計錯長度風險 | 依 ATYP 核對總長，唔夠先繼續等 |
| 無螢幕 | 狀態屏 + RGB LED（綠=ready、藍閃有 session、紅=no wifi） |
| 斷線唔自救 | WiFi 掉線偵測 + 自動 reconnect + 重新 `begin()` |

REP codes：`0x07` = 有 command 非 CONNECT、`0x08` = ATYP IPv6 唔支援、
`0x05` = target 連唔上。

## 恢復其他韌體

```bash
# 聊天玩具
python -m platformio run -d firmware/esp32_cyd_chat -t upload --upload-port COM7
# NEON SERPENT 控制器
python -m platformio run -d firmware/esp32_cyd_controller -t upload --upload-port COM7
```

## 上層補救（NAT）

ESP32 喺 LAN 入面，VM 從外面連唔入去。兩條路：

1. **Router port forward**： WAN 1080 → `192.168.31.34:1080`，
   防火牆只准 VM IP `13.236.188.205`。留意 ISP 係咪有俾你真 WAN IP。
2. **Reverse relay（已實作，呢個係而家用緊嘅方法）**：

   ESP32 主動出連 VM 打穿 NAT，唔使掂 router：

   ```
   VM local client ─> VM 127.0.0.1:1080 (front)
                          │ byte relay
                          ▼
                    VM :9000 (pool) ◄══ ESP32 出連（常備 RELAY_WORKERS 條）
                                        SOCKS5 auth/CONNECT 全部喺 ESP32 處理
   ```

   - 韌體：`VM_HOST=13.236.188.205` / `VM_PORT=9000` / `RELAY_WORKERS=2`，
     每 5 s 補一條 channel；channel 閒置 120 s 自動回收重撥。
   - VM 端：`tools/cyd_relay.py`（零依賴）+ `tools/cyd_relay.service`。

   VM 部署：

   ```bash
   # 1. AWS Security Group：開 TCP 9000 入站（來源限屋企 IP 最好）
   # 2. 上傳
   scp tools/cyd_relay.py tools/cyd_relay.service user@13.236.188.205:/tmp/
   ssh user@13.236.188.205 'sudo mkdir -p /opt/cyd && sudo mv /tmp/cyd_relay.py /opt/cyd/ &&
      sudo mv /tmp/cyd_relay.service /etc/systemd/system/ && sudo systemctl daemon-reload &&
      sudo systemctl enable --now cyd-relay'
   # 3. 驗證
   ssh user@13.236.188.205 "curl --proxy 'socks5://teddy:pogo-teddy-2026@127.0.0.1:1080' https://example.com"
   ```

   收線後 ESP32 會喺 ~5 s 內自動重撥補 channel，兩邊都係自癒設計。
   想暫時收埋 reverse：platformio.ini 將 `VM_HOST` 留空再燒。
