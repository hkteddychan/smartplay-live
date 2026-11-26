import sqlite3
from contextlib import contextmanager

import pytest

import poller.db as db
from poller.db import (
    connect,
    fetch_unsent_sale7,
    init_db,
    load_sessions,
    log_sweep,
    mark_sale7_notified,
    prune,
    upsert_activities,
    upsert_sessions,
)
from poller.parse import Session


def mem():
    c = connect(":memory:"); init_db(c); return c


def add_event(c, seq, kind, venue="A館", ts="2026-11-26T07:00:00+08:00",
              notified_tg=0, notified_ntfy=0):
    c.execute(
        'INSERT INTO events (seq, ts, sport, venue, facility, date, start, "end", '
        "kind, before, \"after\", notified_tg, notified_ntfy) "
        "VALUES (?, ?, 'badminton', ?, '1號場', '2026-11-27', '19:00', '20:00', ?, 0, 1, ?, ?)",
        (seq, ts, venue, kind, notified_tg, notified_ntfy),
    )
    c.commit()


def marks(c):
    return {
        row["seq"]: (row["notified_tg"], row["notified_ntfy"])
        for row in c.execute("SELECT seq, notified_tg, notified_ntfy FROM events ORDER BY seq")
    }


def test_upsert_idempotent():
    c = mem()
    s = Session("badminton", "A館", "主場", "2026-11-27", "19:00", "20:00", 2)
    upsert_sessions(c, [s], "2026-11-26T10:00:00+08:00")
    upsert_sessions(c, [s], "2026-11-26T10:01:00+08:00")
    assert c.execute("select count(*) from sessions").fetchone()[0] == 1


def test_load_sessions_round_trips_diff_keys():
    """R40: keys use the same ISO date text as upsert, ready for diff()."""
    c = mem()
    s = Session("badminton", "A館", "主場", "2026-11-27", "19:00", "20:00", 2)
    upsert_sessions(c, [s], "2026-11-26T10:00:00+08:00")
    assert load_sessions(c) == {
        ("badminton", "A館", "主場", "2026-11-27", "19:00", "20:00"): 2
    }
    assert load_sessions(mem()) == {}


def test_prune_keeps_recent():
    c = mem()
    log_sweep(c, started_at="2020-01-01T00:00:00+08:00", finished_at="2020-01-01T00:01:00+08:00",
              ms=1, bytes=1, ds_ok=5, ds_total=5, waf_state="ok", note="")
    prune(c)
    assert c.execute("select count(*) from sweeps").fetchone()[0] == 0


# --- R46: sale7 summary data helpers ----------------------------------------


def test_fetch_unsent_sale7_returns_only_unsent_sale7_rows():
    c = mem()
    add_event(c, 1, "sale7")
    add_event(c, 2, "sale7", notified_tg=1)
    add_event(c, 3, "new")
    add_event(c, 4, "sale7", notified_ntfy=1)
    add_event(c, 5, "sale7", venue="B館")

    rows = fetch_unsent_sale7(c)

    assert [row["seq"] for row in rows] == [1, 5]
    assert [row["venue"] for row in rows] == ["A館", "B館"]


def test_mark_sale7_notified_marks_exact_rows_and_channel():
    c = mem()
    add_event(c, 1, "sale7")
    add_event(c, 2, "sale7")
    add_event(c, 3, "sale7")
    add_event(c, 4, "new")

    mark_sale7_notified(c, [1, 3], "tg")

    assert marks(c) == {1: (1, 0), 2: (0, 0), 3: (1, 0), 4: (0, 0)}

    mark_sale7_notified(c, [3], "ntfy")
    assert marks(c) == {1: (1, 0), 2: (0, 0), 3: (1, 1), 4: (0, 0)}

    # An unrelated event is never marked, even if its seq is passed in.
    mark_sale7_notified(c, [4], "tg")
    assert marks(c)[4] == (0, 0)


def test_mark_sale7_notified_accepts_both_channels_and_is_a_noop_for_empty():
    c = mem()
    add_event(c, 1, "sale7")
    mark_sale7_notified(c, [1], "tg+ntfy")
    assert marks(c) == {1: (1, 1)}

    mark_sale7_notified(c, [], "tg")
    mark_sale7_notified(c, [1], "unknown")
    assert marks(c) == {1: (1, 1)}


def test_mark_sale7_notified_chunks_large_bursts_under_the_parameter_limit():
    c = mem()
    seqs = list(range(1, 1201))
    c.executemany(
        'INSERT INTO events (seq, ts, sport, venue, facility, date, start, "end", '
        "kind, before, \"after\") VALUES "
        "(?, '2026-11-26T07:00:00+08:00', 'badminton', 'A館', '1號場', "
        "'2026-11-27', '19:00', '20:00', 'sale7', 0, 1)",
        [(seq,) for seq in seqs],
    )
    c.commit()

    statements = []
    c.set_trace_callback(statements.append)
    try:
        marked = mark_sale7_notified(c, seqs, "tg")
    finally:
        c.set_trace_callback(None)

    updates = [sql for sql in statements if sql.lstrip().upper().startswith("UPDATE")]
    assert marked == 1200
    assert len(updates) == 3  # 500 + 500 + 200
    assert c.execute(
        "SELECT COUNT(*) FROM events WHERE notified_tg = 1"
    ).fetchone()[0] == 1200


