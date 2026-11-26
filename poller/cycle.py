"""One 60-second round: fetch → parse → diff → allocate → persist → notify.

``run_cycle`` owns the cross-cutting rules that the pure modules deliberately
do not:

- **R21 — dataset isolation.** Each sport is fetched *and* parsed inside its
  own try. A failure (bad payload, malformed row, transport error) leaves
  that sport's stored sessions untouched: no delete, no ``gone``, and the
  other four datasets still diff normally.
- **R15 — WAF latch.** ``GateBackoff`` aborts the round immediately. There is
  no in-cycle retry and no session/event write from a partial snapshot; the
  sweep is still logged with ``waf_state="latch"``.
- **R25 — sale7.** After diffing, ``new``/``inc`` events for one sport are
  re-labelled ``sale7`` when (a) the local time is 06:45–08:00 and the event
  date is that sport's furthest bookable date, or (b) the sport produced more
  than 50 ``new``/``inc`` events in this cycle.
- **R24/R42/R44 — resync.** When this round's main allocation falls back to
  local mode (``SeqAllocator.degraded``), a second ``allocate(1)`` reserves
  the resync seq immediately and the placeholder event is persisted in the
  same round, so the gap marker cannot be lost to a crash. A cycle with no
  diffed events never allocates and never emits a resync, even while the
  carried-over ``degraded`` flag is still set.
- **R37/R39 — notification bookkeeping.** ``notified_tg``/``notified_ntfy``
  are marked from ``DeliveryResult.sent_seqs`` + ``via`` only, never from a
  seq range and never for ``dec``/``gone``. A failed delivery whose outbox
  write did not persist is surfaced in ``sweeps.note``.

All IO is injected through :class:`Deps`, so the tested path never sleeps,
reads the wall clock or touches the network.
"""

from __future__ import annotations

import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable

from poller import db
from poller.config import SPORTS
from poller.diff import Event, diff_sessions
from poller.fetch import FetchResult, fetch_dataset
from poller.gate import GateBackoff
from poller.notify import DeliveryResult
from poller.parse import Session, parse_records

BASE_URL = "https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data"

SALE7_WINDOW = ("06:45", "08:00")
SALE7_BURST = 50  # strictly greater than this many new/inc events
RESYNC_DATE = date(1970, 1, 1)


@dataclass
class Deps:
    """Everything one cycle needs, injectable for tests."""

    conn: sqlite3.Connection
    gate: object
    allocator: object
    notifier: object
    now_hk: datetime
    base_url: str = BASE_URL
    fetch: Callable[..., FetchResult] = fetch_dataset
    parse: Callable[..., list[Session]] = parse_records
    diff: Callable[..., list[Event]] = diff_sessions
    clock: Callable[[], float] = time.monotonic
    # Task 11's --only smoke path can narrow a round to one dataset. The
    # default keeps the production five-sport round unchanged.
    sports: list[str] = field(default_factory=lambda: list(SPORTS))


@dataclass
class CycleResult:
    """R41: one round's summary; ``ok`` means all five datasets succeeded."""

    ok: bool
    degraded: bool
    aborted: bool
    ms: int
    bytes: int
    ds_ok: int
    ds_total: int
    waf_state: str
    events: int
    sent: int
    parked: int


