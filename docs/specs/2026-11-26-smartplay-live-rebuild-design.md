# SmartPLAY Live v5 — 重建設計文件（Design Spec）

- 日期：2026-11-26
- 狀態：**待批准（未開始實作）**
- 作者：OpenCode（與 Teddy Sir 共同brainstorm）
- 目標 repo：`hkteddychan/smartplay-live`（code/docs）＋ `smartplay-live-vault`（部署源碼鏡像）＋ `smartplay-ops-backup`（n8n 備份）
- 相關文件：`D:\Teddy\Opencode\SmartPLAY\RESOURCE-AUDIT.md`（資源實測）

---

## 1. 意圖（Intent）與原因（Why）

現行系統（v4.0-n8n-db）由五件互不相干嘅東西拼成：Cloudflare Worker cron 每分鐘跑、n8n DataTable 做中間數據庫、GitHub repo 做數據載體、GitHub Pages 做網站、CYD 直接讀 repo 內 JSON。結果：

1. **數據以 git commit 做傳輸**：每輪約 42MB，10,399 commits / 2.9GB repo，接近 GitHub 5GB 軟上限。
2. **延遲不可控**：Worker → n8n DataTable（43k 行分頁，單次 4.5 分鐘）→ Worker → GitHub commit → Pages（cache 600s）→ CYD。實測 2026-11-24 03:21 之後停了 38 小時，**冇任何機制發現**。
3. **數據源冇 conditional GET**：6 個 dataset 共 48.6MB、無 ETag / Last-Modified / gzip、query param 會被 405。所以「更新檢查」= 完整下載。
4. **WAF 風險**：源頭在阿里雲 anti-bot 之後（`aliyungf_tc` / `acw_tc`）。實測短時間內抓 6 個檔（48MB）就會被 405 封 75–120 秒。
5. **密鑰外洩**：n8n API key 明文寫死在 Worker 同 n8n Code node；Telegram token 曾以明文出現在對話。

**v5 的意圖**：把「抓取 → 比對 → 通知 → 派送」變成一條 **單一、可觀察、有後備** 的管道；延遲目標 **≤60 秒**（全部 5 個場地運動）；網站功能一個不減；儲存有上限、唔會爆；Git 只放程式碼。

---

## 2. 目標 / 非目標 / 反目標

### Goals
- G1 五個場地運動（badminton / basketball / volleyball / tennis / turf-soccer-pitch）**每輪 ≤60 秒**完成抓取＋比對＋派送。
- G2 放場（`inc` / `new`）**由偵測到落地 ≤5 秒**送到 Telegram 同 ntfy；CYD 由 poll 到收到 ≤20 秒。
- G3 網站 6 個 tab、所有 filter、CSV 匯出全部保留，並修好 stale 無提示、URL 狀態丟失等問題。
- G4 任何一層死（poller / 派送 / 通知）都有明確後備，且 **5 分鐘內會有人知**。
- G5 儲存有硬上限：SQLite 穩定狀態 ≤500MB；Git repo 不再增長；Cloudflare 用量在免費層內。
- G6 版本可追溯：每次部署可對應 tag + commit + 部署 ID；回滾 <10 分鐘。

### Non-goals
- 不做用戶帳戶 / 登入 / 個人化訂閱（v5.0）。
- 不改 LCSD 官方數據本身，不做自動訂場（自動化落單）。
- 不搬離 GitHub Pages（保留 `hkteddychan.github.io/smartplay-live/`）。
- 不引入新 VPS（用現有 Oracle + Cloudflare + GitHub）。

### Anti-goals（就算技術上做到都算失敗）
- 為求快而令源頭封 IP，導致連續幾小時攞唔到數據。
- 通知太吵，令 Teddy 關掉通知 → 等於零。
- 網站「看起來正常」但數據實際停咗（今次的問題）。
- 為咗省事把 raw 48.6MB 落地，幾日就爆盤。

---

## 3. 約束（Constraints，全部實測）

| # | 約束 | 影響 |
|---|---|---|
| C1 | 源頭 6 個 dataset 共 **48.6MB**，無 ETag / Last-Modified / gzip / pagination；加 query param → 405 | 每輪必須全量下載；無法「只問有冇變」 |
| C2 | 阿里雲 anti-bot：短時大量抓取 → **405 封 75–120 秒** | 必須順序 + 拉開間隔 + 退避；60 秒係「貼線」而非「安全」 |
| C3 | Oracle VM：2 OCPU / 16GB / **磁碟 90% 滿（剩 17GB）** | 開工前要清盤；SQLite 要設上限 |
| C4 | 只有 Cloudflare account `f5ad1a2b…` 的 Workers/KV/D1/Pages **write**；zone 只有 `spot.hk` 且 **read-only** | 不可建自訂 DNS；好用 `*.teddy-spot.workers.dev` |
| C5 | R2 未啟用（開關在 dashboard，`enable` 一次即可） | 需要 Teddy 開一次；否則降級用 KV（有寫入配額問題，見 §7.4） |
| C6 | Telegram：bot `@Teddymoltbot`，chat `5200360037`，thread `68130` | 直發 Bot API，不經 n8n |
| C7 | CYD：ESP32、240×320、ArduinoJson、TFT_eSPI；OTA 每 6 小時 check `esp32/firmware.json` | firmware 必須向後兼容舊 feed 路徑一個版本 |
| C8 | 網站係單檔 `index.html`（87KB SPA），直接 fetch `data/*.json` | 需改為讀 API，但 UI 邏輯盡量不動 |
| C9 | n8n 為共用實例（100 workflows），DataTable 有 43k 行 | 停用 SmartPLAY 相關 workflow 前必須備份 |

