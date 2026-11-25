# tests/test_main.py
"""Task 11 — main.py: scheduling, activity thread, sale7 summary, CLI flags.

The loops are driven by an injected clock and wait function, so these tests
never sleep. SQLite is real (in-memory); only the notifier/fetcher are fakes.
"""

import signal
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from poller import db
from poller.config import ACTIVITY, SPORTS
from poller.cycle import CycleResult
from poller.fetch import FetchResult
from poller.main import (
    activity_once,
    facility_once,
    format_sale7_summary,
    install_signal_handlers,
    main,
    make_signal_handler,
    periodic_loop,
    run_sale7_summary,
    select_sports,
    should_send_sale7_summary,
)
from poller.notify import DeliveryResult

HK = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 26, 10, 0, tzinfo=HK)
SALE7_TS = "2026-11-26T07:00:00+08:00"


# --- fakes -----------------------------------------------------------------


class FakeClock:
    """Monotonic time that only moves when the fake wait is called."""

    def __init__(self, start=0.0):
        self.now = start

    def __call__(self):
        return self.now


class FakeWait:
    """Advance the fake clock; set the stop event at ``stop_at`` seconds."""

    def __init__(self, clock, stop_event, stop_at):
        self.clock = clock
        self.stop_event = stop_event
        self.stop_at = stop_at
        self.calls = []

    def __call__(self, timeout):
        self.calls.append(timeout)
        self.clock.now += timeout
        if self.clock.now >= self.stop_at:
            self.stop_event.set()
            return True
        return False


class FakeSummaryNotifier:
    def __init__(self, delivered=True, via="tg"):
        self.delivered = delivered
        self.via = via
        self.texts = []

    def send_summary(self, text):
        self.texts.append(text)
        return DeliveryResult(
            self.delivered,
            self.via if self.delivered else None,
            [] if self.delivered else ["tg_http_500", "ntfy_http_500"],
        )


class FakeActivityFetcher:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, gate, base_url, name):
        self.calls.append((gate, base_url, name))
        return self.result


class FakeGate:
    state = "ok"
    target_cycle_seconds = 60


class FakeAllocator:
    degraded = False

    def allocate(self, n):
        return 1


class FakeCycleNotifier:
    def send_events(self, events, channel_filter):
        return DeliveryResult(True, None, [])


# --- helpers ---------------------------------------------------------------


def mem():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def add_event(conn, seq, kind, venue="A館", ts=SALE7_TS,
              notified_tg=0, notified_ntfy=0, sport="badminton"):
    conn.execute(
        'INSERT INTO events (seq, ts, sport, venue, facility, date, start, "end", '
        "kind, before, \"after\", notified_tg, notified_ntfy) "
        "VALUES (?, ?, ?, ?, '1號場', '2026-11-27', '19:00', '20:00', ?, 0, 1, ?, ?)",
        (seq, ts, sport, venue, kind, notified_tg, notified_ntfy),
    )
    conn.commit()


def marks(conn):
    return {
        row["seq"]: (row["notified_tg"], row["notified_ntfy"])
        for row in conn.execute(
            "SELECT seq, notified_tg, notified_ntfy FROM events ORDER BY seq"
        )
    }


# --- scheduling (brief: 600s -> facility 10, activity 2) -------------------


def run_for(seconds, every, stop_at=600.0):
    stop = threading.Event()
    clock = FakeClock()
    wait = FakeWait(clock, stop, stop_at)
    runs = []

    periodic_loop(stop, every, lambda: runs.append(clock.now),
                  clock=clock, wait=wait)
    assert clock.now == stop_at
    return runs


def test_activity_runs_every_300s_and_facility_every_60s():
    facility = run_for(600, 60)
    activity = run_for(600, 300)

    assert len(facility) == 10
    assert facility == [0, 60, 120, 180, 240, 300, 360, 420, 480, 540]
    assert len(activity) == 2
    assert activity == [0, 300]


def test_facility_interval_can_double_in_safe_mode():
    # gate.target_cycle_seconds is 120 during safe mode; 600s -> 5 rounds.
    runs = run_for(600, lambda: 120)
    assert len(runs) == 5
    assert runs == [0, 120, 240, 360, 480]