# --- activity snapshot (Task 11 thread B) -----------------------------------


@contextmanager
def _trace(conn):
    """Collect the SQL statements executed inside the ``with`` block.

    A trace callback is the cheapest way to prove a no-op: the test counts
    real DELETE/INSERT statements, not just the returned row count.
    """
    statements = []
    conn.set_trace_callback(statements.append)
    try:
        yield statements
    finally:
        conn.set_trace_callback(None)


def _activity_writes(statements):
    """Only the statements that touch the snapshot table, normalised."""
    return [
        sql.strip().lower()
        for sql in statements
        if sql.strip().lower().startswith(
            ("delete from activities", "insert into activities")
        )
    ]


def test_empty_activity_payload_is_a_noop_without_committing():
    c = mem()
    with _trace(c) as statements:
        assert upsert_activities(c, [], "2026-11-26T10:00:00+08:00") == 0
    assert statements == []


def test_upsert_activities_is_a_snapshot_and_keeps_first_seen():
    c = mem()
    t1 = "2026-11-26T10:00:00+08:00"
    t2 = "2026-11-26T10:05:00+08:00"

    stored = upsert_activities(
        c,
        [
            {"ACTIVITY_NO": "A1", "TC_PGM_NAME": "舊名"},
            {"ACTIVITY_NO": "A2", "TC_PGM_NAME": "另一個"},
            {"TC_PGM_NAME": "沒有編號"},  # malformed: skipped
        ],
        t1,
    )

    assert stored == 2
    assert c.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 2

    # I4: 50% of the stored snapshot is the floor; keep both rows here.
    stored = upsert_activities(
        c,
        [
            {"ACTIVITY_NO": "A1", "TC_PGM_NAME": "新名"},
            {"ACTIVITY_NO": "A2", "TC_PGM_NAME": "另一個"},
        ],
        t2,
    )

    assert stored == 2
    rows = c.execute(
        "SELECT activity_no, payload, first_seen, last_seen FROM activities "
        "ORDER BY activity_no"
    ).fetchall()
    assert [row["activity_no"] for row in rows] == ["A1", "A2"]
    assert rows[0]["first_seen"] == t1
    assert rows[0]["last_seen"] == t2
    assert "新名" in rows[0]["payload"] and "舊名" not in rows[0]["payload"]


def test_unchanged_activity_snapshot_performs_no_delete_or_insert():
    """R51: the 15MB snapshot must not be rewritten when nothing changed."""
    c = mem()
    t1 = "2026-11-26T10:00:00+08:00"
    t2 = "2026-11-26T10:15:00+08:00"
    records = [
        {"ACTIVITY_NO": "A1", "TC_PGM_NAME": "測試"},
        {"ACTIVITY_NO": "A2", "TC_PGM_NAME": "另一個"},
    ]
    assert upsert_activities(c, records, t1) == 2

    with _trace(c) as statements:
        stored = upsert_activities(c, [dict(record) for record in records], t2)

    assert stored == 0
    assert _activity_writes(statements) == []
    assert c.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 2

    meta = c.execute(
        "SELECT hash, updated_at FROM activity_meta WHERE id = 1"
    ).fetchone()
    assert meta["updated_at"] == t2
    assert len(meta["hash"]) == 64


def test_changed_activity_snapshot_rewrites_exactly_once():
    """R51: a real change is one DELETE plus one INSERT pass."""
    c = mem()
    t1 = "2026-11-26T10:00:00+08:00"
    t2 = "2026-11-26T10:15:00+08:00"
    assert upsert_activities(c, [{"ACTIVITY_NO": "A1", "TC_PGM_NAME": "舊"}], t1) == 1

    with _trace(c) as statements:
        stored = upsert_activities(
            c,
            [
                {"ACTIVITY_NO": "A1", "TC_PGM_NAME": "新"},
                {"ACTIVITY_NO": "B2", "TC_PGM_NAME": "新增"},
            ],
            t2,
        )

    assert stored == 2
    writes = _activity_writes(statements)
    assert sum(sql.startswith("delete from activities") for sql in writes) == 1
    assert sum(sql.startswith("insert into activities") for sql in writes) == 2

    rows = c.execute(
        'SELECT activity_no, first_seen, last_seen FROM activities ORDER BY activity_no'
    ).fetchall()
    assert [row["activity_no"] for row in rows] == ["A1", "B2"]
    assert rows[0]["first_seen"] == t1          # survives the rewrite
    assert rows[1]["first_seen"] == t2
    assert all(row["last_seen"] == t2 for row in rows)

    meta = c.execute(
        "SELECT hash, updated_at FROM activity_meta WHERE id = 1"
    ).fetchone()
    assert meta["updated_at"] == t2