---

## 4. 架構（Architecture）

```
                          LCSD Open Data（6 datasets, 48.6MB, WAF）
                                        │
        ┌───────────────────────────────┴────────────────────────────┐
        │ Primary（正常情況）                                          │ Fallback（僅在 primary 心跳停 >3 分鐘，且取得租約）
        ▼                                                             ▼
 Oracle VM  systemd: smartplay-poller                       GitHub Actions cron */5
 Python 3.12 · 單一長跑 process                            同一份 poller.py --once --degraded
        │                                                             │
        ├─ SQLite（Single Source of Truth）                          │
        │   sessions / events(seq) / sweeps / rollup                  │
        ├─ Diff Engine（記憶體內比對）                                 │
        │                                                             │
        ├─► Telegram Bot API（直發，<1s）                              │
        ├─► ntfy（自架，APK + TG 備用通道）                            │
        └─► R2  snapshot（gzip JSON）+ 心跳 status.json ◄──────────────┘
                    │
                    ▼
        Cloudflare Worker「feed-api」×2（A/B 雙部署，read-only）
        /v1/state  /v1/changes?since=  /v1/stream(SSE)  /v1/health
                    │
        ┌───────────┴────────────┬──────────────────┐
        ▼                        ▼                  ▼
  Website (Pages, 6 tabs)   CYD firmware v4   Android APK（未來）
```

> **Fallback 為何用 GitHub Actions 而唔用 Worker**：Worker Free plan 只有 10ms CPU，parse 8–9MB JSON 一定爆；用 Actions（ubuntu runner，Python 同 primary 完全同一份 code）無此限制，代價係延遲變 5 分鐘。詳見 5.9。

**核心原則**
1. 只有一個寫入者（single writer）。Fallback（GitHub Actions）只會在 primary 心跳停 >3 分鐘、並取得租約（`lease.json` in R2，TTL 5 分鐘）之後才寫。
2. 源頭只被「一個 IP」抓（正常情況）。避免兩個 poller 同時打 WAF。
3. 通知與網站互不依賴：TG/ntfy 由 poller 直發；網站/CYD 讀 R2→Worker。任何一邊死，另一邊照跑。
4. R2 係「已發佈狀態」；SQLite 係「完整狀態 + 歷史」。R2 可以隨時由 SQLite 重建。

---

## 5. 元件設計

### 5.1 Oracle Poller（Python 3.12）

位置：`/opt/smartplay/`（systemd `smartplay-poller.service`，`Restart=always`）

```
/opt/smartplay/
├── .env                 (600) TG_TOKEN, TG_CHAT, TG_THREAD, NTFY_URL, R2_* , HMAC_KEY
├── poller.py            主循環
├── fetch.py             HTTP + WAF 節奏控制
├── diff.py              diff engine
├── notify.py            TG / ntfy / 重試 / 去重
├── publish.py           R2 發佈 + 心跳
├── db.py                SQLite helper
├── schema.sql
├── state.db             SQLite（WAL）
└── logs/poller.log      logrotate 每日，保留 14 日
```

**主循環（每 60 秒一輪，永不重疊）**

```python
CYCLE_S = 60                     # 目標週期
STAGGER_S = 8                    # 每個 dataset 之間最少間隔
ORDER = ["turf-soccer-pitch",    # 3.1MB，最細先
         "tennis",               # 4.9MB
         "basketball",           # 8.6MB
         "volleyball",           # 8.6MB
         "badminton",            # 8.9MB
         "activity-prog"]        # 14.6MB（獨立節奏，見下）

def main():
    while True:
        t0 = time.monotonic()
        try:
            run_cycle(t0)
        except Fatal as e:
            alert("poller fatal", e); time.sleep(60)
        time.sleep(max(0, CYCLE_S - (time.monotonic() - t0)))
```

**`run_cycle` 順序**
1. `fetch_all()` — 5 個設施運動，順序，每個之間 `sleep(STAGGER_S ± jitter 0~2s)`。
2. 解析（每檔獨立，失敗只影響該檔）。
3. `diff()` 產生事件（寫入 `events`，`seq` 由 SQLite AUTOINCREMENT 保證單調）。
4. `notify()` 推送（TG + ntfy），成功後標記 `notified_*`。
5. `publish()` 寫 R2：`state/<sport>.json.gz`、`changes/latest.json.gz`、`status.json`。
6. 寫 `sweeps` 一行（耗時、bytes、成功 dataset）。

**activity-prog（14.6MB）獨立節奏 — 獨立 thread，但共用 Gate 鎖**

唔可以塞入同一個 60 秒 cycle（會令該輪 ~49MB、必然超時），所以：

```
Thread A（主）：5 個設施運動，每 60s 一輪          ← 受 G1（≤60s）約束
Thread B（副）：activity-prog，每 5 分鐘一次        ← 唔計入 G1
                 ↓
         兩者共用 `Gate`（threading.Lock）：
         同一時間只可以有一個 HTTP 請求打 LCSD，
         所以 Thread B 會「排隊」等 Thread A 做完一批先插入，
         峰值頻寬唔會翻倍（守住 anti-goal：唔好激怒 WAF）。
```

- 若 Thread B 等超過 3 分鐘仍未取得鎖 → 跳過該輪（活動數據遲 5 分鐘無影響）。
- **SLO 只適用於 Thread A**（5 個設施運動）；驗收表已註明。

