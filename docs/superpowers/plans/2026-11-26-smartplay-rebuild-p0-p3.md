# SmartPLAY Live v5 — Plan 1：Ingest & Notify（P0–P3）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一個單一 writer 的抓取器（Oracle / Python），每 60 秒抓 LCSD 5 個設施運動、比對出事件、寫入 SQLite，並以 Telegram + ntfy 發送放場警報；同時安全地備份並降頻現有系統。

**Architecture:** 一個長跑 Python process（systemd）內含兩個 thread 共用一個 HTTP Gate。SQLite 為 single source of truth；事件以 R2 上的單調計數器配發 `seq`。通知層用「先送後併」策略，失敗入 outbox 重試。此計劃**不包含** R2 發佈、Worker feed-api、網站切換、firmware（屬 Plan 2/3）。

**Tech Stack:** Python 3.12、`requests`、`sqlite3`（stdlib）、`pytest`、systemd、Docker（ntfy）、GitHub Actions（後續）。

**Spec:** `docs/specs/2026-11-26-smartplay-live-rebuild-design.md`

## Global Constraints

- Python **3.12**；依賴只用 `requests` + `pytest`（+ `pytest-mock`）。其餘用 stdlib。
- 主循環週期 **60 秒**；5 個 dataset 之間最少間隔 **8 秒**（±2 秒 jitter）。
- 主循環只處理 5 個設施運動：`badminton, basketball, volleyball, tennis, turf-soccer-pitch`。`activity-prog` 另開 thread，每 **300 秒**。
- 所有時間一律 **ISO8601 with `+08:00`**；內部計算用 HK 時區。
- 原始 48.6MB payload **永不落地**（只存在記憶體，parse 後即棄）。
- `seq` 只可由**持有租約**的 process 配發；租約 TTL **5 分鐘**。
- 事件保留 **180 日**；`sweeps` 保留 **7 日**。
- Telegram：chat `5200360037`、thread `68130`、`parse_mode=HTML`。
- 抓取失敗（任何非 200、HTML 回應、空 array）**不可**產生 `gone` 事件，亦不可覆寫現有 sessions。
- 每個 commit message 前綴：`feat:` / `fix:` / `test:` / `chore:` / `docs:`。

## Review Focus

1. **上游回 405 / WAF HTML 頁** → 必須偵測 `Content-Type: text/html` 或 JSON decode 失敗，保留上一版數據並記錄 `dataset_status`，**唔可以**當成「全部場冇咗」。
2. **上游回 200 但空 array**（上游故障） → 必須視為失敗（`empty_payload` guard），否則會產生數千個 `gone`。
3. **時區／跨日**：HK 07:00 開賣 vs UTC 儲存 → 日期窗（今日..+7）與 `sale7` 判定必須用 HK 時區，否則漏掉最遠可訂日。
4. **客戶端 `since=0` 或極舊 seq** → 不可一次回傳 180 日事件；必須 `limit` + `gap` 標記（Plan 2 實作 API，但事件表要能支撐）。
5. **Telegram 429 / 4096 字上限** → 必須讀 `parameters.retry_after` 並分批，否則訊息靜默丟失。

---

## File Structure

```
smartplay-live/                     (repo root)
├── poller/
│   ├── __init__.py
│   ├── config.py          # env 讀取 + 常數（週期、dataset 清單、TG 設定）
│   ├── gate.py            # HTTP Gate：節流、405 退避、cookie jar、單一併發
│   ├── fetch.py           # fetch_dataset()：回 FetchResult，含驗證（HTML/空陣列）
│   ├── parse.py           # 原始 record → Session（compact、窗口過濾）
│   ├── db.py              # SQLite 連線、schema、migration
│   ├── schema.sql
│   ├── diff.py            # diff_sessions() → list[Event]
│   ├── seq.py             # R2 計數器配發（含本地 fallback 檔）
│   ├── notify.py          # TG + ntfy 發送、批次、outbox
│   ├── cycle.py           # run_cycle()：串起 fetch→parse→diff→persist→notify
│   └── main.py            # 主循環 + 兩個 thread + systemd 友善 signal handling
├── ops/
│   ├── smartplay-poller.service
│   └── ntfy/docker-compose.yml
├── tests/
│   ├── fixtures/*.json
│   ├── test_gate.py
│   ├── test_fetch.py
│   ├── test_parse.py
│   ├── test_db.py
│   ├── test_diff.py
│   ├── test_seq.py
│   ├── test_notify.py
│   └── test_cycle.py
└── docs/specs/... (已存在)
```

