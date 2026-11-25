# tests/test_cycle.py
"""Task 10 — cycle.py: one 60s round, end to end.

Every dependency is injected through ``Deps`` (brief): the gate, fetcher,
parser, allocator and notifier are fakes; SQLite is a real in-memory DB so
the persistence side is exercised for real. No sleeping, no clock reads in
the tested path.
"""

from datetime import date, datetime, timedelta, timezone

import pytest

from poller import db
from poller.config import SPORTS
from poller.cycle import CycleResult, Deps, run_cycle
from poller.fetch import FetchResult
from poller.gate import GateBackoff
from poller.notify import DeliveryResult
from poller.parse import Session, parse_records

HK = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 26, 10, 0, tzinfo=HK)  # outside the 06:45–08:00 window
TODAY = NOW.date()


# --- fakes -----------------------------------------------------------------


class FakeGate:
    def __init__(self, state="ok"):
        self.state = state


class FakeFetcher:
    """Fixed payload per sport; per-sport failures or GateBackoff raises."""

    def __init__(self, payload=None, fail=None, raise_for=None):
        self.payload = payload or {}
        self.fail = fail or {}
        self.raise_for = raise_for or {}
        self.calls = []

    def __call__(self, gate, base_url, name):
        self.calls.append(name)
        if name in self.raise_for:
            raise self.raise_for[name]
        if name in self.fail:
            return FetchResult(name, False, [], 0, self.fail[name])
        records = self.payload.get(name, [])
        return FetchResult(name, True, records, 100, None)


class FakeAllocator:
    def __init__(self, start=1, degraded=False):
        self.next = start
        self.degraded = degraded
        self.calls = []

    def allocate(self, n):
        self.calls.append(n)
        first = self.next
        self.next += n
        return first


class FakeNotifier:
    def __init__(self, delivered=True, via="tg", sent=None, parked=None, errors=None):
        self.delivered = delivered
        self.via = via
        self.sent = sent
        self.parked = parked
        self.errors = errors or []
        self.calls = 0
        self.selected = []

    def send_events(self, events, channel_filter):
        self.calls += 1
        self.selected = [e for e in events if channel_filter(e)]
        seqs = [e.seq for e in self.selected]
        sent = seqs if self.sent is None and self.delivered else (self.sent or [])
        parked = seqs if self.parked is None and not self.delivered else (self.parked or [])
        return DeliveryResult(
            self.delivered,
            self.via if self.delivered else None,
            list(self.errors),
            list(sent),
            list(parked),
        )


class FakeClock:
    def __init__(self, *values):
        self.values = list(values)
        self.i = 0

    def __call__(self):
        value = self.values[min(self.i, len(self.values) - 1)]
        self.i += 1
        return value


# --- helpers ---------------------------------------------------------------


def mem():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def rec(day, start="19:00", end="20:00", venue="A館", facility="1號場", courts=1):
    return {
        "Available_Courts": courts,
        "Available_Date": day.isoformat(),
        "Venue_Name_TC": venue,
        "Facility_Location_Name_TC": facility,
        "Session_Start_Time": start,
        "Session_End_Time": end,
    }


def seed(conn, *sessions):
    db.upsert_sessions(conn, list(sessions), NOW.isoformat())


def make_deps(conn=None, fetcher=None, allocator=None, notifier=None, now=NOW,
              gate=None, clock=None, parse=None):
    return Deps(
        conn=conn if conn is not None else mem(),
        gate=gate or FakeGate(),
        allocator=allocator or FakeAllocator(),
        notifier=notifier or FakeNotifier(),
        now_hk=now,
        fetch=fetcher or FakeFetcher(),
        clock=clock or FakeClock(0.0, 0.0),
        **({"parse": parse} if parse is not None else {}),
    )


def event_rows(conn):
    return conn.execute(
        'SELECT seq, sport, venue, facility, date, start, "end", kind, '
        "before, after, notified_tg, notified_ntfy FROM events ORDER BY seq"
    ).fetchall()


def sweep(conn):
    return conn.execute("SELECT * FROM sweeps ORDER BY id DESC LIMIT 1").fetchone()


# --- R21 / brief: a broken dataset never degrades data ----------------------