#### 5.1.1 WAF 節奏控制（重點）

```python
class Gate:
    """自適應節流：正常 60s；遇 405 即進入 latch，逐級放慢。"""
    BASE = 60
    LATCH_SLEEP = [90, 150, 240, 300]     # 連續 405 的退避階梯
    SAFE_MODE = 120                        # 30 分鐘內 3 次 latch → 安全模式

    def __init__(self):
        self.latches = deque(maxlen=10)     # 記錄最近 latch 時間
        self.safe_until = 0

    def on_405(self):
        self.latches.append(time.time())
        n = len([t for t in self.latches if time.time() - t < 1800])
        sleep(self.LATCH_SLEEP[min(n - 1, 3)])
        if n >= 3:
            self.safe_until = time.time() + 3600
            alert("WAF: 進入安全模式（120s）", f"30 分鐘內 {n} 次 405")
```

**具體規則**
- 用 `requests.Session()`，keep-alive，`Cookie` 持久化到 `cookies.json`（保存 `acw_tc`）。
- Header 固定：`User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36 SmartPlayLive/5.0`、`Accept: application/json`、`Accept-Encoding: gzip, deflate`、`Referer: https://www.smartplay.lcsd.gov.hk/`。
- **順序，不並發**（並發 = 峰值頻寬 = WAF 觸發）。
- 單檔 timeout 90s；失敗重試 2 次（間隔 20s、40s）；仍失敗 → 保留上一版數據，`dataset_status` 記錯，唔中斷整輪。
- 收到 405 / 403 / 429：即刻停手，按 Gate 退避；**唔會**在 latch 期間再試。
- 每日 03:00–03:30（HKT）做一次「冷卻」，跳過 3 個 cycle（降低長時間穩定負載特徵）。
- 監控：`sweeps.waf_state` 記 `ok / latch / safe`，24 小時 latch >6 次 → TG 建議降頻。

> 理由：源頭冇 conditional GET，所以「縮短週期」只能靠「減少每輪浪費」同「拉平頻寬」。60 秒 × 48.6MB = 6.5 Mbps 持續，係可行但要貼線監控。若實測 WAF 太敏感，Fallback 係 75 秒或 90 秒（經設定檔，唔使改 code）。

#### 5.1.2 解析與壓縮

LCSD 原始 record（實測欄位）：`Available_Date`、`Available_Courts`、`Venue_Name_TC`、`District_Name_TC`、`Session_Start_Time`、`Session_End_Time`、`Facility_Name_TC`…（沿用現有 worker 的 `compactRows` 映射，已驗證可用）。

只保留：
- `Available_Courts > 0`
- 日期在 **今日 .. 今日+7**（HKT）
- 5 個場地運動

預估保留 43,752 行（與現狀一致）。

---

### 5.2 SQLite Schema

```sql
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE sessions (
  sport TEXT NOT NULL, venue TEXT NOT NULL, facility TEXT NOT NULL,
  date TEXT NOT NULL, start TEXT NOT NULL, "end" TEXT NOT NULL,
  courts INTEGER NOT NULL,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  released_at TEXT,                 -- 最近一次「由 0 變 >0」時間
  PRIMARY KEY (sport, venue, facility, date, start, "end")
) WITHOUT ROWID;

CREATE TABLE events (
  seq INTEGER PRIMARY KEY,          -- 由 R2 meta/seq.json 配發（見下），唔用 AUTOINCREMENT
  ts TEXT NOT NULL,                 -- ISO8601 +08:00
  sport TEXT NOT NULL, venue TEXT NOT NULL, facility TEXT NOT NULL,
  date TEXT NOT NULL, start TEXT NOT NULL, "end" TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('new','inc','dec','gone','sale7','resync')),
  before INTEGER, after INTEGER,
  notified_tg INTEGER DEFAULT 0, notified_ntfy INTEGER DEFAULT 0,
  notify_err TEXT
);
CREATE INDEX idx_events_ts ON events(ts);
CREATE INDEX idx_events_kind ON events(kind, ts);

CREATE TABLE sweeps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT, finished_at TEXT, ms INTEGER,
  bytes INTEGER, ds_ok INTEGER, ds_total INTEGER,
  waf_state TEXT, note TEXT
);

CREATE TABLE dataset_status (
  name TEXT PRIMARY KEY, last_ok TEXT, last_err TEXT,
  err_streak INTEGER DEFAULT 0, bytes INTEGER
);

CREATE TABLE daily_rollup (
  day TEXT, sport TEXT, venue TEXT, kind TEXT, n INTEGER,
  PRIMARY KEY(day, sport, venue, kind)
);

CREATE TABLE outbox (           -- 通知失敗重試隊列
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seq_from INTEGER, seq_to INTEGER, channel TEXT,
  payload TEXT, attempts INTEGER DEFAULT 0,
  next_try TEXT, last_error TEXT
);
```

**Retention 政策（每次 cycle 尾執行，成本 <10ms）**
| 表 | 保留 | 動作 |
|---|---|---|
| `events` | 180 日 | 先 rollup 去 `daily_rollup`，再 delete |
| `sweeps` | 7 日 | delete |
| `outbox` | 成功後即刪；失敗 3 日 | delete |
| `daily_rollup` | 永久（每年 <100KB） | — |

每週日 04:00 `VACUUM`。