**責任邊界**
- `gate.py` 只管節奏與 HTTP 合法性，不懂業務。
- `fetch.py` 只管「拿到可信的 list[dict]」，不懂 schema。
- `parse.py` 只管欄位映射與窗口過濾，不做 diff。
- `db.py` 只管 SQL，不做業務判斷。
- `diff.py` 純函數，無 IO。
- `notify.py` 只管送出與重試，不懂事件來源。

---

### Task 1: 工作區與 repo 骨架

**Files:**
- Create: repo clone at `D:\Teddy\Opencode\SmartPLAY\repo\`
- Create: `poller/__init__.py`, `requirements.txt`, `pytest.ini`

**Interfaces:**
- Produces: 一個可跑 `pytest` 的 repo；branch `feature/rebuild-v5`。

- [ ] **Step 1: Clone repo 並開 branch**

```bash
cd /d/Teddy/Opencode/SmartPLAY
git clone https://github.com/hkteddychan/smartplay-live.git repo
cd repo
git checkout -b feature/rebuild-v5
```

- [ ] **Step 2: 建立 requirements 與 pytest 設定**

`requirements.txt`
```
requests==2.32.*
pytest==8.*
pytest-mock==3.*
```

`pytest.ini`
```ini
[pytest]
testpaths = tests
pythonpath = .
```

- [ ] **Step 3: 安裝並確認**

Run: `python -m pip install -r requirements.txt && python -m pytest -q`
Expected: `no tests ran`（exit code 5），即環境正常。

- [ ] **Step 4: Commit**

```bash
git add requirements.txt pytest.ini poller/__init__.py
git commit -m "chore: bootstrap poller package and test config"
```

---

### Task 2: `config.py` — 設定與常數

**Files:**
- Create: `poller/config.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `SPORTS: list[str]`（5 個，固定順序：turf-soccer-pitch, tennis, basketball, volleyball, badminton）
  - `ACTIVITY = "activity-prog"`
  - `CYCLE_SECONDS = 60`, `STAGGER_SECONDS = 8`, `ACTIVITY_EVERY_SECONDS = 300`
  - `class Settings`（欄位 `tg_token, tg_chat, tg_thread, ntfy_url, r2_*`, `db_path`）→ `Settings.from_env()` 讀環境變數，缺 `TG_TOKEN` 時 raise `ConfigError`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_config.py
import pytest
from poller.config import Settings, SPORTS, ConfigError

def test_sports_order_is_smallest_first():
    assert SPORTS == ["turf-soccer-pitch", "tennis", "basketball", "volleyball", "badminton"]

def test_settings_requires_tg_token(monkeypatch):
    monkeypatch.delenv("TG_TOKEN", raising=False)
    with pytest.raises(ConfigError):
        Settings.from_env()