def test_failed_dataset_does_not_delete_sessions():
    conn = mem()
    seed(
        conn,
        Session("badminton", "A館", "1號場", TODAY, "19:00", "20:00", 2),
        Session("badminton", "A館", "2號場", TODAY, "20:00", "21:00", 1),
    )
    result = run_cycle(make_deps(conn=conn, fetcher=FakeFetcher(fail={"badminton": "empty_payload"})))

    assert conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE sport = 'badminton'"
    ).fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    assert result.events == 0
    assert result.ds_ok == 4 and result.ds_total == 5
    assert result.ok is False          # R41: only 5/5 is ok
    assert result.degraded is True     # R41: 4/5 is degraded


def test_empty_payload_produces_no_gone():
    conn = mem()
    seed(conn, Session("badminton", "A館", "1號場", TODAY, "19:00", "20:00", 1))
    fetcher = FakeFetcher(fail={sport: "empty_payload" for sport in SPORTS})
    result = run_cycle(make_deps(conn=conn, fetcher=fetcher))

    assert [r["kind"] for r in event_rows(conn)] == []
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert result.events == 0
    assert result.ds_ok == 0
    assert result.ok is False and result.degraded is False


def test_only_successful_sports_are_diffed():
    conn = mem()
    seed(
        conn,
        Session("badminton", "A館", "1號場", TODAY, "19:00", "20:00", 1),
        Session("tennis", "B館", "1號場", TODAY, "19:00", "20:00", 1),
    )
    result = run_cycle(make_deps(
        conn=conn, fetcher=FakeFetcher(fail={"badminton": "http_500"})))

    assert [(r["sport"], r["kind"]) for r in event_rows(conn)] == [("tennis", "gone")]
    assert conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE sport = 'badminton'"
    ).fetchone()[0] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE sport = 'tennis'"
    ).fetchone()[0] == 0
    assert result.events == 1


def test_parse_failure_is_isolated_per_dataset():
    conn = mem()
    seed(
        conn,
        Session("badminton", "A館", "1號場", TODAY, "19:00", "20:00", 2),
        Session("badminton", "A館", "2號場", TODAY, "20:00", "21:00", 1),
    )

    def broken_parse(sport, records, today_hk, horizon_days=7):
        if sport == "badminton":
            raise ValueError("bad row")
        return parse_records(sport, records, today_hk, horizon_days)

    result = run_cycle(make_deps(conn=conn, parse=broken_parse))

    assert conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE sport = 'badminton'"
    ).fetchone()[0] == 2
    assert event_rows(conn) == []
    assert result.ds_ok == 4 and result.degraded is True
    status = conn.execute(
        "SELECT * FROM dataset_status WHERE name = 'badminton'"
    ).fetchone()
    assert status["err_streak"] == 1 and "ValueError" in status["last_err"]


# --- R15: GateBackoff aborts the round immediately --------------------------


def test_gate_backoff_aborts_without_persisting_fetched_data():
    conn = mem()
    seed(conn, Session("badminton", "A館", "1號場", TODAY, "19:00", "20:00", 1))
    fetcher = FakeFetcher(raise_for={"tennis": GateBackoff(90)})
    allocator = FakeAllocator()
    notifier = FakeNotifier()

    result = run_cycle(make_deps(
        conn=conn, fetcher=fetcher, allocator=allocator, notifier=notifier,
        gate=FakeGate("safe"), clock=FakeClock(10.0, 10.5),
    ))

    assert fetcher.calls == ["turf-soccer-pitch", "tennis"]
    assert result.aborted is True
    assert result.waf_state == "latch"   # R15: latch even while safe mode is active
    assert result.events == 0 and result.sent == 0 and result.parked == 0
    assert result.ms == 500
    assert allocator.calls == [] and notifier.calls == 0
    # No session/event writes from the sports fetched before the latch.
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert event_rows(conn) == []
    row = sweep(conn)
    assert row["waf_state"] == "latch" and row["note"] == "gate_backoff"
    assert row["ds_ok"] == 1 and row["ds_total"] == 5


def test_backoff_mid_cycle_does_not_persist_partial_snapshot():
    conn = mem()
    seed(conn, Session("badminton", "A館", "1號場", TODAY, "19:00", "20:00", 1))
    day = TODAY + timedelta(days=1)
    fetcher = FakeFetcher(
        payload={
            "turf-soccer-pitch": [rec(day, venue="足球場", facility="1號場")],
            "tennis": [rec(day, venue="網球場", facility="1號場")],
        },
        raise_for={"basketball": GateBackoff(150)},
    )
    allocator = FakeAllocator()
    result = run_cycle(make_deps(conn=conn, fetcher=fetcher, allocator=allocator))

    assert result.aborted is True and result.ds_ok == 2
    assert allocator.calls == []
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 1
    assert event_rows(conn) == []