**容量預測（用實測 3 變化/分鐘）**
| 項目 | 大小 |
|---|---|
| sessions 43,752 行 | ~7MB（+index ~15MB） |
| events 180 日（~780k 行） | ~90MB |
| rollup | <1MB |
| **合計穩定狀態** | **~110MB** |
| 磁碟 guard | >75% 警告、>85% 自動 prune 至 90 日 |

#### 5.2.1 `seq` 由邊個配發（重要 — 解決雙 writer 問題）

`seq` **唔可以**用 SQLite `AUTOINCREMENT`，因為 primary 同 fallback 可能輪流寫。改為：

```
R2: meta/seq.json = {"seq": 123456}

每次要發事件：
  1. 取得寫入租約（lease，見 5.9）→ 保證同一時間只有一個 writer
  2. 讀 meta/seq.json
  3. 本地分配 seq+1 .. seq+n
  4. 寫入 SQLite（seq 用明確值）
  5. 寫回 meta/seq.json（帶 If-Match/ETag 條件寫，衝突則重讀重試）
```

- 租約 holder 換人（Oracle ↔ GitHub Actions）時，新 holder 先讀 `meta/seq.json` 續號，唔會撞。
- Primary 恢復時做一次 **resync**：用 SQLite 最後狀態 vs 新抓數據 diff，若發現中間有 fallback 寫過嘅事件，只補 `seq` 之後嘅新事件，並插一條 `kind='resync', note='{from_seq}..{to_seq} 由 fallback 處理'`，令客戶端知道自己漏咗一段（`/v1/changes` 會回 `gap:true`）。
- 客戶端規則：見到 `resync` → 重拉 `/v1/state`（唔會顯示錯嘅舊數據）。

---

### 5.3 Diff Engine

```python
def diff(prev: dict[Key, int], cur: dict[Key, int]) -> list[Event]:
    ev = []
    for k, n in cur.items():
        p = prev.get(k)
        if p is None:                       ev.append(E(k, "new", 0, n))
        elif n > p:                         ev.append(E(k, "inc", p, n))
        elif n < p:                          ev.append(E(k, "dec", p, n))
    for k, p in prev.items():
        if k not in cur and p > 0:          ev.append(E(k, "gone", p, 0))
    return ev
```

**規則**
- `Key = (sport, venue, facility, date, start, end)`。
- 同一 key 在 **90 秒內** flip 兩次（1→0→1）：只保留最後狀態，`inc` 事件仍會發，但 `dec` 標記 `suppress_alert`（避免「被訂走」噪音）。
- **day-7 開賣（`sale7`）**：唔用固定時間窗（LCSD 時間會漂移），改用**兩個條件任一成立**：
  1. **時間 + 日期**：06:45–08:00 HKT，且事件日期 = 當前資料集中**最遠可訂日期**（唔硬編 `today+7`）
  2. **爆量偵測**：任何 60 秒內同一運動 `new/inc` 事件 > 50 條 → 整批標為 `sale7`

  該批次**不合併入普通放場通知**，改為 08:15 出一條 summary（場館 × 可訂場數）。若 08:15 前仍有爆量（例如開賣延遲），summary 順延至爆量結束後 15 分鐘。
- 事件一律先落 SQLite（`seq` 單調），再通知。斷電重啟後可從 `outbox` 補發。

**通知篩選（不同 channel）**

| 條件 | TG | ntfy | CYD beep | 網站 |
|---|---|---|---|---|
| `inc` / `new`，`start < 18:00` | ✅ | ✅ | ❌ | ✅ |
| `inc` / `new`，`start ≥ 18:00` | ✅ | ✅ | ✅ | ✅ |
| `dec` / `gone` | ❌（只入記錄） | ❌ | ❌ | ✅ |
| `sale7` | ✅ summary | ✅ summary | ✅ 短促（不同 pattern） | ✅ |

---

### 5.4 通知層（notify.py）

**Telegram**
```python
def tg_send(text, thread=TG_THREAD, disable_notification=False):
    r = post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json={
        "chat_id": TG_CHAT, "message_thread_id": thread,
        "text": text, "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": disable_notification,
    }, timeout=10)
    if r.status_code == 429:            # 被限流 → 等 retry_after
        time.sleep(int(r.json()["parameters"]["retry_after"]))
        raise Retryable()
```

**批次合併 — 先送後併（send-first, coalesce-after）**

為同時滿足「≤5 秒送達」同「唔洗版」：

```
每輪 diff 完成（t=0）：
  ├─ 第一批事件（最多 12 條）→ 即刻發（不等）        ← 延遲 = 抓取 + diff ≈ 3–8s
  └─ 同一輪或之後 15 秒內再有事件 → 合併成 1 條「補充」訊息

07:00 爆量（sale7）：
  ├─ 唔逐條發 → 只發一條「開賣中…」提示
  └─ 08:15 發 summary（見 5.3）
```

即係：正常情況零等待；爆量情況自動收斂。**唔存在固定 30 秒窗口造成的延遲。**

```
🏸 放場 ×3
• 11-28 (五) 19:00-20:00 香港單車館 主場 1→3
• 11-29 (六) 20:00-21:00 荃灣體育館 2→2 (+1)
• 11-30 (日) 18:00-19:00 摩士公園 1→1 (新)
```

**重試**：3 次（1s / 5s / 20s）→ 失敗入 `outbox`，每 60 秒重試，最多 3 日。

**ntfy**
```
POST https://ntfy.tedton.hk/smartplay
Title: 🏸 放場
Priority: high
Tags: tennis
Body: ...
```
- 同步發去 TG 同 ntfy；**兩者任一成功即算送達**（記 `delivered`）。
- 如果兩者都失敗 → `outbox` + 網站 banner「通知管道異常」。