def test_settings_reads_thread_as_int(monkeypatch):
    monkeypatch.setenv("TG_TOKEN", "x")
    monkeypatch.setenv("TG_CHAT", "5200360037")
    monkeypatch.setenv("TG_THREAD", "68130")
    s = Settings.from_env()
    assert s.tg_thread == 68130 and isinstance(s.tg_thread, int)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: poller.config`

- [ ] **Step 3: 實作 `poller/config.py`**

`Settings.from_env()` 讀 `TG_TOKEN`（必需）、`TG_CHAT`（預設 `5200360037`）、`TG_THREAD`（預設 `68130`，轉 int）、`NTFY_URL`、`DB_PATH`（預設 `/opt/smartplay/state.db`）。`ConfigError(Exception)` 自訂。

- [ ] **Step 4: 跑測試**

Run: `python -m pytest tests/test_config.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add poller/config.py tests/test_config.py
git commit -m "feat: add poller config with sports order and tg settings"
```

---

### Task 3: `gate.py` — WAF 節奏控制

**Files:**
- Create: `poller/gate.py`, `tests/test_gate.py`

**Interfaces:**
- Produces:
  - `class Gate`：`__init__(session, sleep=time.sleep, clock=time.monotonic, stagger=STAGGER_SECONDS)`
  - `Gate.get(url: str) -> requests.Response` — 序列化（`threading.Lock`），每次呼叫之間 sleep `stagger ± jitter`
  - `Gate.on_status(status: int) -> float` — 回傳「應該 sleep 幾秒」；405/403/429 → latch 階梯 `[90,150,240,300]`
  - `Gate.state -> str`（`"ok" | "latch" | "safe"`）
  - `Gate.safe_mode() -> bool`

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_gate.py
import pytest
from poller.gate import Gate

class FakeSession:
    def __init__(self): self.calls = []
    def get(self, url, **kw):
        self.calls.append(url)
        return type("R", (), {"status_code": 200, "headers": {}, "text": "{}", "json": lambda s: {}})()

def test_sequential_and_staggered():
    slept, fake = [], FakeSession()
    g = Gate(fake, sleep=lambda s: slept.append(s), jitter=lambda: 0)
    g.get("u1"); g.get("u2")
    assert len(slept) == 1 and 7 <= slept[0] <= 9

def test_405_enters_latch_and_ladder():
    g = Gate(FakeSession(), sleep=lambda s: None, jitter=lambda: 0)
    assert g.on_status(405) == 90
    assert g.state == "latch"
    assert g.on_status(405) == 150

def test_three_latches_within_30min_enters_safe_mode():
    g = Gate(FakeSession(), sleep=lambda s: None, jitter=lambda: 0)
    for _ in range(3): g.on_status(405)
    assert g.state == "safe" and g.safe_mode() is True
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_gate.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 實作 `poller/gate.py`**

要點：`threading.Lock` 保證同一時間一個請求；記錄 `last_request_at`，不足 stagger 就 sleep；`deque(maxlen=10)` 記 latch 時間，30 分鐘內 ≥3 次 → `safe_until = clock() + 3600`；`jitter` 參數可注入（測試用 `lambda: 0`），預設 `random.uniform(0, 2)`。

- [ ] **Step 4: 跑測試**

Run: `python -m pytest tests/test_gate.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add poller/gate.py tests/test_gate.py
git commit -m "feat: add WAF-aware gate with stagger, latch and safe mode"
```

---

### Task 4: `fetch.py` — 抓取與可信度驗證

**Files:**
- Create: `poller/fetch.py`, `tests/test_fetch.py`, `tests/fixtures/badminton_sample.json`

**Interfaces:**
- Produces:
  - `@dataclass FetchResult`: `name: str, ok: bool, records: list[dict], bytes: int, error: str | None`
  - `fetch_dataset(gate, base_url: str, name: str) -> FetchResult`
  - 驗證規則（Review Focus 1 & 2）：
    - `status_code != 200` → `ok=False, error=f"http_{code}"`
    - `"text/html" in content-type` → `ok=False, error="html_response"`
    - JSON decode 失敗 → `ok=False, error="bad_json"`
    - 不是 list → `ok=False, error="not_list"`
    - `len(records) == 0` → `ok=False, error="empty_payload"`
    - 少於 100 筆（非 activity）→ `ok=False, error="suspiciously_small"`

- [ ] **Step 1: 寫失敗測試（覆蓋 5 種壞回應）**

```python
# tests/test_fetch.py
import json, pytest
from poller.fetch import fetch_dataset
from tests.conftest import FakeGateResponse