# --- normal round: persist, allocate once, notify, mark ---------------------


def test_new_session_persists_event_and_marks_notified():
    conn = mem()
    day = TODAY + timedelta(days=1)
    fetcher = FakeFetcher(payload={"badminton": [rec(day)]})
    allocator = FakeAllocator()
    notifier = FakeNotifier()
    result = run_cycle(make_deps(
        conn=conn, fetcher=fetcher, allocator=allocator, notifier=notifier,
        clock=FakeClock(100.0, 100.25),
    ))

    rows = event_rows(conn)
    assert len(rows) == 1
    row = rows[0]
    assert (row["seq"], row["kind"], row["before"], row["after"]) == (1, "new", 0, 1)
    assert row["notified_tg"] == 1 and row["notified_ntfy"] == 0
    assert conn.execute(
        "SELECT courts FROM sessions WHERE sport = 'badminton'"
    ).fetchone()[0] == 1
    assert allocator.calls == [1]
    assert result == CycleResult(
        ok=True, degraded=False, aborted=False, ms=250, bytes=500,
        ds_ok=5, ds_total=5, waf_state="ok", events=1, sent=1, parked=0,
    )
    assert notifier.selected[0].seq == 1


def test_no_events_means_no_allocation_and_no_notification():
    conn = mem()
    allocator = FakeAllocator()
    notifier = FakeNotifier()
    result = run_cycle(make_deps(
        conn=conn, allocator=allocator, notifier=notifier,
        clock=FakeClock(0.0, 1.0),
    ))

    assert result.events == 0 and result.ok is True
    assert allocator.calls == [] and notifier.calls == 0
    assert event_rows(conn) == []
    assert sweep(conn)["note"] is None


def test_notified_marks_come_from_sent_seqs_and_dec_stays_unmarked():
    conn = mem()
    day = TODAY + timedelta(days=1)
    seed(conn, Session("badminton", "A館", "2號場", day, "19:00", "20:00", 2))
    fetcher = FakeFetcher(payload={"badminton": [
        rec(day, facility="1號場"),                    # new  -> seq 1
        rec(day, facility="2號場", courts=1),          # dec  -> seq 2 (not alerted)
        rec(day, facility="3號場"),                    # new  -> seq 3
    ]})
    notifier = FakeNotifier()
    run_cycle(make_deps(conn=conn, fetcher=fetcher, notifier=notifier))

    assert [e.seq for e in notifier.selected] == [1, 3]   # dec filtered out
    marks = [(r["seq"], r["notified_tg"], r["notified_ntfy"]) for r in event_rows(conn)]
    assert marks == [(1, 1, 0), (2, 0, 0), (3, 1, 0)]


def test_parked_events_stay_unmarked_and_outbox_failure_is_noted():
    conn = mem()
    day = TODAY + timedelta(days=1)
    notifier = FakeNotifier(
        delivered=False, via=None,
        errors=["tg_http_500", "ntfy_http_500", "outbox_write_failed"],
    )
    result = run_cycle(make_deps(
        conn=conn, fetcher=FakeFetcher(payload={"badminton": [rec(day)]}),
        notifier=notifier,
    ))

    row = event_rows(conn)[0]
    assert row["notified_tg"] == 0 and row["notified_ntfy"] == 0
    assert result.sent == 0 and result.parked == 1
    # R39: a failed delivery with no outbox row must surface in the sweep.
    assert "outbox_write_failed" in sweep(conn)["note"]


# --- R25: sale7 classification ----------------------------------------------


def test_sale7_window_relabels_farthest_bookable_date_only():
    conn = mem()
    now = datetime(2026, 11, 26, 7, 0, tzinfo=HK)
    near = TODAY + timedelta(days=1)
    far = TODAY + timedelta(days=2)
    fetcher = FakeFetcher(payload={"badminton": [
        rec(near, facility="1號場"), rec(far, facility="2號場"),
    ]})
    run_cycle(make_deps(conn=conn, fetcher=fetcher, now=now))

    rows = event_rows(conn)
    assert [(r["date"], r["kind"]) for r in rows] == [
        (near.isoformat(), "new"), (far.isoformat(), "sale7")]