def test_activity_hash_ignores_upstream_row_order():
    """R51: re-ordering the same payload must not look like a change."""
    c = mem()
    t1 = "2026-11-26T10:00:00+08:00"
    t2 = "2026-11-26T10:15:00+08:00"
    first = {"ACTIVITY_NO": "A1", "TC_PGM_NAME": "甲"}
    second = {"ACTIVITY_NO": "B2", "TC_PGM_NAME": "乙"}
    assert upsert_activities(c, [first, second], t1) == 2

    with _trace(c) as statements:
        stored = upsert_activities(c, [second, first], t2)

    assert stored == 0
    assert _activity_writes(statements) == []


# --- I4: activity minimum guard ---------------------------------------------


def _activity_ids(count):
    return [{"ACTIVITY_NO": f"A{index}"} for index in range(count)]


def test_activity_snapshot_below_half_is_rejected_and_keeps_the_old_one():
    c = mem()
    t1 = "2026-11-26T10:00:00+08:00"
    t2 = "2026-11-26T10:15:00+08:00"
    assert upsert_activities(c, _activity_ids(10), t1) == 10
    logs = []

    stored = upsert_activities(c, _activity_ids(3), t2, log=logs.append)

    assert stored == 0
    assert c.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 10
    assert any("suspiciously_small" in line for line in logs)


def test_activity_snapshot_at_half_is_accepted():
    c = mem()
    t1 = "2026-11-26T10:00:00+08:00"
    t2 = "2026-11-26T10:15:00+08:00"
    assert upsert_activities(c, _activity_ids(10), t1) == 10

    assert upsert_activities(c, _activity_ids(5), t2) == 5
    assert c.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 5


# --- R56: first-start connection race ---------------------------------------


class _FakeConn:
    """Records pragmas so their order can be asserted without a real file."""

    def __init__(self):
        self.statements = []
        self.row_factory = None
        self.closed = False

    def execute(self, sql, *args):
        self.statements.append(sql)
        return self

    def close(self):
        self.closed = True


def test_connect_sets_busy_timeout_before_switching_to_wal(monkeypatch):
    """R56: the timeout must exist before the WAL switch can contend."""
    fake = _FakeConn()
    monkeypatch.setattr(db.sqlite3, "connect", lambda path: fake)

    db.connect("state.db")

    pragmas = [sql for sql in fake.statements if sql.upper().startswith("PRAGMA")]
    assert pragmas[0] == f"PRAGMA busy_timeout={db.BUSY_TIMEOUT_MS}"
    assert any("journal_mode=WAL" in sql for sql in pragmas)


def test_connect_retries_a_locked_database_then_succeeds(monkeypatch):
    """Both workers may race the WAL switch on a brand-new state.db."""
    real_connect = sqlite3.connect
    calls = []
    sleeps = []

    def flaky(path):
        calls.append(path)
        if len(calls) < 3:
            raise sqlite3.OperationalError("database is locked")
        return real_connect(":memory:")

    monkeypatch.setattr(db.sqlite3, "connect", flaky)

    conn = db.connect("state.db", sleep=sleeps.append)

    assert len(calls) == 3
    assert sleeps == [0.2, 0.5]
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == db.BUSY_TIMEOUT_MS


def test_connect_gives_up_after_three_retries(monkeypatch):
    calls = []
    sleeps = []

    def always_locked(path):
        calls.append(path)
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(db.sqlite3, "connect", always_locked)

    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        db.connect("state.db", sleep=sleeps.append)

    assert len(calls) == 4  # initial attempt + 3 retries
    assert sleeps == [0.2, 0.5, 1.0]


def test_connect_does_not_retry_unrelated_operational_errors(monkeypatch):
    calls = []

    def broken(path):
        calls.append(path)
        raise sqlite3.OperationalError("unable to open database file")

    monkeypatch.setattr(db.sqlite3, "connect", broken)

    with pytest.raises(sqlite3.OperationalError, match="unable to open"):
        db.connect("state.db", sleep=lambda _: pytest.fail("must not back off"))

    assert calls == ["state.db"]


def test_connect_backoff_prefers_the_stop_event_wait(monkeypatch):
    """A worker passes its stop_event; backoff must go through its wait()."""
    real_connect = sqlite3.connect
    calls = []
    waits = []

    class _Event:
        def wait(self, timeout):
            waits.append(timeout)
            return False

    def flaky(path):
        calls.append(path)
        if len(calls) < 2:
            raise sqlite3.OperationalError("database is locked")
        return real_connect(":memory:")

    monkeypatch.setattr(db.sqlite3, "connect", flaky)

    db.connect("state.db", stop_event=_Event())

    assert len(calls) == 2
    assert waits == [0.2]