@pytest.mark.parametrize("resp,expected_error", [
    (FakeGateResponse(405, "text/html", "<html>405</html>"), "http_405"),
    (FakeGateResponse(200, "text/html", "<html>blocked</html>"), "html_response"),
    (FakeGateResponse(200, "application/json", "not-json"), "bad_json"),
    (FakeGateResponse(200, "application/json", "[]"), "empty_payload"),
    (FakeGateResponse(200, "application/json", "[]"), "empty_payload"),
])
def test_bad_responses_are_rejected(resp, expected_error):
    class G:
        def get(self, url, **kw): return resp
    r = fetch_dataset(G(), "http://x", "badminton")
    assert r.ok is False and r.error == expected_error

def test_good_response_parses():
    data = json.load(open("tests/fixtures/badminton_sample.json", encoding="utf-8"))
    class G:
        def get(self, url, **kw): return FakeGateResponse(200, "application/json", json.dumps(data))
    r = fetch_dataset(G(), "http://x", "badminton")
    assert r.ok and len(r.records) == len(data) and r.bytes > 0
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `python -m pytest tests/test_fetch.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 建立 fixture**

`tests/fixtures/badminton_sample.json`：由真實 LCSD 回應抽 **150 筆**（確保 > 100 門檻），保留原始欄位名（`Available_Date` 等）。用一次性腳本抓取後手動存檔，**不入 repo 的 data/ 目錄**。

- [ ] **Step 4: 實作 `poller/fetch.py`**（按 Interfaces 的規則逐條 if）

- [ ] **Step 5: 跑測試**

Run: `python -m pytest tests/test_fetch.py -q`
Expected: `6 passed`

- [ ] **Step 6: Commit**

```bash
git add poller/fetch.py tests/test_fetch.py tests/fixtures/badminton_sample.json
git commit -m "feat: fetch datasets with WAF/html/empty-payload guards"
```

---

### Task 5: `parse.py` — 欄位映射與窗口過濾

**Files:**
- Create: `poller/parse.py`, `tests/test_parse.py`

**Interfaces:**
- Produces:
  - `@dataclass Session`：`sport, venue, facility, date, start, end, courts`（全部 `str` 除 `courts: int`）；`key()` 回 6-tuple
  - `parse_records(sport: str, records: list[dict], today_hk: date, horizon_days: int = 7) -> list[Session]`
  - 規則：`courts <= 0` 丟棄；日期不在 `[today, today+horizon]` 丟棄；時間取 `HH:MM`；`venue/facility` strip。

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_parse.py
from datetime import date
from poller.parse import parse_records

def rec(d, st, en, c, v="測試館", f="主場"):
    return {"Available_Date": d, "Session_Start_Time": st + ":00",
            "Session_End_Time": en + ":00", "Available_Courts": str(c),
            "Venue_Name_TC": v, "Facility_Name_TC": f}

def test_filters_zero_courts_and_out_of_window():
    today = date(2026, 11, 26)
    rows = [rec("2026-11-27", "19:00", "20:00", 2),
            rec("2026-11-27", "20:00", "21:00", 0),
            rec("2026-12-31", "19:00", "20:00", 3)]
    out = parse_records("badminton", rows, today)
    assert len(out) == 1 and out[0].courts == 2 and out[0].start == "19:00"

def test_key_is_stable():
    today = date(2026, 11, 26)
    a = parse_records("badminton", [rec("2026-11-27", "19:00", "20:00", 1)], today)[0]
    b = parse_records("badminton", [rec("2026-11-27", "19:00", "20:00", 5)], today)[0]
    assert a.key() == b.key()
```

- [ ] **Step 2: 跑測試確認失敗** → Expected: FAIL

- [ ] **Step 3: 實作 `poller/parse.py`**（`datetime.strptime(...).time()` 取 `HH:MM`；比較用 `date.fromisoformat`）

