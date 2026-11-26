-- SmartPLAY poller schema (spec §5.2). All timestamps ISO8601 +08:00.
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS sessions (
  sport TEXT NOT NULL, venue TEXT NOT NULL, facility TEXT NOT NULL,
  date TEXT NOT NULL, start TEXT NOT NULL, "end" TEXT NOT NULL,
  courts INTEGER NOT NULL,
  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
  released_at TEXT,                 -- 最近一次「由 0 變 >0」時間
  PRIMARY KEY (sport, venue, facility, date, start, "end")
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY,          -- 由 R2 meta/seq.json 配發，唔用 AUTOINCREMENT
  ts TEXT NOT NULL,                 -- ISO8601 +08:00
  sport TEXT NOT NULL, venue TEXT NOT NULL, facility TEXT NOT NULL,
  date TEXT NOT NULL, start TEXT NOT NULL, "end" TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('new','inc','dec','gone','sale7','resync')),
  before INTEGER, after INTEGER,
  notified_tg INTEGER DEFAULT 0, notified_ntfy INTEGER DEFAULT 0,
  notify_err TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind, ts);

CREATE TABLE IF NOT EXISTS sweeps (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT, finished_at TEXT, ms INTEGER,
  bytes INTEGER, ds_ok INTEGER, ds_total INTEGER,
  waf_state TEXT, note TEXT
);

CREATE TABLE IF NOT EXISTS dataset_status (
  name TEXT PRIMARY KEY, last_ok TEXT, last_err TEXT,
  err_streak INTEGER DEFAULT 0, bytes INTEGER,
  records INTEGER                   -- I3: last successful payload row count
);

CREATE TABLE IF NOT EXISTS daily_rollup (
  day TEXT, sport TEXT, venue TEXT, kind TEXT, n INTEGER,
  PRIMARY KEY(day, sport, venue, kind)
);

CREATE TABLE IF NOT EXISTS activities (   -- activity-prog 快照（獨立 900s thread）
  activity_no TEXT PRIMARY KEY,
  payload TEXT NOT NULL,             -- 原始 JSON（搜尋 tab 用）
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS activity_meta (  -- R51: 快照 hash，避免每 tick 重寫 15MB
  id INTEGER PRIMARY KEY CHECK(id = 1),
  hash TEXT,
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS outbox (           -- 通知失敗重試隊列
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seq_from INTEGER, seq_to INTEGER, channel TEXT,
  payload TEXT, attempts INTEGER DEFAULT 0,
  next_try TEXT, last_error TEXT
);