---

### 5.5 發佈層（R2 + 心跳）

每次有變化才寫（用內容 hash 比對，避免無謂寫入）：

| 物件 | 內容 | 大細 |
|---|---|---|
| `state/<sport>.json.gz` | 該運動當前所有可訂場（compact） | 30–300KB |
| `state/meta.json` | 生成時間、行數、hash | <1KB |
| `changes/latest.json.gz` | 最新一批變化（給 CYD/APK） | 5–60KB |
| `changes/seq/<n>.json.gz` | 可選：按 seq 分頁（給 `?since=`） | — |
| `status.json` | 心跳：last_ok、cycle_ms、datasets、waf_state、rows、version | <2KB |
| `lease.json` | primary 租約（TTL 5 分鐘） | <200B |

> `changes/seq/<n>.json.gz` 若 R2 寫入量太大，改為在 Worker 內由 `events` 導出（見 5.6）。實作時先量測。

---

### 5.6 Cloudflare Worker「feed-api」（read-only）

部署：`smartplay-feed.teddy-spot.workers.dev`（**唔需要 DNS**）。

```
GET /v1/health                      → {ok, last_ok, age_s, version}
GET /v1/state?sport=&district=&date= → compact state（gzip）
GET /v1/changes?since=<seq>&limit=200 → {events:[...], next_seq, more:bool}
GET /v1/stream?since=<seq>          → SSE，每 5 秒查一次 R2，有新事件即推
GET /v1/analytics?range=7d|30d      → 預計算 rollup
GET /v1/esp/status                  → CYD 實機狀態（讀 mirror Worker 寫入嘅 KV）
GET /v1/legacy/<file>.json          → 向後兼容舊 CYD（代理 R2 物件）
```

- 綁定 R2 bucket `smartplay`（read-only binding）。
- Cache API：`/v1/state` 邊緣 cache 10 秒；`/v1/changes` 5 秒。
- CORS：`Access-Control-Allow-Origin: https://hkteddychan.github.io`（+ `*` for GET 方便測試）。
- Rate limit：每 IP 每分鐘 120 次（用 `cf-connecting-ip` + cache 計數；超限回 429）。
- **呢個 Worker 完全唔碰 LCSD，亦唔做 diff**（避免 Free plan CPU 10ms 限制；亦避免成為第二個 WAF 來源）。
- 雙部署：同一份 code 部署兩個 script — `smartplay-feed` 同 `smartplay-feed-b`（同一 account、同一 R2 binding）。網站/CYD 依次試 A → B，任何一個 script 壞都仲有另一個（script 級故障域，唔係 account 級）。
- **CYD 上報唔喺呢個 Worker**：`POST /esp/report` 保留在現有 `smartplay-live-mirror` Worker（帶 `X-Device-Key`），寫入 KV（每 5 分鐘一次 = 288 寫/日，遠低於免費層 1,000/日）。feed-api 只讀。KV 喺免費層內，唔需要 D1。

**Worker 亦兼任 Watchdog**（見 5.8）。

---

### 5.7 CYD Firmware v4（ESP32-2432S028）

改動最小化：
- `URL_CHANGES = https://smartplay-feed.teddy-spot.workers.dev/v1/changes?since=%d&beep=1`
- Poll 間隔：**20 秒**（現時 90 秒 / 文檔寫 3 分鐘）。
- 首次開機只取 `latest_seq` 做 baseline（唔 beep 歷史）。
- 斷線 >5 分鐘重連：只更新 `since`，**唔會補 beep**，畫面顯示「⚠️ 漏咗 N 個放場」。
- 保留 `browse.json` 路徑（由 `/v1/state` 生成），瀏覽模式不變。
- OTA：維持 `esp32/firmware.json`（每 6 小時 check），但 **CI 改為直接寫入 `smartplay-live` repo**（現時寫入 vault，靠人手同步，係隱患）；刪除死檔 `esp32/ota.json`。
- 新增：`REPORT_KEY` 驗證（現時 `/esp/report` 無 auth，任何人可偽造狀態）。

---

### 5.8 監控與 Watchdog（四層）

| 層 | 位置 | 頻率 | 做乜 | 如果佢自己死 |
|---|---|---|---|---|
| W1 | 專用 Worker `smartplay-watchdog`（cron `* * * * *`，獨立於 feed-api） | 每 1 分鐘 | 讀 `status.json`；`age > 180s` → TG 告警 + 開租約俾 fallback | GitHub Actions 兜底 |
| W2 | GitHub Actions cron | 每 5 分鐘 | 直接查 R2 API；`age > 600s` → TG 告警（唔經 Worker） | W1 仍會響 |
| W3 | systemd `OnFailure=` + `WatchdogSec` | 即時 | poller crash / hang → TG + 重啟 | — |
| W4 | 每日 09:00 通道 canary | 每日 | 同時經 TG 同 ntfy 發一條 HEARTBEAT，檢查兩個通道 | 人手 |

**實際最壞情況**：W1 1 分鐘 + `age>180s` ≈ **4 分鐘**內知道；若 W1 同時死，W2 5 分鐘內補上（≈ 10 分鐘）。呢個係接受範圍，比今次 38 小時好 500 倍。
（原本設計寫「5 分鐘」係錯，因為 W1 每 5 分鐘跑一次；已改為每分鐘。）

**告警去重**：同一狀態 15 分鐘內只發一次；恢復時發一條「✅ 已恢復（停了 X 分鐘）」。