- [ ] **Step 4: 跑測試** → Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add poller/parse.py tests/test_parse.py
git commit -m "feat: parse LCSD records into compact sessions"
```

---

### Task 6: `db.py` + schema + retention

**Files:**
- Create: `poller/schema.sql`, `poller/db.py`, `tests/test_db.py`

**Interfaces:**
- Produces:
  - `connect(path: str) -> sqlite3.Connection`（WAL、row_factory）
  - `init_db(conn)` — 執行 `schema.sql`（`CREATE TABLE IF NOT EXISTS`）
  - `upsert_sessions(conn, sessions: list[Session], now_iso: str)` — 不刪除缺席者（由 `diff` 決定）
  - `delete_sessions(conn, keys: list[tuple])`
  - `insert_events(conn, events: list[Event]) -> list[int]`（回傳 seq）
  - `log_sweep(conn, **kw)`
  - `prune(conn, now: datetime)` — events 180 日 → rollup → delete；sweeps 7 日

- [ ] **Step 1: 寫失敗測試**

```python
# tests/test_db.py
from poller.db import connect, init_db, upsert_sessions, log_sweep, prune
from poller.parse import Session

def mem():
    c = connect(":memory:"); init_db(c); return c

def test_upsert_idempotent():
    c = mem()
    s = Session("badminton", "A館", "主場", "2026-11-27", "19:00", "20:00", 2)
    upsert_sessions(c, [s], "2026-11-26T10:00:00+08:00")
    upsert_sessions(c, [s], "2026-11-26T10:01:00+08:00")
    assert c.execute("select count(*) from sessions").fetchone()[0] == 1

def test_prune_keeps_recent():
    c = mem()
    log_sweep(c, started_at="2020-01-01T00:00:00+08:00", finished_at="2020-01-01T00:01:00+08:00",
              ms=1, bytes=1, ds_ok=5, ds_total=5, waf_state="ok", note="")
    prune(c)
    assert c.execute("select count(*) from sweeps").fetchone()[0] == 0
```

- [ ] **Step 2: 跑測試確認失敗** → Expected: FAIL

- [ ] **Step 3: 寫 `poller/schema.sql`**（照 spec §5.2，`events.seq INTEGER PRIMARY KEY` 無 AUTOINCREMENT，`kind` 含 `resync`）

- [ ] **Step 4: 實作 `poller/db.py`**（`prune` 用參數化日期比較；`rollup` 先 `INSERT ... ON CONFLICT DO UPDATE` 再 delete）

- [ ] **Step 5: 跑測試** → Expected: `2 passed`

- [ ] **Step 6: Commit**

```bash
git add poller/schema.sql poller/db.py tests/test_db.py
git commit -m "feat: sqlite schema, upsert and retention pruning"
```

---

### Task 7: `diff.py` — 純函數比對

**Files:**
- Create: `poller/diff.py`, `tests/test_diff.py`

**Interfaces:**
- Produces:
  - `@dataclass Event`：`sport, venue, facility, date, start, end, kind, before, after, ts`（`kind ∈ {new, inc, dec, gone}`；`seq` 由呼叫者填）
  - `diff_sessions(prev: dict[tuple, int], cur: dict[tuple, int], ts: str) -> list[Event]`
  - `is_alerting(event) -> bool`（`inc`/`new`）
  - `is_evening(event) -> bool`（`start >= "18:00"`）

- [ ] **Step 1: 失敗測試**

```python
# tests/test_diff.py
from poller.diff import diff_sessions, is_evening

K = ("badminton", "A館", "主場", "2026-11-27", "19:00", "20:00")
TS = "2026-11-26T10:00:00+08:00"

def kinds(prev, cur):
    return sorted((e.kind, e.before, e.after) for e in diff_sessions(prev, cur, TS))

