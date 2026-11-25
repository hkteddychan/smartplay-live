from poller.db import connect, init_db, load_sessions, upsert_sessions, log_sweep, prune
from poller.parse import Session


def mem():
    c = connect(":memory:"); init_db(c); return c


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