---

### 5.9 後備矩陣（Fallback Matrix）

| 失敗情境 | 偵測 | 自動反應 | 用戶感知 |
|---|---|---|---|
| LCSD 單一 dataset 失敗 | `dataset_status.err_streak` | 用上一版數據，重試 3 次；5 次連續失敗 → 暫停該 dataset 10 分鐘 | 該運動數據稍舊（banner 標示） |
| LCSD WAF 405 | HTTP status | 退避 90→300s；30 分鐘 3 次 → 安全模式 120s | 延遲由 60s 變 120s，TG 通知 |
| Oracle poller crash | systemd | 自動重啟；失敗 3 次 → 停用 + 告警 | TG「poller 停」 |
| Oracle 整機死 / 斷網 | W1 心跳 >3 分鐘 | Fallback（GitHub Actions）取租約，每 5 分鐘跑同一份 `poller.py --once --degraded`，寫 R2 + 發 TG | 延遲變 5 分鐘，網站 banner「降級模式」 |
| Oracle 磁碟滿 | disk guard | 自動 prune（180→90→30→7 日）；仍 >90% → 停寫大 snapshot，只寫 `changes` | TG 告警 |
| R2 寫入失敗 | publish 例外 | 重試 3 次；仍失敗 → 保留 SQLite，Worker 回 503 + 網站 banner | 網站 stale 提示 |
| feed-api Worker 死 | W1/外部 | 網站自動切 `smartplay-feed-b`（第二個 script，同一 R2） | 用戶無感 |
| 兩個 feed Worker 都死 | 網站 | 退回讀 Pages 上的 `last-good.json`（只在有變化時更新，細檔） | 功能降級，仍可看 |
| Telegram 429/5xx | API 回應 | 重試 3 次 → ntfy → outbox | 遲幾秒 |
| Telegram 完全掛 | 連續失敗 | ntfy 成為唯一通道（APK 都收） | 少一條通道 |
| ntfy 死 | HTTP | TG 為主；APK 改用 poll `/v1/changes` | APK 由 push 變 poll |
| 兩者都死 | outbox | 累積 + 恢復後補發（標記「遲到」）+ 網站 banner | 網站仍可查 |
| CYD 離線 | 裝置端 | 重連後 `?since=` 補狀態，不補 beep | 畫面提示漏咗 N 個 |
| GitHub Pages 部署失敗 | Actions | 重試 3 次（現有機制保留）+ TG 告警 | 網站停留上一版 |
| 密鑰外洩 | 人工 | 一鍵 rotate：改 CF secret + Oracle .env + ntfy token | — |

---

## 6. 網站（index.html）改動

**不改的東西**：6 個 tab、所有 filter、CSV、CYD 1:1 重演、分析圖表、深色 UI。

**改的東西**

| 項目 | 現時 | v5 |
|---|---|---|
| 數據來源 | `data/*.json`（git） | `/v1/state`、`/v1/changes`、`/v1/analytics` |
| 更新方式 | 每 2 分鐘 fetch + cache-buster | 首頁 60s poll + `?since=` 增量（有變化才重繪） |
| 首屏 | 一次過 parse 33MB | 只拉當前運動 + 當前 7 日（~300KB gzip） |
| Stale 提示 | 冇（今年 11-24 停 38 小時冇人知） | `age > 180s` → 頂部紅色 banner + 顯示真實數據年齡 |
| URL 狀態 | 無 | `#tab=facility&sport=badminton&d=2026-11-28` |
| 分析 tab | 「重新分析」逐次計 | 讀 `daily_rollup`，開頁即出 |
| 無障礙 | 0 aria | 主要 control 加 aria-label |
| ESP View | 讀 `esp32/status*.json` | 讀 `/v1/esp/status`（CYD 經 Worker 上報） |

**向後兼容**：舊 `data/*.json` 同 `esp32/*.json` 保留最後一份，舊 CYD firmware 唔會即刻壞（可以慢慢 OTA）。

---

## 7. 安全

| 項目 | 現狀 | v5 |
|---|---|---|
| n8n API key | 明文在 Worker code + n8n Code node | **即刻 rotate**；只存 Oracle `.env` / CF secret |
| Telegram token | 曾明文出現 | 只存 CF secret + Oracle `.env`（600）；建議之後換新 bot |
| `/esp/report` | 無 auth | `X-Device-Key`（firmware build flag 注入） |
| `/tg-test` | 有 RUN_KEY（已修) | 移除，改為 `/v1/health` 只回 ok/time |
| R2 憑證 | — | 只存在 Oracle（S3 API token，限定 bucket） |
| n8n DataTable API key | 同上 | 停用相關 workflow 後 revoke |
| Worker secrets | `GITHUB_PAT`, `RUN_KEY`, `TG_BOT_TOKEN` | 只保留 `TG_BOT_TOKEN`（watchdog 用）；其餘刪 |

---

## 8. 版本控制與發佈流程

### 8.1 Repo 分工

| Repo | 內容 | 可見性 |
|---|---|---|
| `smartplay-live` | 網站、docs、specs、CHANGELOG、firmware sketch、worker 部署源碼 | public |
| `smartplay-live-vault` | 每個 tag 的 deploy 源碼快照（worker.js、poller.py、firmware） | private |
| `smartplay-ops-backup` | n8n workflow + DataTable 快照 | private |

**`smartplay-live` 不再存放大批數據**，但有 **14 日兼容期**：