def test_loop_uses_injected_wait_and_stops_immediately():
    # The loop must use stop_event.wait(timeout), never time.sleep.
    stop = threading.Event()
    clock = FakeClock()
    waited = []
    runs = []

    def wait(timeout):
        waited.append(timeout)
        stop.set()
        return True

    periodic_loop(stop, 60, lambda: runs.append(clock.now),
                  clock=clock, wait=wait)

    assert runs == [0]
    assert waited == [60]
    assert stop.is_set()


def test_overrun_does_not_catch_up_with_a_burst_of_runs():
    # A slow round (t jumps past the next due time) waits a full interval.
    stop = threading.Event()
    clock = FakeClock()
    waited = []
    runs = []

    def run():
        runs.append(clock.now)
        clock.now += 70  # this round took 70s, longer than the 60s cadence

    def wait(timeout):
        waited.append(timeout)
        clock.now += timeout
        if len(waited) == 2:
            stop.set()
            return True
        return False

    periodic_loop(stop, 60, run, clock=clock, wait=wait)

    assert runs == [0, 130]
    assert waited == [60, 60]


# --- sale7 summary (R48) ----------------------------------------------------


def test_summary_fires_in_window_and_marks_exactly_the_rows_sent():
    conn = mem()
    add_event(conn, 1, "sale7", venue="A館")
    add_event(conn, 2, "sale7", venue="A館")
    add_event(conn, 3, "sale7", venue="B館")
    add_event(conn, 4, "new", venue="C館")
    notifier = FakeSummaryNotifier()

    sent = run_sale7_summary(conn, notifier, datetime(2026, 11, 26, 8, 10, tzinfo=HK))

    assert sent == 3
    assert len(notifier.texts) == 1
    text = notifier.texts[0]
    assert "A館：2 場" in text
    assert "B館：1 場" in text
    assert marks(conn) == {1: (1, 0), 2: (1, 0), 3: (1, 0), 4: (0, 0)}

    # One summary marks every sent row; the same minute cannot send again.
    assert run_sale7_summary(conn, notifier, datetime(2026, 11, 26, 8, 11, tzinfo=HK)) == 0
    assert len(notifier.texts) == 1


def test_summary_window_is_inclusive_0810_to_0820():
    # Fresh rows (08:08) isolate the window condition from the 15-minute
    # idle condition at 08:21.
    for minute, expected in ((9, False), (10, True), (20, True), (21, False)):
        conn = mem()
        add_event(conn, 1, "sale7", ts="2026-11-26T08:08:00+08:00")
        assert should_send_sale7_summary(
            db.fetch_unsent_sale7(conn),
            datetime(2026, 11, 26, 8, minute, tzinfo=HK),
        ) is expected


def test_summary_waits_for_15_minutes_of_sale7_silence():
    conn = mem()
    add_event(conn, 1, "sale7", ts="2026-11-26T09:50:00+08:00")

    assert should_send_sale7_summary(
        db.fetch_unsent_sale7(conn), datetime(2026, 11, 26, 10, 4, tzinfo=HK)
    ) is False
    assert should_send_sale7_summary(
        db.fetch_unsent_sale7(conn), datetime(2026, 11, 26, 10, 5, tzinfo=HK)
    ) is True


def test_summary_not_sent_when_no_unsent_sale7_rows():
    conn = mem()
    add_event(conn, 1, "new")
    notifier = FakeSummaryNotifier()

    assert run_sale7_summary(conn, notifier, NOW) == 0
    assert notifier.texts == []
    assert should_send_sale7_summary([], NOW) is False


def test_failed_summary_leaves_rows_unsent_for_the_next_round():
    conn = mem()
    add_event(conn, 1, "sale7")
    notifier = FakeSummaryNotifier(delivered=False, via=None)

    assert run_sale7_summary(conn, notifier, datetime(2026, 11, 26, 8, 15, tzinfo=HK)) == 0
    assert marks(conn) == {1: (0, 0)}