def run_cycle(deps: Deps) -> CycleResult:
    """Run one facility-sport round and persist everything it produced."""
    started = deps.clock()
    ts = deps.now_hk.isoformat(timespec="seconds")
    prev = db.load_sessions(deps.conn)
    today_hk = deps.now_hk.date()

    # Phase 1 — network + parsing only. Nothing is written until the whole
    # sweep is known, so a GateBackoff cannot leave a half-applied snapshot.
    outcomes: dict[str, tuple[bool, list[Session], int, str | None]] = {}
    bytes_total = 0
    aborted = False
    for sport in deps.sports:
        try:
            fetched = deps.fetch(deps.gate, deps.base_url, sport)
        except GateBackoff:
            aborted = True
            break
        except Exception as exc:  # R21: one broken dataset must not stop the rest
            outcomes[sport] = (False, [], 0, f"fetch:{type(exc).__name__}")
            continue
        bytes_total += fetched.bytes
        if not fetched.ok:
            outcomes[sport] = (False, [], fetched.bytes, fetched.error or "fetch_failed")
            continue
        try:
            sessions = deps.parse(sport, fetched.records, today_hk)
        except GateBackoff:
            aborted = True
            break
        except Exception as exc:  # R21: a malformed row only fails its own sport
            outcomes[sport] = (False, [], fetched.bytes, f"parse:{type(exc).__name__}")
            continue
        outcomes[sport] = (True, sessions, fetched.bytes, None)

    ds_ok = sum(1 for ok, *_ in outcomes.values() if ok)
    ds_total = len(deps.sports)

    if aborted:
        ms = _elapsed_ms(started, deps.clock())
        # C4: the latch path still owes dataset_status evidence. Only the
        # sports that never produced a result were stopped by the gate; a
        # sport that genuinely succeeded before the latch keeps its status.
        for sport in deps.sports:
            if sport not in outcomes:
                _update_dataset_status(deps.conn, sport, False, 0, ts,
                                       "gate_backoff")
        _log_sweep(deps, ts, ms, bytes_total, ds_ok, ds_total, "latch",
                   "gate_backoff", prune=False)
        return CycleResult(
            ok=False, degraded=ds_ok in (3, 4), aborted=True, ms=ms,
            bytes=bytes_total, ds_ok=ds_ok, ds_total=ds_total,
            waf_state="latch", events=0, sent=0, parked=0,
        )

    # Phase 2 — combine only the datasets that succeeded.
    all_sessions: list[Session] = []
    cur: dict[tuple, int] = {}
    for sport in deps.sports:
        ok, sessions, _, _ = outcomes[sport]
        if not ok:
            continue
        all_sessions.extend(sessions)
        for session in sessions:
            cur[session.key()] = session.courts

    events: list[Event] = []
    for sport in deps.sports:
        if not outcomes[sport][0]:
            continue  # failed sport: keep last version, emit no gone
        prev_sport = {key: count for key, count in prev.items() if key[0] == sport}
        cur_sport = {key: count for key, count in cur.items() if key[0] == sport}
        events.extend(deps.diff(prev_sport, cur_sport, ts))

    furthest = _furthest_dates(cur)
    _apply_sale7(events, deps.now_hk, furthest)

    # Phase 3 — reserve seqs first, then persist state, then events.
    # Reserving before any SQLite write means an allocator failure cannot leave
    # sessions updated without the events that explain the change.
    seq_start = 0
    # R44: only a degradation observed by *this* round's main allocation may
    # raise a resync. The flag is carried over across rounds, so reading it
    # unconditionally would mint a resync — and burn another 1000-seq local
    # block — on every quiet cycle for as long as R2 stays down.
    main_degraded = False
    if events:
        seq_start = deps.allocator.allocate(len(events))
        main_degraded = deps.allocator.degraded
    # R42: a main allocation that fell back to local mode opened a seq gap in
    # *this* round, so reserve the resync seq right away and persist the marker
    # below in the same round. Deferring it to the next round would report the
    # gap a cycle late — or never, if the process dies in between.
    resync: Event | None = None
    resync_seq = 0
    if main_degraded:
        resync_seq = deps.allocator.allocate(1)
        resync = _resync_event(ts)
    if all_sessions:
        db.upsert_sessions(deps.conn, all_sessions, ts)
    gone_keys = [
        (event.sport, event.venue, event.facility, event.date, event.start, event.end)
        for event in events
        if event.kind == "gone"
    ]
    if gone_keys:
        db.delete_sessions(deps.conn, gone_keys)
    if events:
        db.insert_events(deps.conn, events, seq_start)
    if resync is not None:
        db.insert_events(deps.conn, [resync], resync_seq)

    # Phase 4 — notify, then record exactly what a channel accepted.
    delivery = _notify_if_any(deps, events)
    outbox_failed = (
        not delivery.delivered and "outbox_write_failed" in delivery.errors
    )

    for sport in deps.sports:
        ok, _, nbytes, error = outcomes[sport]
        _update_dataset_status(deps.conn, sport, ok, nbytes, ts, error)

    ms = _elapsed_ms(started, deps.clock())
    notes = [f"{sport}:{outcomes[sport][3]}" for sport in deps.sports if not outcomes[sport][0]]
    if outbox_failed:
        notes.append("outbox_write_failed")
    _log_sweep(
        deps, ts, ms, bytes_total, ds_ok, ds_total, deps.gate.state,
        "; ".join(notes) or None,
    )

    return CycleResult(
        ok=ds_ok == len(deps.sports),
        degraded=ds_ok in (3, 4),
        aborted=False,
        ms=ms,
        bytes=bytes_total,
        ds_ok=ds_ok,
        ds_total=ds_total,
        waf_state=deps.gate.state,
        events=len(events) + (1 if resync is not None else 0),
        sent=len(delivery.sent_seqs),
        parked=len(delivery.parked_seqs),
    )


# --- notification ----------------------------------------------------------


def _should_notify(event: Event) -> bool:
    """Only ``new``/``inc`` reach a phone (R43).

    ``sale7`` is deliberately excluded: it is stored unmarked for the 08:15
    HKT summary job (Task 11) instead of being batched through ``send_events``,
    which would produce the 07:00 spam the design forbids. ``dec``/``gone``
    roll up in the database only.
    """
    return event.kind in ("new", "inc")