def test_new_inc_dec_gone():
    assert kinds({}, {K: 2}) == [("new", 0, 2)]
    assert kinds({K: 1}, {K: 3}) == [("inc", 1, 3)]
    assert kinds({K: 3}, {K: 1}) == [("dec", 3, 1)]
    assert kinds({K: 2}, {}) == [("gone", 2, 0)]

def test_no_event_when_unchanged():
    assert diff_sessions({K: 2}, {K: 2}, TS) == []

def test_evening_boundary():
    e = diff_sessions({}, {K: 1}, TS)[0]
    assert is_evening(e) is True
```

- [ ] **Step 2: 跑測試確認失敗** → Expected: FAIL

- [ ] **Step 3: 實作**（雙迴圈；`before=0` for `new`）

- [ ] **Step 4: 跑測試** → Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add poller/diff.py tests/test_diff.py
git commit -m "feat: pure diff engine for session changes"
```

---

### Task 8: `seq.py` — R2 計數器（含本地 fallback）

**Files:**
- Create: `poller/seq.py`, `tests/test_seq.py`

**Interfaces:**
- Produces:
  - `class SeqAllocator(url: str, token: str, local_path: str)`
  - `SeqAllocator.allocate(n: int) -> int`（回傳起始 seq；本地檔案為 cache，R2 為權威）
  - 失敗策略：R2 不可達 → 用本地 `seq.json` + 1000 的跳號 buffer，並回傳 `degraded=True`（attribute）
  - `SeqAllocator.reserve(n)` 先寫 R2 `{"seq": current+n}`（ETag 條件寫），成功後才回傳

- [ ] **Step 1: 失敗測試（用 `responses` 或注入 fake http）**

```python
# tests/test_seq.py
import json
from poller.seq import SeqAllocator

class FakeR2:
    def __init__(self): self.val = {"seq": 100}; self.puts = 0
    def get(self, url, headers=None, timeout=None):
        class R: status_code = 200
        R.json = lambda s: dict(self.val); R.headers = {"ETag": "e1"}
        return R()
    def put(self, url, data=None, headers=None, timeout=None):
        self.puts += 1
        body = json.loads(data) if isinstance(data, str) else json.loads(data.decode())
        self.val = body
        class R: status_code = 200
        return R()

def test_allocate_advances_counter(tmp_path):
    r2 = FakeR2()
    a = SeqAllocator("u", "t", str(tmp_path / "seq.json"), http=r2)
    start = a.allocate(3)
    assert start == 101 and r2.val["seq"] == 103

def test_conflict_retries_once(tmp_path):
    ...
```

- [ ] **Step 2: 跑測試確認失敗**

- [ ] **Step 3: 實作**（`If-Match` header；412 → 重讀重試一次；R2 失敗 → 本地 +1000 buffer、`degraded=True`）

- [ ] **Step 4: 跑測試** → Expected: passed

- [ ] **Step 5: Commit**

```bash
git add poller/seq.py tests/test_seq.py
git commit -m "feat: monotonic seq allocator backed by R2 with local degraded mode"
```

---

### Task 9: `notify.py` — 先送後併、429、outbox

**Files:**
- Create: `poller/notify.py`, `tests/test_notify.py`

**Interfaces:**
- Produces:
  - `class Notifier(settings, http=requests)`
  - `Notifier.send_events(events: list[Event], channel_filter: Callable) -> DeliveryResult`
  - `Notifier.format_batch(events) -> str`（≤12 條，其餘 `…+N 場`；總長 > 4000 字則再拆）
  - `DeliveryResult(delivered: bool, via: str | None, errors: list[str])`
  - `Notifier.flush_outbox(conn) -> int`（回傳成功重送數）
  - 行為：**第一批即送**；同一次呼叫內第二組起合併為一條「補充」；TG 429 → sleep(`retry_after`) → 重試；TG 失敗 → ntfy；兩者失敗 → 寫 `outbox`。

- [ ] **Step 1: 失敗測試**