def test_summary_marks_the_ntfy_channel_when_tg_failed():
    conn = mem()
    add_event(conn, 1, "sale7")
    notifier = FakeSummaryNotifier(delivered=True, via="ntfy")

    run_sale7_summary(conn, notifier, datetime(2026, 11, 26, 8, 15, tzinfo=HK))

    assert marks(conn) == {1: (0, 1)}


def test_format_groups_by_venue_and_sorts_by_count():
    rows = [
        {"venue": "B館"}, {"venue": "A館"}, {"venue": "A館"},
    ]
    text = format_sale7_summary(rows)
    assert text.splitlines()[0] == "🛒 開賣 summary ×3"
    assert "• A館：2 場" in text


# --- activity thread --------------------------------------------------------


def test_activity_once_stores_a_valid_payload():
    conn = mem()
    gate = FakeGate()
    fetcher = FakeActivityFetcher(
        FetchResult(ACTIVITY, True, [{"ACTIVITY_NO": "A1", "TC_PGM_NAME": "測試"}], 42, None)
    )

    assert activity_once(conn, gate, NOW, fetch=fetcher, log=lambda _: None) is True
    assert len(fetcher.calls) == 1
    called_gate, _base_url, name = fetcher.calls[0]
    assert called_gate is gate and name == ACTIVITY
    row = conn.execute("SELECT activity_no, payload FROM activities").fetchone()
    assert row["activity_no"] == "A1" and "測試" in row["payload"]


def test_activity_once_keeps_the_snapshot_when_fetch_is_bad():
    conn = mem()
    db.upsert_activities(conn, [{"ACTIVITY_NO": "A1"}], NOW.isoformat())
    fetcher = FakeActivityFetcher(
        FetchResult(ACTIVITY, False, [], 0, "html_response")
    )

    assert activity_once(conn, FakeGate(), NOW, fetch=fetcher, log=lambda _: None) is False
    assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1


# --- CLI / wiring ----------------------------------------------------------


def test_select_sports_for_only_flag():
    assert select_sports(None) == list(SPORTS)
    assert select_sports("tennis") == ["tennis"]
    assert select_sports(ACTIVITY) == []


def test_facility_once_passes_the_selected_subset_to_the_cycle():
    conn = mem()
    captured = {}

    def fake_run(deps):
        captured["sports"] = deps.sports
        return CycleResult(
            ok=True, degraded=False, aborted=False, ms=1, bytes=10,
            ds_ok=1, ds_total=1, waf_state="ok", events=0, sent=0, parked=0,
        )

    result = facility_once(
        conn, FakeGate(), FakeAllocator(), FakeCycleNotifier(), ["tennis"], NOW,
        run=fake_run, log=lambda _: None,
    )

    assert result.ok is True
    assert captured["sports"] == ["tennis"]


def test_signal_handler_sets_the_stop_event():
    stop = threading.Event()
    make_signal_handler(stop)(signal.SIGTERM, None)
    assert stop.is_set()


def test_install_signal_handlers_covers_sigterm_and_sigint():
    stop = threading.Event()
    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    try:
        install_signal_handlers(stop)
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        assert stop.is_set()
        stop.clear()
        signal.getsignal(signal.SIGINT)(signal.SIGINT, None)
        assert stop.is_set()
    finally:
        signal.signal(signal.SIGTERM, old_term)
        signal.signal(signal.SIGINT, old_int)


def test_dry_run_prints_the_plan_without_env_or_network(monkeypatch, capsys):
    for name in ("TG_TOKEN", "SEQ_URL", "SEQ_TOKEN"):
        monkeypatch.delenv(name, raising=False)

    assert main(["--dry-run"]) == 0

    out = capsys.readouterr().out.lower()
    assert "dry run" in out
    assert "60" in out and "300" in out
    assert "08:10" in out and "08:20" in out
    assert "activity-prog" in out


def test_dry_run_with_only_activity_shows_no_facility_loop(monkeypatch, capsys):
    monkeypatch.delenv("TG_TOKEN", raising=False)
    assert main(["--dry-run", "--only=activity-prog"]) == 0
    out = capsys.readouterr().out.lower()
    assert "facility" in out and "skip" in out


def test_main_rejects_unknown_only_value(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--dry-run", "--only=not-a-sport"])
    assert exc.value.code == 2