def test_sale7_window_not_applied_outside_0645_0800():
    conn = mem()
    now = datetime(2026, 11, 26, 8, 30, tzinfo=HK)
    far = TODAY + timedelta(days=2)
    fetcher = FakeFetcher(payload={"badminton": [rec(far)]})
    run_cycle(make_deps(conn=conn, fetcher=fetcher, now=now))

    assert [r["kind"] for r in event_rows(conn)] == ["new"]


@pytest.mark.parametrize("count,expected", [(50, "new"), (51, "sale7")])
def test_burst_threshold_is_over_fifty_per_sport(count, expected):
    conn = mem()
    day = TODAY + timedelta(days=1)
    records = [rec(day, facility=f"{i}號場") for i in range(1, count + 1)]
    run_cycle(make_deps(
        conn=conn, fetcher=FakeFetcher(payload={"badminton": records})))

    assert {r["kind"] for r in event_rows(conn)} == {expected}


def test_sale7_burst_relabels_that_sport_only():
    conn = mem()
    day = TODAY + timedelta(days=1)
    fetcher = FakeFetcher(payload={
        "badminton": [rec(day, facility=f"{i}號場") for i in range(1, 61)],
        "tennis": [rec(day, venue="網球場", facility="1號場")],
    })
    run_cycle(make_deps(conn=conn, fetcher=fetcher))

    rows = event_rows(conn)
    by_sport = {}
    for row in rows:
        by_sport.setdefault(row["sport"], set()).add(row["kind"])
    assert by_sport == {"badminton": {"sale7"}, "tennis": {"new"}}


# --- R24: degraded allocator emits exactly one resync -----------------------


def test_resync_emitted_when_allocator_degraded():
    conn = mem()
    day = TODAY + timedelta(days=1)
    allocator = FakeAllocator(start=1, degraded=True)
    notifier = FakeNotifier()
    result = run_cycle(make_deps(
        conn=conn, allocator=allocator, notifier=notifier,
        fetcher=FakeFetcher(payload={"badminton": [rec(day)]}),
    ))

    rows = event_rows(conn)
    assert len(rows) == 2
    resync = rows[1]
    assert (resync["sport"], resync["venue"], resync["facility"]) == (
        "_system", "", "")
    assert (resync["date"], resync["start"], resync["end"]) == (
        "1970-01-01", "00:00", "00:00")
    assert resync["kind"] == "resync"
    assert resync["before"] is None and resync["after"] is None
    assert allocator.calls == [2]                    # one allocate for both events
    assert result.events == 2
    assert [e.seq for e in notifier.selected] == [1]  # resync is never notified


def test_resync_alone_when_degraded_with_no_events():
    conn = mem()
    allocator = FakeAllocator(start=7, degraded=True)
    result = run_cycle(make_deps(conn=conn, allocator=allocator))

    rows = event_rows(conn)
    assert len(rows) == 1 and rows[0]["kind"] == "resync"
    assert rows[0]["seq"] == 7
    assert allocator.calls == [1]
    assert result.events == 1


def test_resync_not_emitted_when_allocator_healthy():
    conn = mem()
    result = run_cycle(make_deps(conn=conn))
    assert result.events == 0 and event_rows(conn) == []


# --- telemetry --------------------------------------------------------------


def test_dataset_status_err_streak_increments_then_recovers():
    conn = mem()
    day = TODAY + timedelta(days=1)
    run_cycle(make_deps(
        conn=conn, fetcher=FakeFetcher(fail={"badminton": "empty_payload"})))
    status = conn.execute(
        "SELECT * FROM dataset_status WHERE name = 'badminton'").fetchone()
    assert status["err_streak"] == 1 and status["last_err"] == "empty_payload"
    assert status["last_ok"] is None

    run_cycle(make_deps(
        conn=conn, fetcher=FakeFetcher(payload={"badminton": [rec(day)]})))
    status = conn.execute(
        "SELECT * FROM dataset_status WHERE name = 'badminton'").fetchone()
    assert status["err_streak"] == 0 and status["last_err"] is None
    assert status["last_ok"] is not None and status["bytes"] == 100


def test_cycle_prunes_old_sweeps():
    conn = mem()
    db.log_sweep(conn, started_at="2020-01-01T00:00:00+08:00",
                 finished_at="2020-01-01T00:01:00+08:00", ms=1, bytes=1,
                 ds_ok=5, ds_total=5, waf_state="ok", note="")
    run_cycle(make_deps(conn=conn))

    assert conn.execute("SELECT COUNT(*) FROM sweeps").fetchone()[0] == 1