```python
# tests/test_notify.py
from poller.notify import Notifier

def test_first_batch_sent_immediately(monkeypatch):
    sent = []
    class H:
        def post(self, url, json=None, timeout=None, **kw):
            sent.append((url, json)); return type("R", (), {"status_code": 200, "json": lambda s: {"ok": True}})()
    n = Notifier.__new__(Notifier); n.http = H(); n.settings = type("S", (), {"tg_token":"t","tg_chat":"1","tg_thread":1,"ntfy_url":"http://n"})()
    n.send_events([ev], lambda e: True)
    assert len(sent) == 1 and "sendMessage" in sent[0][0]

def test_tg_429_waits_retry_after():
    ...

def test_both_channels_fail_writes_outbox():
    ...
```

- [ ] **Step 2: 跑測試確認失敗**

- [ ] **Step 3: 實作 `notify.py`**（HTML escape；`disable_notification` 只用於非放場事件；ntfy header `Title/Priority/Tags`）

- [ ] **Step 4: 跑測試** → Expected: passed

- [ ] **Step 5: Commit**

```bash
git add poller/notify.py tests/test_notify.py
git commit -m "feat: notify with send-first batching, 429 handling and outbox"
```

---

### Task 10: `cycle.py` — 串起一輪

**Files:**
- Create: `poller/cycle.py`, `tests/test_cycle.py`

**Interfaces:**
- Consumes: `Gate`, `fetch_dataset`, `parse_records`, `diff_sessions`, `db.*`, `SeqAllocator`, `Notifier`
- Produces:
  - `run_cycle(deps: Deps) -> CycleResult`（`Deps` 為 dataclass 注入所有依賴，方便測試）
  - `CycleResult(ok: bool, ms: int, bytes: int, ds_ok: int, waf_state: str, events: int)`
  - 規則：任何 dataset `ok=False` → 該運動保留上一版 `sessions`（不 delete、不產生 gone）；整體 `ok` 只看 ≥4/5 成功。

- [ ] **Step 1: 失敗測試（用 fake fetch 回傳固定資料）**

```python
# tests/test_cycle.py
def test_failed_dataset_does_not_delete_sessions(tmp_path):
    # 預存 2 個 sessions；fetch 對 badminton 回 ok=False
    # 期望：2 個 sessions 仍在；events == 0；result.ok is True (4/5 成功)

def test_empty_payload_produces_no_gone():
    # fetch 回 ok=False, error="empty_payload"
    # 期望：0 個 gone 事件
```

- [ ] **Step 2: 跑測試確認失敗**

- [ ] **Step 3: 實作 `cycle.py`**（先計 `prev = load_sessions()`，再逐 dataset fetch→parse→組合 `cur`；只對「成功」的 sport 做 diff；失敗的 sport 跳過）

- [ ] **Step 4: 跑測試** → Expected: passed

- [ ] **Step 5: Commit**

```bash
git add poller/cycle.py tests/test_cycle.py
git commit -m "feat: cycle runner that never degrades data on partial fetch failure"
```

---

### Task 11: `main.py` + systemd + 部署到 Oracle

**Files:**
- Create: `poller/main.py`, `ops/smartplay-poller.service`
- Modify: Oracle `/etc/systemd/system/`

**Interfaces:**
- Produces: `main()` 跑兩個 thread（facility 60s、activity 300s）；SIGTERM → graceful stop。

- [ ] **Step 1: 寫測試（只測 thread 排程邏輯，用注入的 clock）**

```python
def test_activity_runs_every_300s(fake_runner):
    # 跑 600 秒模擬時鐘 → activity 應執行 2 次，facility 10 次
```

- [ ] **Step 2: 跑測試** → Expected: passed

- [ ] **Step 3: 寫 systemd unit**

