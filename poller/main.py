"""Process entry point: two long-running threads over one SQLite database.

Thread A (facility) runs :func:`poller.cycle.run_cycle` every
``gate.target_cycle_seconds`` (60s normally, 120s in WAF safe mode). Thread B
fetches ``activity-prog`` every 900s and stores the snapshot in SQLite; it is
deliberately outside the five-sport cycle so the 14.6MB payload never touches
the G1 budget. A payload hash keeps an unchanged snapshot from being rewritten
(R51). Both threads share one :class:`poller.gate.Gate`, so only one
HTTP request is ever in flight.

The sale7 summary job (R48) runs from thread A once per facility round:

* inside **08:10–08:20 HKT**, or
* after a sale7 burst has had no new events for **15 minutes**,

one message is sent with ``venue → number of slots`` for every unsent sale7
row, then exactly those rows are marked on the channel that accepted it.
Sale7 never goes through ``Notifier.send_events``.

Shutdown (R50): SIGTERM/SIGINT only set a ``threading.Event``; each worker
finishes the iteration in progress (never mid-request) and exits, then the
database connections are closed. Sleeps are ``stop_event.wait(timeout)``, so
systemd does not have to wait out a full cycle.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import signal
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Iterable, Mapping

import requests

from poller import db
from poller.config import (
    ACTIVITY,
    ACTIVITY_EVERY_SECONDS,
    CYCLE_SECONDS,
    SPORTS,
    Settings,
)
from poller.cycle import BASE_URL, CycleResult, Deps, run_cycle
from poller.fetch import FetchResult, fetch_dataset
from poller.gate import Gate, GateBackoff
from poller.notify import Notifier, sport_name
from poller.seq import SeqAllocator

HK = db.HK
SALE7_WINDOW = ("08:10", "08:20")     # R48: inclusive HKT clock window
SALE7_IDLE = timedelta(minutes=15)    # R48: quiet time after a burst
SUMMARY_MAX_VENUES = 60
SUMMARY_MAX_CHARS = 4000
TG_MAX_CHARS = 4096                   # Telegram hard limit (escaped text)
HTTP_TIMEOUT = (10, 60)               # connect, read — below systemd's 90s stop
MAX_CONSECUTIVE_FAILURES = 5          # R54: then exit non-zero for systemd
LIVENESS_POLL_SECONDS = 5.0           # how often main() checks its workers

Log = Callable[[str], None]


def log(message: str) -> None:
    """One line to the journal; flushed so systemd sees it immediately."""
    print(message, flush=True)


# --- scheduling -------------------------------------------------------------

Interval = float | Callable[[], float]


def periodic_loop(
    stop_event: threading.Event,
    interval: Interval,
    run: Callable[[], None],
    *,
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], bool] | None = None,
) -> None:
    """Run ``run`` immediately, then every ``interval`` seconds.

    ``interval`` may be a callable so the facility loop can follow
    ``gate.target_cycle_seconds`` into safe mode. The next due time is pinned
    to the cadence rather than to the finish time, so a round that overruns
    waits a full interval instead of firing a catch-up burst. ``wait`` is
    ``stop_event.wait`` in production and a fake in tests; its return value
    means "stop requested".
    """
    wait = wait if wait is not None else stop_event.wait
    next_due = clock()
    while not stop_event.is_set():
        run()
        every = interval() if callable(interval) else interval
        next_due += every
        now = clock()
        if next_due <= now:
            next_due = now + every
        if wait(max(0.0, next_due - now)):
            break


def make_signal_handler(stop_event: threading.Event):
    """Build the SIGTERM/SIGINT handler: set the event, do nothing else."""

    def handler(signum, frame) -> None:  # noqa: ARG001 - signal API signature
        stop_event.set()

    return handler


def install_signal_handlers(stop_event: threading.Event) -> None:
    handler = make_signal_handler(stop_event)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


# --- sale7 summary (R48) ----------------------------------------------------


def _aware_hk(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=HK)


def _row_ts(row: Mapping) -> datetime:
    parsed = datetime.fromisoformat(row["ts"])
    return _aware_hk(parsed)


def should_send_sale7_summary(
    rows: Iterable[Mapping], now_hk: datetime
) -> bool:
    """True when there is something unsent and either R48 condition holds."""
    rows = list(rows)
    if not rows:
        return False
    now_hk = _aware_hk(now_hk)
    if SALE7_WINDOW[0] <= now_hk.strftime("%H:%M") <= SALE7_WINDOW[1]:
        return True
    latest = max(_row_ts(row) for row in rows)
    return now_hk - latest >= SALE7_IDLE


def format_sale7_summary(rows: Iterable[Mapping]) -> str:
    """One message: header plus ``• [sport] venue：N 場``, sorted by count."""
    rows = list(rows)
    counts = Counter((str(row["sport"]), str(row["venue"])) for row in rows)
    items = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    header = f"🛒 開賣 summary ×{len(rows)}"
    selected = items[:SUMMARY_MAX_VENUES]
    while True:
        hidden = items[len(selected):]
        note = (
            f"…另有 {len(hidden)} 場館 / {sum(count for _, count in hidden)} 場"
            if hidden else ""
        )
        lines = [
            header,
            *(f"• [{sport_name(sport)}] {venue}：{count} 場"
              for (sport, venue), count in selected),
        ]
        if note:
            lines.append(note)
        text = "\n".join(lines)
        if len(text) <= SUMMARY_MAX_CHARS and len(html.escape(text)) <= TG_MAX_CHARS:
            return text
        if not selected:
            return header
        selected.pop()


def run_sale7_summary(
    conn, notifier, now_hk: datetime, *, log: Log = log
) -> int:
    """Send (at most) one summary and mark exactly the rows it covered."""
    rows = db.fetch_unsent_sale7(conn)
    if not should_send_sale7_summary(rows, now_hk):
        return 0
    text = format_sale7_summary(rows)
    result = notifier.send_summary(text)
    if not result.delivered or not result.via:
        log(f"sale7 summary_failed {';'.join(result.errors) or 'no_channel'}")
        return 0
    db.mark_sale7_notified(conn, [row["seq"] for row in rows], result.via)
    return len(rows)


# --- one iteration of each thread -------------------------------------------


def _session_count(conn, sports: Iterable[str]) -> int:
    sports = list(sports)
    if not sports:
        return 0
    placeholders = ",".join("?" * len(sports))
    return conn.execute(
        f"SELECT COUNT(*) FROM sessions WHERE sport IN ({placeholders})", sports
    ).fetchone()[0]


def _human_bytes(count: int) -> str:
    # Decimal units, matching the plan's ``bytes=3.1MB`` example.
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}MB"
    return f"{count / 1_000:.0f}KB"


def _result_line(result: CycleResult, sessions: int) -> str:
    status = "ok" if result.ok else ("aborted" if result.aborted else "degraded")
    return (
        f"fetch {status} bytes={_human_bytes(result.bytes)} "
        f"parse={sessions} sessions ds={result.ds_ok}/{result.ds_total} "
        f"events={result.events} sent={result.sent} parked={result.parked} "
        f"cycle_ms={result.ms} waf={result.waf_state}"
    )


def facility_once(
    conn,
    gate,
    allocator,
    notifier,
    sports: Iterable[str],
    now_hk: datetime,
    *,
    run: Callable[[Deps], CycleResult] | None = None,
    seed: bool = False,
    log: Log = log,
) -> CycleResult:
    """One facility round restricted to ``sports`` (``--only`` friendly)."""
    sports = list(sports)
    deps = Deps(
        conn=conn,
        gate=gate,
        allocator=allocator,
        notifier=notifier,
        now_hk=now_hk,
        sports=sports,
        baseline=True if seed else None,
    )
    result = (run or run_cycle)(deps)
    log(_result_line(result, _session_count(conn, sports)))
    return result


def activity_once(
    conn,
    gate,
    now_hk: datetime,
    *,
    fetch: Callable[..., FetchResult] = fetch_dataset,
    store: Callable[..., int] = db.upsert_activities,
    log: Log = log,
) -> bool:
    """Fetch+store one activity snapshot; a bad payload leaves the old one."""
    try:
        fetched = fetch(gate, BASE_URL, ACTIVITY)
    except GateBackoff as exc:
        log(f"activity waf_backoff seconds={exc.seconds:g}")
        return False
    except Exception as exc:  # never kill the thread on one transport error
        log(f"activity fetch_failed {type(exc).__name__}")
        return False
    if not fetched.ok:
        log(f"activity fetch_failed {fetched.error}")
        return False
    try:
        stored = store(
            conn, fetched.records, now_hk.isoformat(timespec="seconds"),
            log=log,
        )
    except Exception as exc:
        log(f"activity store_failed {type(exc).__name__}")
        return False
    log(
        f"activity ok bytes={_human_bytes(fetched.bytes)} "
        f"records={len(fetched.records)} stored={stored}"
    )
    return True


# --- thread bodies ----------------------------------------------------------


def facility_loop(
    stop_event: threading.Event,
    *,
    conn,
    gate,
    allocator,
    notifier,
    sports: Iterable[str],
    run: Callable[[Deps], CycleResult] | None = None,
    summary: Callable[[object, object, datetime], int] = run_sale7_summary,
    now: Callable[[], datetime] = lambda: datetime.now(HK),
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], bool] | None = None,
    fatal_event: threading.Event | None = None,
    seed: bool = False,
    log: Log = log,
) -> None:
    """Facility round + sale7 summary, once per target cycle.

    R59: ``seed`` forces exactly the first round to be a silent baseline, so
    ``poller --seed`` can re-baseline a populated DB without disabling diffing
    forever.

    R54: a run that keeps raising must not log forever while the unit stays
    ``active``. After ``MAX_CONSECUTIVE_FAILURES`` failed rounds the shared
    ``fatal_event`` is set, ``stop_event`` stops the sibling worker, and
    ``main()`` exits non-zero so systemd restarts the service.
    """
    failures = 0
    seed_first = seed
    wait_for_stop = wait if wait is not None else stop_event.wait

    def tick() -> None:
        nonlocal failures, seed_first
        use_seed, seed_first = seed_first, False
        try:
            result = facility_once(
                conn, gate, allocator, notifier, sports, now(),
                run=run, seed=use_seed, log=log,
            )
        except Exception as exc:  # a bad round must not kill the thread
            log(f"facility cycle_failed {type(exc).__name__}")
            failures += 1
        else:
            # C4: a WAF latch round or an all-datasets-failed round raises
            # nothing, yet nothing was observed. Escalate those too; only a
            # round that actually read something clears the streak.
            if result.ds_ok < 1:
                log(f"facility cycle_no_datasets ds_ok={result.ds_ok}/{result.ds_total}")
                failures += 1
            else:
                failures = 0
            # I5: "405 → stop now, back off by the Gate ladder". Sleeping the
            # requested seconds here (interruptible) is what makes the ladder
            # real; the normal cadence alone would retry during the latch.
            if result.aborted and result.backoff_seconds > 0:
                log(f"facility waf_backoff seconds={result.backoff_seconds:g}")
                if wait_for_stop(result.backoff_seconds):
                    return
        # C3: retry parked batches once per tick. flush_outbox is deliberately
        # non-blocking (single attempt per channel), so it cannot eat the
        # round's cadence; a failure keeps the row for the next tick.
        try:
            resent = notifier.flush_outbox(conn)
        except Exception as exc:  # a broken outbox must not kill the thread
            log(f"outbox flush_failed {type(exc).__name__}")
        else:
            if resent:
                log(f"outbox resent={resent}")
        try:
            sent = summary(conn, notifier, now())
        except Exception as exc:
            log(f"sale7 summary_failed {type(exc).__name__}")
        else:
            if sent:
                log(f"sale7 summary rows={sent}")
        if failures >= MAX_CONSECUTIVE_FAILURES:
            log(f"facility fatal consecutive_failures={failures}")
            if fatal_event is not None:
                fatal_event.set()
            stop_event.set()

    periodic_loop(
        stop_event, lambda: gate.target_cycle_seconds, tick,
        clock=clock, wait=wait_for_stop,
    )


def activity_loop(
    stop_event: threading.Event,
    *,
    conn,
    gate,
    now: Callable[[], datetime] = lambda: datetime.now(HK),
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], bool] | None = None,
    fatal_event: threading.Event | None = None,
    log: Log = log,
) -> None:
    """activity-prog once every 900s; ``activity_once`` swallows failures.

    R54: ``activity_once`` returns ``False`` for a failure instead of raising,
    so the loop counts consecutive ``False`` results the same way the facility
    loop counts exceptions.
    """
    failures = 0

    def tick() -> None:
        nonlocal failures
        # Spec's "skip if the gate lock waits > 3 min" is deliberately omitted; 900s + hash makes a missed tick harmless.
        try:
            ok = activity_once(conn, gate, now(), log=log)
        except Exception as exc:  # never kill the thread on one transport error
            log(f"activity cycle_failed {type(exc).__name__}")
            ok = False
        failures = 0 if ok else failures + 1
        if failures >= MAX_CONSECUTIVE_FAILURES:
            log(f"activity fatal consecutive_failures={failures}")
            if fatal_event is not None:
                fatal_event.set()
            stop_event.set()

    periodic_loop(
        stop_event, float(ACTIVITY_EVERY_SECONDS), tick,
        clock=clock, wait=wait,
    )


# --- worker thread bodies ---------------------------------------------------


def facility_worker(
    stop_event: threading.Event,
    *,
    settings: Settings,
    gate,
    allocator,
    sports: Iterable[str],
    fatal_event: threading.Event | None = None,
    run: Callable[[Deps], CycleResult] | None = None,
    summary: Callable[[object, object, datetime], int] = run_sale7_summary,
    now: Callable[[], datetime] = lambda: datetime.now(HK),
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], bool] | None = None,
    seed: bool = False,
    log: Log = log,
) -> None:
    """Open the facility connection *inside* this thread, then run the loop.

    SQLite connections are thread-affine (R53): the connection and the
    ``Notifier`` that shares it must be created here and closed here, never
    handed down from ``main()``.
    """
    conn = _open_db(settings.db_path)
    try:
        facility_loop(
            stop_event,
            conn=conn,
            gate=gate,
            allocator=allocator,
            notifier=Notifier(settings, conn=conn),
            sports=sports,
            run=run,
            summary=summary,
            now=now,
            clock=clock,
            wait=wait,
            fatal_event=fatal_event,
            seed=seed,
            log=log,
        )
    finally:
        conn.close()


def activity_worker(
    stop_event: threading.Event,
    *,
    settings: Settings,
    gate,
    fatal_event: threading.Event | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(HK),
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], bool] | None = None,
    log: Log = log,
) -> None:
    """Open the activity connection *inside* this thread and close it here (R53)."""
    conn = _open_db(settings.db_path)
    try:
        activity_loop(
            stop_event,
            conn=conn,
            gate=gate,
            now=now,
            clock=clock,
            wait=wait,
            fatal_event=fatal_event,
            log=log,
        )
    finally:
        conn.close()


# --- process wiring ---------------------------------------------------------


class _TimeoutSession(requests.Session):
    """requests.Session whose requests always carry a connect/read timeout.

    ``Gate.get`` calls ``session.get(url)`` without a timeout; without this
    wrapper a stalled LCSD connection could hold SIGTERM shutdown until
    systemd's stop timeout. 60s read keeps shutdown below systemd's 90s.
    """

    def request(self, method, url, *args, **kwargs):
        kwargs.setdefault("timeout", HTTP_TIMEOUT)
        return super().request(method, url, *args, **kwargs)


# C1 / spec §5.1.1: a bare python-requests UA is an instant WAF latch; the
# anti-bot wants an ordinary browser fetching the JSON from the site itself.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 SmartPlayLive/5.0"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
    "Referer": "https://www.smartplay.lcsd.gov.hk/",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
}


class PersistentCookieSession(_TimeoutSession):
    """Session with browser headers and a cookie jar persisted as JSON.

    The WAF hands out ``acw_tc``/``aliyungf_tc`` cookies; keeping them across
    restarts makes the poller look like one returning client instead of a new
    one every boot. Loading or saving must never abort a cycle: every failure
    is logged and the request goes ahead with whatever jar is in memory.
    """

    def __init__(self, cookies_path: str, log: Log = log) -> None:
        super().__init__()
        self.cookies_path = cookies_path
        self._log = log
        self.headers.update(REQUEST_HEADERS)
        self.load_cookies()

    def request(self, method, url, *args, **kwargs):
        response = super().request(method, url, *args, **kwargs)
        if response.status_code == 200:
            self.save_cookies()
        return response

    def load_cookies(self) -> None:
        try:
            with open(self.cookies_path, encoding="utf-8") as f:
                payload = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as exc:
            self._log(f"cookies load_failed {type(exc).__name__}")
            return
        if not isinstance(payload, list):
            self._log("cookies load_failed not_list")
            return
        for item in payload:
            if not isinstance(item, dict):
                continue
            name, value = item.get("name"), item.get("value")
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            self.cookies.set_cookie(
                requests.cookies.create_cookie(
                    name=name,
                    value=value,
                    domain=item.get("domain") or None,
                    path=item.get("path") or "/",
                )
            )

    def save_cookies(self) -> None:
        payload = [
            {
                "name": cookie.name,
                "value": cookie.value,
                "domain": cookie.domain,
                "path": cookie.path,
            }
            for cookie in self.cookies
        ]
        tmp = self.cookies_path + ".tmp"
        try:
            parent = os.path.dirname(self.cookies_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.cookies_path)
        except OSError as exc:
            self._log(f"cookies save_failed {type(exc).__name__}")
            try:
                os.unlink(tmp)
            except OSError:
                pass


def build_http_session(settings: Settings, log: Log = log) -> requests.Session:
    """The one session every fetch uses (C1: headers + persistent cookies)."""
    return PersistentCookieSession(settings.cookies_path, log=log)


def select_sports(only: str | None) -> list[str]:
    """Translate ``--only`` into the facility sports this process handles."""
    if only is None:
        return list(SPORTS)
    if only == ACTIVITY:
        return []
    if only not in SPORTS:
        raise ValueError(f"unknown dataset: {only}")
    return [only]


def _open_db(path: str):
    conn = db.connect(path)
    conn.execute("PRAGMA busy_timeout=5000")
    db.init_db(conn)
    return conn


def _seq_allocator(settings: Settings) -> SeqAllocator:
    """Build the allocator and seed it from ``MAX(events.seq)`` (I7).

    Rationale: losing ``seq.json`` (fresh volume, cleanup) must not restart
    numbering below rows already in ``events`` — every insert would then hit
    the primary key and crash-loop the round. An empty ``SEQ_URL`` selects the
    R58 local-only mode (Plan 1 has no Worker ``/seq`` route yet).
    """
    url = os.environ.get("SEQ_URL", "").strip()
    token = os.environ.get("SEQ_TOKEN", "").strip()
    local = os.environ.get("SEQ_LOCAL_PATH", "").strip() or str(
        Path(settings.db_path).with_name("seq.json")
    )
    allocator = SeqAllocator(url, token, local)
    try:
        conn = _open_db(settings.db_path)
    except Exception as exc:  # a seed failure must not stop start-up
        log(f"seq seed_skipped {type(exc).__name__}")
        return allocator
    try:
        allocator.seed_at_least(db.max_event_seq(conn))
    except (OSError, ValueError) as exc:
        log(f"seq seed_failed {type(exc).__name__}")
    finally:
        conn.close()
    return allocator


def _plan_text(args: argparse.Namespace) -> str:
    sports = select_sports(args.only)
    activity = args.only is None or args.only == ACTIVITY
    facility = (
        f"{', '.join(sports)} every {CYCLE_SECONDS}s (120s in safe mode)"
        if sports else "(skipped)"
    )
    activity_line = (
        f"{ACTIVITY} every {ACTIVITY_EVERY_SECONDS}s" if activity else "(skipped)"
    )
    return "\n".join(
        [
            "SmartPLAY poller — dry run (no network, no DB writes)",
            f"facility : {facility}",
            f"activity : {activity_line}",
            "summary  : one sale7 summary in 08:10-08:20 HKT, or 15 min "
            "after the last sale7 event",
            "shutdown : SIGTERM/SIGINT sets an event; workers stop between "
            "iterations",
            f"once     : {'yes' if args.once else 'no'}",
            f"seed     : {'yes (first facility round only)' if args.seed else 'no'}",
            f"db       : {os.environ.get('DB_PATH', '/opt/smartplay/state.db')}",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="poller.main", description="SmartPLAY live poller"
    )
    parser.add_argument(
        "--once", action="store_true",
        help="run one iteration of the selected thread(s) and exit",
    )
    parser.add_argument(
        "--only", metavar="DATASET",
        help=f"restrict work to one sport or {ACTIVITY}",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the plan; no network, no database, no credentials",
    )
    parser.add_argument(
        "--seed", action="store_true",
        help="make the first facility round a silent baseline (R59): persist "
             "sessions without emitting events or sending anything",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.only is not None and args.only != ACTIVITY and args.only not in SPORTS:
        parser.error(f"unknown --only value: {args.only}")
    if args.dry_run:
        print(_plan_text(args))
        return 0

    settings = Settings.from_env()
    sports = select_sports(args.only)
    run_activity = args.only is None or args.only == ACTIVITY
    stop_event = threading.Event()
    install_signal_handlers(stop_event)
    gate = Gate(build_http_session(settings))
    allocator = _seq_allocator(settings)

    if args.once:
        conn = _open_db(settings.db_path)
        try:
            if sports:
                result = facility_once(
                    conn, gate, allocator, Notifier(settings, conn=conn),
                    sports, datetime.now(HK), seed=args.seed,
                )
                return 0 if result.ok else 1
            return 0 if activity_once(conn, gate, datetime.now(HK)) else 1
        finally:
            conn.close()

    fatal_event = threading.Event()
    threads: list[threading.Thread] = []
    if sports:
        threads.append(
            threading.Thread(
                name="facility",
                target=facility_worker,
                kwargs={
                    "stop_event": stop_event,
                    "settings": settings,
                    "gate": gate,
                    "allocator": allocator,
                    "sports": sports,
                    "fatal_event": fatal_event,
                    "seed": args.seed,
                },
            )
        )
    if run_activity:
        threads.append(
            threading.Thread(
                name="activity",
                target=activity_worker,
                kwargs={
                    "stop_event": stop_event,
                    "settings": settings,
                    "gate": gate,
                    "fatal_event": fatal_event,
                },
            )
        )

    log(
        f"poller starting sports={','.join(sports) or '-'} "
        f"activity={'on' if run_activity else 'off'} db={settings.db_path}"
    )
    for thread in threads:
        thread.start()
    exit_code = 0
    try:
        while not stop_event.is_set():
            # R54: a worker that keeps failing sets fatal_event; stop the
            # sibling worker and exit non-zero so systemd restarts the unit.
            if fatal_event.is_set():
                exit_code = 1
                break
            # C2: every worker must be alive. With two threads ``any`` let one
            # silent death keep the unit looking healthy while half the
            # pipeline was gone. A dead worker with no fatal_event still
            # escalates: mark fatal, stop the sibling and exit non-zero.
            dead = [thread for thread in threads if not thread.is_alive()]
            if dead:
                log(
                    "poller worker exited unexpectedly name="
                    + ",".join(thread.name for thread in dead)
                )
                fatal_event.set()
                stop_event.set()
                exit_code = 1
                break
            stop_event.wait(LIVENESS_POLL_SECONDS)
    finally:
        stop_event.set()
        for thread in threads:
            thread.join()
    if fatal_event.is_set():
        log("poller fatal worker failure")
        exit_code = 1
    log("poller stopped")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