| 期間 | `data/*.json` | `esp32/changes-eve.json` + `browse.json` | 目的 |
|---|---|---|---|
| P1–P5（建置中） | 由 v4 繼續更新（cron 降至 5 分鐘） | 繼續 | 網站/CYD 唔會斷 |
| P6–P6+14 日 | 停止更新 | 由 poller 發佈（**最多 5 分鐘一次 commit，≤150KB**） | 未 OTA 嘅舊 CYD 仲有數據 |
| P6+14 日之後 | 凍結 | 停止 commit（加 `.gitignore`） | repo 零增長 |

- 舊 CYD 每 6 小時 check `firmware.json`，14 日內應該全部 OTA 完成；未完成會在網站「ESP View」顯示離線。
- 兼容檔用 `last-good` 內容，唔會因為 poller 死而 404（但網站會顯示 stale banner）。
- 兼容期結束後 repo 增加量：**0**（只有 code commit）。

### 8.2 Branch / Tag 規則

```
main                     ← 永遠可部署
feature/rebuild-v5       ← 本次重建
fix/<issue>              ← bug fix
docs/<topic>             ← 文件

tag: v5.0.0 / v5.0.1 / v5.1.0
release notes: 必列「行為改變 / 需要手動步驟 / 回滾方法」
```

- 每個 milestone（P1..P8）合併前跑 `npm test`（見 §10）+ 24h soak 抽樣。
- 合併 main 後打 tag，並由 CI 將源碼同步去 vault（用 `gh` push，附 tag）。
- Firmware：tag `esp32-fw-vX.Y`，附 `.bin`；`esp32/firmware.json` 由 CI 寫入 **live repo**。
- CHANGELOG 用 Keep a Changelog 格式。

### 8.3 部署可追溯

每次部署自動寫入 R2 `status.json`：
```json
{"version":"5.0.0","sha":"abc1234","deployed_at":"2026-11-26T10:00:00+08:00",
 "host":"oracle-2ocpu","cycle_s":60}
```
Website footer 顯示 `v5.0.0 · abc1234 · 12s ago`。

### 8.4 回滾

| 層 | 方法 | 時間 |
|---|---|---|
| Website | `git revert` + push（Pages 自動） | ~3 分鐘 |
| Worker | `wrangler rollback` | ~1 分鐘 |
| Poller | `systemctl stop` + 切回 `/opt/smartplay/prev/` symlink | ~1 分鐘 |
| Firmware | 改 `firmware.json` 指回上一個 bin（板 6 小時內自動降級） | ≤6 小時 |
| 數據 | 由 SQLite 重建 R2；或由 vault 的備份還原 | ~5 分鐘 |

---

## 9. 實作計劃（Phases）

| Phase | 內容 | 驗收 | 可獨立回滾 |
|---|---|---|---|
| **P0** | n8n 全量備份（workflow + DataTable）→ `smartplay-ops-backup`，tag `pre-rebuild-2026-11-26`；停用 v1/v2 搬運工；v4 降至 5 分鐘一次（**唔停用**，見 §9.1） | 備份可還原（抽 3 個 workflow 匯入測試） | 是 |
| **P1** | Oracle 清盤 + 建 `/opt/smartplay` + poller 骨架 + SQLite + fetch/gate | 連續 2 小時每輪成功，實測 cycle ≤50s | 是（停 service） |
| **P2** | diff + events + rollup + retention | 用 2 份真實 snapshot 重放，事件數與舊 `changes.json` 對得上 | 是 |
| **P3** | TG + ntfy 通知（含批次、重試、outbox） | 測試訊息到 chat/thread 正確；斷網模擬後補發 | 是 |
| **P4** | R2 發佈 + status 心跳 + Worker `feed-api` | `/v1/state` `/v1/changes` `/v1/health` 正確，延遲 <2s | 是 |
| **P5** | 網站切換數據源（保留舊路徑 fallback） | 6 個 tab 全部功能對比舊版 100% 對齊 | 是（回舊 index.html） |
| **P6** | CYD firmware v4 + OTA 流程修正 | 板上 20s poll、beep 條件正確、OTA 成功 | 是（firmware.json 回舊） |
| **P7** | Watchdog W1/W2/W4 + fallback（GitHub Actions）降級模式 | 手動停 poller → 4 分鐘內告警 + 10 分鐘內接管 | 是 |
| **P8** | 48 小時 soak + 文件 + tag `v5.0.0` | §10 全部達標 | — |
| **P9（可選）** | Repo 瘦身（`git filter-repo` 或開新 repo 保留舊 archive） | clone <300MB | 需另行批准 |

**總工期估算**：P1–P8 約 5–7 個工作天（視乎 WAF 實測結果同 CYD 上板測試）。

### 9.1 平行運行策略（避免網站斷 + 避免雙重打 WAF）

| 期間 | v4 Worker | 新 Poller | 備註 |
|---|---|---|---|
| P0–P1 | cron 由 `* * * * *` 改 `*/5 * * * *` | 只抓 **2 個 dataset**（badminton + turf-soccer）做開發測試 | 兩個來源唔同時抓全部 6 個 |
| P2–P3 | `*/5` | 抓齊 5 個設施運動（60s） | 總負載仍低於現狀（現狀 48MB/min） |
| P4–P5 | `*/10`（只作 shadow） | 全速 | 網站開始讀新 API |
| P6 後 | **停用** | 全速 + fallback | v4 只保留 `/esp/report` |

每周檢視 `waf_state`：若 latch 增加，先降 v4，再考慮 poller 由 60s → 75s。

---