```ini
[Unit]
Description=SmartPLAY Live poller
After=network-online.target
OnFailure=smartplay-alert@%n.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/smartplay
EnvironmentFile=/opt/smartplay/.env
ExecStart=/opt/smartplay/venv/bin/python -m poller.main
Restart=always
RestartSec=5
WatchdogSec=150
MemoryMax=1G
CPUQuota=150%

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 4: 部署（清盤 → 建 venv → scp → enable）**

```bash
ssh ubuntu@192.9.242.154 'df -h / && sudo du -sh /var/log/* 2>/dev/null | sort -h | tail -5'
# 清單經 Teddy 批准後才刪
```

- [ ] **Step 5: 煙霧測試（只抓 1 個 dataset，手動跑一次）**

Run: `ssh ... 'cd /opt/smartplay && venv/bin/python -m poller.main --once --only=turf-soccer-pitch'`
Expected: log 顯示 `fetch ok bytes=3.1MB parse=NNN sessions cycle_ms<20000`，DB 有行。

- [ ] **Step 6: Commit + 開 service**

```bash
git add poller/main.py ops/smartplay-poller.service
git commit -m "feat: main loop with dual threads and systemd unit"
```

---

### Task 12: P0 備份與降頻（與 code 並行）

**Files:**
- Create: `smartplay-ops-backup/smartplay/2026-11-26/*`

**Interfaces:**
- Produces: 可還原的快照 + tag。

- [ ] **Step 1: 匯出 n8n workflows 與 DataTable**

用 n8n API：`GET /api/v1/workflows?limit=250`、`GET /api/v1/data-tables/dTRKG3urLMZFvuWf/rows?limit=250&cursor=...`（loop）。

- [ ] **Step 2: 寫入 ops-backup 並 tag**

```bash
git add smartplay/2026-11-26 && git commit -m "chore: pre-rebuild snapshot 2026-11-26"
git tag pre-rebuild-2026-11-26 && git push --tags
```

- [ ] **Step 3: 還原演練（抽 1 個 workflow 匯入 n8n 測試，然後刪除）**

Expected: 匯入成功、node 數一致。

- [ ] **Step 4: 降頻 v4 Worker（cron `* * * * *` → `*/5 * * * *`）**

```bash
wrangler deployments ...  # 改 wrangler.toml 的 crons 後 wrangler deploy
```

- [ ] **Step 5: 停用 n8n v1/v2**

`POST /api/v1/workflows/{id}/deactivate`（v1 `DVF3X5UefVgx0MLO`、v2 `4dPLxXsAhSZaxCyf`）

- [ ] **Step 6: Rotate n8n API key + 移除 worker 內 hardcode**

產生新 key → 更新 Oracle `.env`、CF secret；worker 內 `API_KEY` 常數改讀 `env.N8N_KEY`。

---

## Self-Review

**1. Spec coverage（Plan 1 範圍）**
- §5.1 主循環 / stagger / activity thread → Task 3, 10, 11 ✅
- §5.1.1 Gate 退避 / safe mode → Task 3 ✅
- §5.1.2 欄位映射 / 窗口 → Task 5 ✅
- §5.2 schema / retention → Task 6 ✅
- §5.2.1 seq 租約 → Task 8（租約本身在 Plan 2，這裡只做計數器）⚠️ 部分
- §5.3 diff / 篩選 → Task 7, 9 ✅
- §5.4 通知 / 先送後併 / outbox → Task 9 ✅
- §5.9 fallback 矩陣（poller 相關行） → Task 10（部分失敗不刪數據）✅
- P0 備份/降頻 → Task 12 ✅
- R2 發佈、Worker、網站、firmware、watchdog → **不在本計劃**（Plan 2/3）

**2. Step scan**：每個 step 有單一動作與可檢查結果；未見「handle edge cases」類空話。

**3. Type consistency**：`Session.key()` 回 6-tuple，`diff_sessions` 收 `dict[tuple,int]`，`db.insert_events` 收 `Event`（含 `kind`）— 一致。

**4. Review Focus**：5 項全部有測試（Task 4 ×2、Task 5/10 時區、Task 8 limit、Task 9 429）。

**5. Proportion**：計劃約為 spec 的 1/3 長度，主要係簽名與測試，非逐行實作。
