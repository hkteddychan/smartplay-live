# tests/test_main.py
"""Task 11 — main.py: scheduling, activity thread, sale7 summary, CLI flags.

The loops are driven by an injected clock and wait function, so these tests
never sleep. SQLite is real (in-memory); only the notifier/fetcher are fakes.
"""

import json
import signal
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import poller.main as main_module
from poller import db
from poller.config import ACTIVITY, SPORTS
from poller.cycle import CycleResult
from poller.fetch import FetchResult
from poller.main import (
    activity_once,
    facility_loop,
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
from poller.parse import Session

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


def test_activity_runs_every_900s_and_facility_every_60s():
    # R51: activity search is not latency-critical, so thread B moved to 900s.
    facility = run_for(600, 60)
    activity = run_for(1800, 900, stop_at=1800)

    assert len(facility) == 10
    assert facility == [0, 60, 120, 180, 240, 300, 360, 420, 480, 540]
    assert len(activity) == 2
    assert activity == [0, 900]


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

    assert run_sale7_summary(
        conn, notifier, datetime(2026, 11, 26, 8, 15, tzinfo=HK),
        log=lambda _: None,
    ) == 0
    assert marks(conn) == {1: (0, 0)}


def test_summary_marks_the_ntfy_channel_when_tg_failed():
    conn = mem()
    add_event(conn, 1, "sale7")
    notifier = FakeSummaryNotifier(delivered=True, via="ntfy")

    run_sale7_summary(conn, notifier, datetime(2026, 11, 26, 8, 15, tzinfo=HK))

    assert marks(conn) == {1: (0, 1)}


def test_format_groups_by_sport_and_venue_and_sorts_by_count():
    rows = [
        {"sport": "badminton", "venue": "B館"},
        {"sport": "badminton", "venue": "A館"},
        {"sport": "badminton", "venue": "A館"},
    ]
    text = format_sale7_summary(rows)
    assert text.splitlines()[0] == "🛒 開賣 summary ×3"
    assert "• [羽毛球] A館：2 場" in text
    assert "• [羽毛球] B館：1 場" in text


def test_format_summary_labels_each_venue_with_its_sport():
    rows = [
        {"sport": "turf-soccer-pitch", "venue": "B館"},
        {"sport": "badminton", "venue": "A館"},
        {"sport": "badminton", "venue": "A館"},
    ]
    text = format_sale7_summary(rows)
    assert "• [羽毛球] A館：2 場" in text
    assert "• [足球] B館：1 場" in text


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


# --- C4: a non-raising failed round still escalates -------------------------


def _aborted_result(ds_ok=0, ds_total=5) -> CycleResult:
    return CycleResult(
        ok=False, degraded=False, aborted=True, ms=1, bytes=0,
        ds_ok=ds_ok, ds_total=ds_total, waf_state="latch",
        events=0, sent=0, parked=0,
    )


def _drive_facility(runs, *, stop_at):
    stop = threading.Event()
    clock = FakeClock()
    wait = FakeWait(clock, stop, stop_at=stop_at)
    fatal = threading.Event()
    logs = []
    calls = []

    def run(deps):
        calls.append(1)
        return runs[len(calls) - 1]

    facility_loop(
        stop, conn=mem(), gate=FakeGate(), allocator=FakeAllocator(),
        notifier=FakeCycleNotifier(), sports=["tennis"], run=run,
        summary=lambda *args: 0, now=lambda: NOW, clock=clock, wait=wait,
        fatal_event=fatal, log=logs.append,
    )
    return fatal, stop, calls, logs


def test_five_aborted_rounds_exit_non_zero():
    """C4: a WAF latch round raises nothing but is a real upstream failure."""
    fatal, stop, calls, logs = _drive_facility(
        [_aborted_result() for _ in range(10)], stop_at=10_000.0
    )
    assert len(calls) == 5
    assert fatal.is_set() and stop.is_set()
    assert "facility fatal consecutive_failures=5" in logs


def test_aborted_round_waits_the_gate_backoff():
    """I5: the exception's seconds must drive the loop, not just the log."""
    stop = threading.Event()
    clock = FakeClock()
    wait = FakeWait(clock, stop, stop_at=90.0)
    result = CycleResult(
        ok=False, degraded=False, aborted=True, ms=1, bytes=0,
        ds_ok=0, ds_total=5, waf_state="latch", events=0, sent=0, parked=0,
        backoff_seconds=90,
    )

    facility_loop(
        stop, conn=mem(), gate=FakeGate(), allocator=FakeAllocator(),
        notifier=FakeCycleNotifier(), sports=["tennis"],
        run=lambda deps: result, summary=lambda *args: 0, now=lambda: NOW,
        clock=clock, wait=wait, log=lambda _: None,
    )

    assert wait.calls[0] == 90
    assert clock.now >= 90


def test_an_ok_round_resets_the_failure_streak():
    fatal, stop, calls, logs = _drive_facility(
        [_aborted_result() for _ in range(4)]
        + [CycleResult(ok=True, degraded=False, aborted=False, ms=1, bytes=1,
                       ds_ok=5, ds_total=5, waf_state="ok",
                       events=0, sent=0, parked=0)]
        + [_aborted_result() for _ in range(10)],
        stop_at=360.0,
    )
    assert len(calls) == 6
    assert not fatal.is_set()


# --- C3: the facility tick drains the outbox --------------------------------


class _OkHttp:
    def __init__(self):
        self.posts = []

    def post(self, url, json=None, data=None, headers=None, timeout=None, **kw):
        self.posts.append(url)
        return SimpleNamespace(status_code=200, json=lambda: {"ok": True})


def test_facility_tick_drains_a_parked_outbox_batch():
    """C3: flush_outbox was written but never called, so parks never retried."""
    from poller.config import Settings
    from poller.main import facility_loop
    from poller.notify import Notifier

    conn = mem()
    add_event(conn, 5, "new")
    payload = json.dumps(
        {"text": "🏸 放場 ×1\n• …", "title": "🏸 放場", "tags": "badminton",
         "silent": False, "seqs": [5]}
    )
    conn.execute(
        "INSERT INTO outbox (seq_from, seq_to, channel, payload, attempts, next_try, last_error) "
        "VALUES (5, 5, 'tg+ntfy', ?, 0, '2000-01-01T00:00:00+08:00', 'x')",
        (payload,),
    )
    conn.commit()
    settings = Settings(
        tg_token="t", tg_chat="1", tg_thread=1, ntfy_url="http://n/x",
        r2_endpoint="", r2_bucket="", r2_access_key="", r2_secret_key="",
        db_path=":memory:",
    )
    http = _OkHttp()
    notifier = Notifier(settings, http=http, conn=conn)

    stop = threading.Event()
    clock = FakeClock()
    wait = FakeWait(clock, stop, stop_at=60.0)
    result = CycleResult(
        ok=True, degraded=False, aborted=False, ms=1, bytes=10,
        ds_ok=1, ds_total=1, waf_state="ok", events=0, sent=0, parked=0,
    )
    facility_loop(
        stop, conn=conn, gate=FakeGate(), allocator=FakeAllocator(),
        notifier=notifier, sports=["tennis"], run=lambda deps: result,
        summary=lambda *args: 0, now=lambda: NOW, clock=clock, wait=wait,
        log=lambda _: None,
    )

    assert conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
    assert marks(conn)[5] == (1, 0)
    assert http.posts


# --- CLI / wiring ----------------------------------------------------------


def test_select_sports_for_only_flag():
    assert select_sports(None) == list(SPORTS)
    assert select_sports("tennis") == ["tennis"]
    assert select_sports(ACTIVITY) == []


def test_result_line_matches_the_smoke_test_log_shape():
    from poller.main import _result_line

    result = CycleResult(
        ok=True, degraded=False, aborted=False, ms=1234, bytes=3_100_000,
        ds_ok=1, ds_total=1, waf_state="ok", events=2, sent=2, parked=0,
    )
    line = _result_line(result, 321)

    assert "fetch ok bytes=3.1MB" in line
    assert "parse=321 sessions" in line
    assert "cycle_ms=1234" in line


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


def test_seed_flag_forces_a_baseline_round_in_main(monkeypatch, tmp_path):
    """R59: --seed re-baselines even when the sessions table is populated."""
    monkeypatch.setenv("TG_TOKEN", "t")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setenv("COOKIES_PATH", str(tmp_path / "cookies.json"))
    monkeypatch.setenv("SEQ_URL", "")
    monkeypatch.setenv("SEQ_LOCAL_PATH", str(tmp_path / "seq.json"))

    conn = db.connect(str(tmp_path / "state.db"))
    db.init_db(conn)
    db.upsert_sessions(
        conn,
        [Session("tennis", "A館", "1號場", date(2026, 11, 27), "19:00", "20:00", 1)],
        NOW.isoformat(timespec="seconds"),
    )
    conn.close()

    captured = {}

    def fake_run(deps):
        captured["baseline"] = deps.baseline
        return CycleResult(
            ok=True, degraded=False, aborted=False, ms=1, bytes=10,
            ds_ok=1, ds_total=1, waf_state="ok", events=0, sent=0, parked=0,
        )

    monkeypatch.setattr(main_module, "run_cycle", fake_run)

    assert main_module.main(["--once", "--seed", "--only=tennis"]) == 0
    assert captured["baseline"] is True

    main_module.main(["--once", "--only=tennis"])
    assert captured["baseline"] is None       # auto-detect when not seeding


def test_seed_only_affects_the_first_long_running_round():
    baselines = []
    result = CycleResult(
        ok=True, degraded=False, aborted=False, ms=1, bytes=1,
        ds_ok=1, ds_total=1, waf_state="ok", events=0, sent=0, parked=0,
    )

    def run(deps):
        baselines.append(deps.baseline)
        return result

    stop = threading.Event()
    clock = FakeClock()
    wait = FakeWait(clock, stop, stop_at=120.0)
    facility_loop(
        stop, conn=mem(), gate=FakeGate(), allocator=FakeAllocator(),
        notifier=FakeCycleNotifier(), sports=["tennis"], run=run,
        summary=lambda *args: 0, now=lambda: NOW, clock=clock, wait=wait,
        seed=True, log=lambda _: None,
    )

    assert baselines == [True, None]


def test_seq_allocator_seeds_local_counter_from_the_events_table(
    monkeypatch, tmp_path
):
    """I7: losing seq.json must not restart numbering below existing rows."""
    from poller.config import Settings

    db_path = tmp_path / "state.db"
    conn = db.connect(str(db_path))
    db.init_db(conn)
    add_event(conn, 500, "new")
    conn.close()
    monkeypatch.setenv("SEQ_URL", "")
    monkeypatch.setenv("SEQ_LOCAL_PATH", str(tmp_path / "seq.json"))
    settings = Settings(
        tg_token="t", tg_chat="1", tg_thread=1, ntfy_url="",
        r2_endpoint="", r2_bucket="", r2_access_key="", r2_secret_key="",
        db_path=str(db_path),
    )

    allocator = main_module._seq_allocator(settings)

    assert allocator.allocate(1) == 501


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
    assert "60" in out and "900" in out
    assert "08:10" in out and "08:20" in out
    assert "activity-prog" in out


def test_dry_run_with_only_activity_shows_no_facility_loop(monkeypatch, capsys):
    monkeypatch.delenv("TG_TOKEN", raising=False)
    assert main(["--dry-run", "--only=activity-prog"]) == 0
    out = capsys.readouterr().out.lower()
    assert "facility" in out and "skip" in out


def test_systemd_unit_allows_a_graceful_stop_and_has_no_watchdog():
    """R52/R45: stop must not SIGKILL a cycle stuck in notify backoff."""
    unit = (
        Path(__file__).resolve().parents[1] / "ops" / "smartplay-poller.service"
    ).read_text(encoding="utf-8")

    assert "TimeoutStopSec=120" in unit
    assert "KillSignal=SIGTERM" in unit
    assert "Restart=always" in unit
    assert "RestartSec=5" in unit
    assert "MemoryMax=1G" in unit
    assert "CPUQuota=150%" in unit
    assert "WatchdogSec" not in unit


def test_systemd_onfailure_targets_the_alert_template_correctly():
    """I8: %n already ends in .service — appending it again double-suffixes."""
    ops = Path(__file__).resolve().parents[1] / "ops"
    unit = (ops / "smartplay-poller.service").read_text(encoding="utf-8")

    assert "OnFailure=smartplay-alert@%n\n" in unit
    assert "smartplay-alert@%n.service" not in unit
    assert "StartLimitIntervalSec=300" in unit
    assert "StartLimitBurst=5" in unit
    assert "WatchdogSec" not in unit          # R45/R52 still hold

    alert = (ops / "smartplay-alert@.service").read_text(encoding="utf-8")
    assert "Type=oneshot" in alert
    assert "EnvironmentFile=-/opt/smartplay/.env" in alert
    assert 'if [ -z "$TG_TOKEN" ]' in alert
    assert "curl" in alert and "api.telegram.org" in alert
    assert "%i" in alert


def test_main_rejects_unknown_only_value(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--dry-run", "--only=not-a-sport"])
    assert exc.value.code == 2


# --- thread ownership (R53) -------------------------------------------------


def test_worker_thread_opens_its_own_connection_and_writes(
    monkeypatch, tmp_path, capsys
):
    """R53: SQLite connections are thread-affine, so each worker must open its
    own connection *inside* the thread. A connection created by ``main()`` and
    lent to the worker raises ProgrammingError on every query.
    """
    monkeypatch.setenv("TG_TOKEN", "test-token")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "state.db"))

    written = threading.Event()
    errors: list[BaseException] = []

    def fake_run(deps):
        try:
            db.upsert_sessions(
                deps.conn,
                [
                    Session(
                        "tennis", "A館", "1號場", date(2026, 11, 27),
                        "19:00", "20:00", 1,
                    )
                ],
                NOW.isoformat(timespec="seconds"),
            )
        except BaseException as exc:  # record the RED reason for the assertion
            errors.append(exc)
            raise
        written.set()
        return CycleResult(
            ok=True, degraded=False, aborted=False, ms=1, bytes=10,
            ds_ok=1, ds_total=1, waf_state="ok", events=0, sent=0, parked=0,
        )

    stop_holder: dict[str, threading.Event] = {}

    def fake_install_signal_handlers(stop_event):
        # main() runs in a non-main test thread here; capturing the event also
        # gives the test a safe way to request shutdown.
        stop_holder["stop"] = stop_event

    monkeypatch.setattr(main_module, "run_cycle", fake_run)
    monkeypatch.setattr(
        main_module, "install_signal_handlers", fake_install_signal_handlers
    )

    runner = threading.Thread(
        target=lambda: main_module.main(["--only=tennis"]), name="test-main"
    )
    runner.start()
    try:
        wrote = written.wait(10)
    finally:
        stop_holder["stop"].set()
    runner.join(timeout=10)
    output = capsys.readouterr().out

    assert wrote, (
        "facility worker never wrote a session; worker errors="
        f"{[type(exc).__name__ for exc in errors]!r}\n{output}"
    )
    assert not runner.is_alive(), "main() did not stop within 10s"
    assert errors == [], [repr(exc) for exc in errors]
    assert "ProgrammingError" not in output

    conn = db.connect(str(tmp_path / "state.db"))
    try:
        rows = conn.execute("SELECT sport, venue FROM sessions").fetchall()
    finally:
        conn.close()
    assert [(row["sport"], row["venue"]) for row in rows] == [("tennis", "A館")]