def _notify_if_any(deps: Deps, events: list[Event]):
    """Send the alert round and mark ``notified_*`` per accepted seq (R37).

    R43 literal: the list handed to ``send_events`` is pre-filtered, so a
    ``sale7`` row is never inside that argument at all.
    """
    candidates = [event for event in events if _should_notify(event)]
    if not candidates:
        return _empty_delivery()
    result = deps.notifier.send_events(candidates, _should_notify)
    _mark_notified(deps.conn, result.sent_seqs, result.via)
    return result


def _empty_delivery() -> DeliveryResult:
    return DeliveryResult(True, None, [], [], [])


def _mark_notified(conn: sqlite3.Connection, seqs: list[int], via: str | None) -> None:
    """Mark the exact seqs on the channel(s) that accepted them.

    ``via`` is aggregated per round ("tg", "ntfy" or "tg+ntfy"), not per
    message, so a mixed round marks every sent seq on both used channels.
    ``sale7`` stays unmarked for the 08:15 summary job (R43), as do
    ``dec``/``gone``, even if a caller hands them in.
    """
    if not seqs or not via:
        return
    channels = set(via.split("+"))
    columns = [column for channel, column in
               (("tg", "notified_tg"), ("ntfy", "notified_ntfy"))
               if channel in channels]
    for column in columns:
        for start in range(0, len(seqs), db.NOTIFY_CHUNK):
            chunk = list(seqs[start:start + db.NOTIFY_CHUNK])
            placeholders = ",".join("?" * len(chunk))
            conn.execute(
                f"UPDATE events SET {column} = 1, notify_err = NULL "
                f"WHERE seq IN ({placeholders}) AND kind IN ('new','inc')",
                chunk,
            )
    conn.commit()


# --- sale7 / resync ---------------------------------------------------------


def _furthest_dates(cur: dict[tuple, int]) -> dict[str, date]:
    """Latest bookable date seen in each sport's successful snapshot."""
    furthest: dict[str, date] = {}
    for sport, _venue, _facility, day, _start, _end in cur:
        if not isinstance(day, date):
            day = date.fromisoformat(day)
        if sport not in furthest or day > furthest[sport]:
            furthest[sport] = day
    return furthest


def _apply_sale7(
    events: list[Event], now_hk: datetime, furthest: dict[str, date]
) -> None:
    """Re-label ``new``/``inc`` as ``sale7`` (R25); never touches dec/gone."""
    counts = Counter(e.sport for e in events if e.kind in ("new", "inc"))
    in_window = SALE7_WINDOW[0] <= now_hk.strftime("%H:%M") <= SALE7_WINDOW[1]
    for event in events:
        if event.kind not in ("new", "inc"):
            continue
        burst = counts[event.sport] > SALE7_BURST
        last_day = furthest.get(event.sport)
        window_hit = in_window and last_day is not None and event.date == last_day
        if burst or window_hit:
            event.kind = "sale7"


def _resync_event(ts: str) -> Event:
    """R24 placeholder identity: events columns are NOT NULL."""
    return Event(
        sport="_system",
        venue="",
        facility="",
        date=RESYNC_DATE,
        start="00:00",
        end="00:00",
        kind="resync",
        before=None,  # type: ignore[arg-type]
        after=None,   # type: ignore[arg-type]
        ts=ts,
    )


# --- telemetry -------------------------------------------------------------


def _update_dataset_status(
    conn: sqlite3.Connection, name: str, ok: bool, nbytes: int,
    ts: str, error: str | None,
) -> None:
    """Track per-dataset success/err_streak (R21); ``bytes`` keeps the last good size."""
    if ok:
        conn.execute(
            "INSERT INTO dataset_status (name, last_ok, last_err, err_streak, bytes) "
            "VALUES (?, ?, NULL, 0, ?) "
            "ON CONFLICT(name) DO UPDATE SET last_ok = excluded.last_ok, "
            "last_err = NULL, err_streak = 0, bytes = excluded.bytes",
            (name, ts, nbytes),
        )
    else:
        conn.execute(
            "INSERT INTO dataset_status (name, last_ok, last_err, err_streak, bytes) "
            "VALUES (?, NULL, ?, 1, 0) "
            "ON CONFLICT(name) DO UPDATE SET last_err = excluded.last_err, "
            "err_streak = dataset_status.err_streak + 1",
            (name, error),
        )
    conn.commit()


def _log_sweep(
    deps: Deps, ts: str, ms: int, nbytes: int, ds_ok: int, ds_total: int,
    waf_state: str, note: str | None, prune: bool = True,
) -> None:
    finished = (deps.now_hk + timedelta(milliseconds=ms)).isoformat(timespec="seconds")
    db.log_sweep(
        deps.conn,
        started_at=ts,
        finished_at=finished,
        ms=ms,
        bytes=nbytes,
        ds_ok=ds_ok,
        ds_total=ds_total,
        waf_state=waf_state,
        note=note,
    )
    if prune:
        db.prune(deps.conn, now=deps.now_hk)


def _elapsed_ms(started: float, stopped: float) -> int:
    return int(round((stopped - started) * 1000))