## 10. 驗收標準（Acceptance / SLO）

| 指標 | 目標 | 量度方法 |
|---|---|---|
| 每輪耗時 | median ≤45s，p95 ≤60s（5 個設施運動；activity-prog 另計） | `sweeps.ms` |
| 成功率 | 24h 內 ≥98% cycle 完成 5/5 dataset | `sweeps.ds_ok` |
| 警報延遲 | p95 ≤60s（資料改變 → TG 落地） | `events.ts` vs TG message timestamp |
| WAF | 24h 內 405 latch ≤2 次 | `sweeps.waf_state` |
| Stale 偵測 | ≤5 分鐘 | 手動 kill poller 測試 |
| 通知送達 | ≥99.5%（TG 或 ntfy 任一） | `events.notified_*` |
| 網站 | 6 tab 功能對齊；首屏 ≤2s（4G）；stale banner 正確 | 手動 checklist |
| CYD | poll ≤20s；beep 條件 100% 正確；離線 30 分鐘重連不補 beep | 實機 |
| 儲存 | 30 日後 DB ≤200MB；repo 零增長 | `du`、commit 監控 |
| 回滾 | 任何一層 <10 分鐘 | 演練一次 |

---

## 11. 我（AI）做嘅決定（builder 可自行調整，但需記錄）

1. **SQLite 而唔係 PostgreSQL**：單機、單 writer、<1GB，SQLite 更快更簡單。
2. **Python 而唔係 Node**：現有 `fetch_data.py`、`fetch_esp32.py` 都係 Python；48MB JSON 解析記憶體更可控。
3. **R2 而唔係 KV**：KV 免費層每日 1,000 次寫入，60 秒週期會爆；R2 免費 100 萬寫/月（我們約 4.3 萬）。
4. **Worker 做 read API，唔做寫入**：寫入只有一個來源（poller），避免競態。
5. **`since=<seq>` 增量協議**：CYD / APK / 網站共用，斷線重連唔會漏。
6. **activity-prog 5 分鐘節奏**：保護 60 秒主循環。
7. **day-7 開賣獨立事件類型 `sale7`**：避免 07:00 大批 release 誤鳴。
8. **保留 GitHub Pages**：零 DNS 改動，風險最低。
9. **唔刪除舊 n8n workflow，只停用**：可即時 re-enable。
10. **`/v1/legacy/*` 兼容層**：舊 CYD 未 OTA 完都唔會壞。
11. **`seq` 由 R2 計數器配發 + 租約**，唔用 SQLite AUTOINCREMENT（雙 writer 會撞號）。
12. **Fallback 用 GitHub Actions，唔用 Cloudflare Worker**：Worker Free plan 10ms CPU 冇可能 parse 8–9MB JSON；Actions 跑同一份 Python code。
13. **舊 CYD 兼容期 14 日**，每 5 分鐘最多一次 commit、≤150KB；之後 repo 零數據增長。
14. **通知先送後併**：第一批即刻發，15 秒內其餘合併成一條補充；唔用固定 30 秒窗口。
15. **activity-prog 用獨立 thread + 共用 Gate 鎖**，唔塞入 60 秒主循環；SLO 只計 5 個設施運動。
16. **sale7 = 時間窗（06:45–08:00 + 最遠可訂日）或 60 秒內 >50 條爆量**，唔硬編 `today+7`。
17. **feed-api 唯讀**；CYD 上報留在 `smartplay-live-mirror`（帶 `X-Device-Key`）寫 KV。
18. **feed-api 雙部署 A/B**（兩個 script、同一 R2），避免單一 script 故障；網站自動切換。

---

## 12. 仍需 Teddy 決定 / 提供

| # | 事項 | 影響 | 狀態 |
|---|---|---|---|
| D1 | 開啟 R2（dashboard 一鍵） | 無 R2 → 降級用 KV（延遲 +60s、有配額風險） | ⏳ |
| D2 | 清 Oracle 磁碟（我會先列出清單） | 唔清 → 寫入空間不足 | ⏳ |
| D3 | **ntfy 服務放邊、用邊個 domain**（建議 `ntfy.tedton.hk` → `192.9.242.154`，Docker + NPM + Let's Encrypt） | 冇 → APK 推送 + TG 備援都做唔到；P3 由「寫 client」變成「起服務」 | ⏳ **要你答** |
| D4 | 批准 P9 repo 瘦身 | 唔做 → repo 保持 2.9GB（但唔再增長） | ⏳ |
| D5 | Telegram：確認用 `@Teddymoltbot`（token 已提供）；建議 P8 後 rotate | 影響 P3 開始時間 | ✅ 已答（用 #3） |
| D6 | Workers plan（Free / Paid） | 已用 Actions 做 fallback，唔再阻塞；但影響 feed-api 可否用 Durable Object（v5.1 才需要） | 非阻塞，P4 時確認 |

### 12.1 P0 前必須清嘅風險（我已準備好）

1. Rotate n8n API key（原本明文在 worker + workflow code）。
2. 移走 worker 內 hardcode 嘅 DataTable API key。
3. `esp32/ota.json`（空 md5 死檔）刪除。
4. `smartplay-ops-backup` 快照 + `pre-rebuild-2026-11-26` tag。

---

## 13. 明確唔做（v5.0 範圍外）

- 用戶帳戶 / 多用戶訂閱
- 自動訂場（SmartPLAY 登入 + 落單）
- iOS / Web Push
- 把 `activity-prog` 納入 60 秒循環
- 改動 LCSD 以外的數據源