def test_one_dead_worker_stops_the_process_non_zero(
    monkeypatch, tmp_path, capsys
):
    """C2: with two threads, ``any`` liveness would hide a silent death.

    One worker returning without setting ``fatal_event`` must still stop the
    unit with a non-zero exit (systemd restarts it; OnFailure alerts).
    """
    monkeypatch.setenv("TG_TOKEN", "test-token")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "state.db"))
    monkeypatch.setenv("COOKIES_PATH", str(tmp_path / "cookies.json"))
    monkeypatch.setattr(main_module, "LIVENESS_POLL_SECONDS", 0.01)
    monkeypatch.setattr(main_module, "install_signal_handlers", lambda event: None)

    def dead_facility(**kwargs):
        return None  # thread exits without touching fatal_event

    def live_activity(**kwargs):
        kwargs["stop_event"].wait(5)

    monkeypatch.setattr(main_module, "facility_worker", dead_facility)
    monkeypatch.setattr(main_module, "activity_worker", live_activity)

    code = main_module.main([])
    output = capsys.readouterr().out

    assert code != 0
    assert "worker exited unexpectedly" in output


def test_five_consecutive_worker_failures_exit_non_zero(
    monkeypatch, tmp_path, capsys
):
    """R54: a permanently failing worker must escalate, not log forever."""
    monkeypatch.setenv("TG_TOKEN", "test-token")
    monkeypatch.setenv("DB_PATH", str(tmp_path / "state.db"))

    def always_fail(deps):
        raise RuntimeError("boom")

    iterations: list[int] = []

    def fake_periodic(stop_event, interval, run, *, clock=None, wait=None):
        # Drive five real ticks without sleeping; the sixth check proves the
        # loop was stopped by the failure counter, not by the 10-iteration cap.
        for number in range(10):
            if stop_event.is_set():
                break
            iterations.append(number)
            run()

    monkeypatch.setattr(main_module, "run_cycle", always_fail)
    monkeypatch.setattr(main_module, "periodic_loop", fake_periodic)

    code = main_module.main(["--only=tennis"])
    output = capsys.readouterr().out

    assert code != 0
    assert iterations == [0, 1, 2, 3, 4]
    assert "facility fatal consecutive_failures=5" in output
    assert "poller fatal worker failure" in output
