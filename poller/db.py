"""SQLite persistence for the SmartPLAY poller (spec §5.2).

Single-writer design: ``events.seq`` is assigned by the caller (via the R2
seq allocator) and passed in as ``seq_start`` — never AUTOINCREMENT, so a
primary/fallback handover cannot collide. All timestamps are ISO8601 +08:00,
which makes plain string comparison a valid chronological ordering.

Each write helper commits its own work so a crash between cycles cannot lose
events that were already acknowledged to the caller.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol

from poller.parse import Session

HK = timezone(timedelta(hours=8))

_SCHEMA = Path(__file__).with_name("schema.sql")

EVENT_RETENTION_DAYS = 180
SWEEP_RETENTION_DAYS = 7
ACTIVITY_MIN_RATIO = 0.5  # I4: never replace the snapshot below half its rows
NOTIFY_CHUNK = 500  # rows per IN (...) so a large burst stays under SQLite's limit

BUSY_TIMEOUT_MS = 5000
CONNECT_RETRIES = 3
CONNECT_BACKOFF = (0.2, 0.5, 1.0)


class EventLike(Protocol):
    """Structural stand-in for ``poller.diff.Event`` (Task 7, R22).

    Any object exposing these attributes is accepted; ``seq`` is written by
    :func:`insert_events`, so it must be a mutable attribute.
    """

    sport: str
    venue: str
    facility: str
    date: str
    start: str
    end: str
    kind: str
    before: int
    after: int
    ts: str
    seq: int


def _connect_once(path: str) -> sqlite3.Connection:
    """Open one connection, with ``busy_timeout`` set before the WAL switch.

    R56: ``PRAGMA journal_mode=WAL`` itself takes a lock. Two workers opening
    a brand-new ``state.db`` at the same moment can collide there, so the busy
    timeout must already be in force when that pragma runs.
    """
    conn = sqlite3.connect(path)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.OperationalError:
        conn.close()
        raise
    return conn


def _retry_connect(
    connector: Callable[[], sqlite3.Connection],
    *,
    retries: int = CONNECT_RETRIES,
    backoff: tuple[float, ...] = CONNECT_BACKOFF,
    wait: Callable[[float], object] | None = None,
) -> sqlite3.Connection:
    """Call ``connector``, retrying a locked/busy database with a short backoff.

    R56: a first-start lock race must not kill a worker thread; ``main()``
    only notices a dead pair, so one dead worker would leave the unit
    half-alive. Non-lock operational errors (bad path, bad permissions) are
    real faults and are re-raised immediately.
    """
    pause = wait if wait is not None else time.sleep
    for attempt in range(retries + 1):
        try:
            return connector()
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" not in message and "busy" not in message:
                raise
            if attempt == retries:
                raise
            pause(backoff[min(attempt, len(backoff) - 1)])
    raise AssertionError("unreachable")  # pragma: no cover


def connect(
    path: str,
    *,
    stop_event: threading.Event | None = None,
    sleep: Callable[[float], object] | None = None,
) -> sqlite3.Connection:
    """Open the database with WAL journalling and dict-like rows.

    On ``:memory:`` the WAL pragma reports ``memory`` instead of ``wal``;
    that is expected and harmless. A locked database is retried up to
    ``CONNECT_RETRIES`` times (R56); pass ``stop_event`` to make the backoff
    interruptible or ``sleep`` to inject a deterministic waiter in tests.
    """
    wait = sleep if sleep is not None else (
        stop_event.wait if stop_event is not None else None
    )
    return _retry_connect(lambda: _connect_once(path), wait=wait)


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema if absent (idempotent), then apply small migrations."""
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    _migrate(conn)
    conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a database was first created.

    ``CREATE TABLE IF NOT EXISTS`` does not touch an existing table, so a
    unit that upgrades in place would otherwise miss ``dataset_status.records``
    (I3) until the DB is rebuilt.
    """
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(dataset_status)")
    }
    if "records" not in columns:
        conn.execute("ALTER TABLE dataset_status ADD COLUMN records INTEGER")


def dataset_record_count(conn: sqlite3.Connection, name: str) -> int | None:
    """Latest successful row count for ``name`` (I3 baseline), or None."""
    row = conn.execute(
        "SELECT records FROM dataset_status WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        return None
    value = row["records"]
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _date_text(value: date | str) -> str:
    """Session.date is a ``date``; diff keys carry ISO strings. Accept both."""
    return value.isoformat() if isinstance(value, date) else str(value)


def upsert_sessions(
    conn: sqlite3.Connection, sessions: list[Session], now_iso: str,
    *, commit: bool = True,
) -> None:
    """Insert or refresh sessions; never delete absentees (diff decides that).

    ``first_seen`` is kept from the original insert; ``last_seen`` and
    ``courts`` track the latest sweep. ``commit=False`` lets the cycle layer
    group this write with ``delete_sessions``/``insert_events`` in one
    transaction (I1).
    """
    conn.executemany(
        """
        INSERT INTO sessions
          (sport, venue, facility, date, start, "end", courts, first_seen, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(sport, venue, facility, date, start, "end") DO UPDATE SET
          courts = excluded.courts,
          last_seen = excluded.last_seen
        """,
        [
            (
                s.sport,
                s.venue,
                s.facility,
                _date_text(s.date),
                s.start,
                s.end,
                s.courts,
                now_iso,
                now_iso,
            )
            for s in sessions
        ],
    )
    if commit:
        conn.commit()


def load_sessions(conn: sqlite3.Connection) -> dict[tuple, int]:
    """Snapshot ``{Session.key(): courts}`` for the diff engine (R40).

    Dates are read back as ISO text — the same ``_date_text`` format
    ``upsert_sessions`` writes — which ``diff_sessions`` normalises back to
    ``date``.
    """
    rows = conn.execute(
        'SELECT sport, venue, facility, date, start, "end", courts FROM sessions'
    ).fetchall()
    return {
        (
            row["sport"],
            row["venue"],
            row["facility"],
            _date_text(row["date"]),
            row["start"],
            row["end"],
        ): row["courts"]
        for row in rows
    }


def delete_sessions(
    conn: sqlite3.Connection, keys: list[tuple], *, commit: bool = True
) -> None:
    """Remove sessions by their 6-tuple identity (sport, venue, facility, date, start, end)."""
    conn.executemany(
        """
        DELETE FROM sessions
        WHERE sport = ? AND venue = ? AND facility = ?
          AND date = ? AND start = ? AND "end" = ?
        """,
        [(k[0], k[1], k[2], _date_text(k[3]), k[4], k[5]) for k in keys],
    )
    if commit:
        conn.commit()


def insert_events(
    conn: sqlite3.Connection, events: list[EventLike], seq_start: int,
    *, commit: bool = True,
) -> list[int]:
    """Assign ``seq_start + i`` to ``events[i].seq``, insert, return the seqs (R4)."""
    seqs: list[int] = []
    for i, ev in enumerate(events):
        ev.seq = seq_start + i
        seqs.append(ev.seq)
        conn.execute(
            """
            INSERT INTO events
              (seq, ts, sport, venue, facility, date, start, "end", kind, before, after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ev.seq,
                ev.ts,
                ev.sport,
                ev.venue,
                ev.facility,
                _date_text(ev.date),
                ev.start,
                ev.end,
                ev.kind,
                ev.before,
                ev.after,
            ),
        )
    if commit:
        conn.commit()
    return seqs


def fetch_unsent_sale7(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Sale7 rows no channel has delivered yet (R46).

    "Unsent" means **both** channel flags are still 0: once either channel
    accepted the summary the row must not be included in the next one.
    """
    return conn.execute(
        'SELECT seq, ts, sport, venue, facility, date, start, "end", before, after '
        "FROM events "
        "WHERE kind = 'sale7' AND notified_tg = 0 AND notified_ntfy = 0 "
        "ORDER BY seq"
    ).fetchall()


def mark_sale7_notified(
    conn: sqlite3.Connection, seqs: list[int], channel: str
) -> int:
    """Mark exactly ``seqs`` on the channel(s) that accepted a sale7 summary.

    ``channel`` is ``"tg"``, ``"ntfy"`` or ``"tg+ntfy"``. The ``kind`` guard
    makes the helper safe even if a caller passes a mixed seq list: a sale7
    summary must never mark an ordinary ``new``/``inc`` row. Returns the
    number of sale7 rows touched by the first updated column.
    """
    if not seqs or not channel:
        return 0
    channels = set(channel.split("+"))
    columns = [
        column
        for name, column in (("tg", "notified_tg"), ("ntfy", "notified_ntfy"))
        if name in channels
    ]
    if not columns:
        return 0
    marked = 0
    for column in columns:
        total = 0
        for start in range(0, len(seqs), NOTIFY_CHUNK):
            chunk = list(seqs[start:start + NOTIFY_CHUNK])
            placeholders = ",".join("?" * len(chunk))
            cursor = conn.execute(
                f"UPDATE events SET {column} = 1, notify_err = NULL "
                f"WHERE seq IN ({placeholders}) AND kind = 'sale7'",
                chunk,
            )
            total += cursor.rowcount
        marked = max(marked, total)
    conn.commit()
    return marked


def _activity_rows(records: list[dict]) -> list[tuple[str, str]]:
    """Compact ``(activity_no, payload)`` rows, sorted for a stable hash.

    Records without an ``ACTIVITY_NO`` are skipped (one bad upstream row must
    not abort the whole snapshot). Sorting makes an upstream re-order look
    like what it is: no change.
    """
    rows = []
    for record in records:
        if not isinstance(record, dict):
            continue
        activity_no = record.get("ACTIVITY_NO")
        if not isinstance(activity_no, str) or not activity_no.strip():
            continue
        rows.append(
            (
                activity_no.strip(),
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
            )
        )
    rows.sort()
    return rows


def _snapshot_hash(rows: list[tuple[str, str]]) -> str:
    """SHA-256 over the compact payload actually written to ``activities``."""
    digest = hashlib.sha256()
    for activity_no, payload in rows:
        digest.update(activity_no.encode("utf-8"))
        digest.update(b"\x1f")
        digest.update(payload.encode("utf-8"))
        digest.update(b"\x1e")
    return digest.hexdigest()


def upsert_activities(
    conn: sqlite3.Connection, records: list[dict], now_iso: str,
    *, log: Callable[[str], None] | None = None,
) -> int:
    """Store ``records`` as the activity snapshot, but only when it changed.

    R51: the payload is ~15MB, so rewriting it every tick would cost ~4GB/day
    of SQLite writes. ``activity_meta`` keeps the hash of the compact payload;
    ``activities`` is rewritten (delete-all + insert in one transaction) only
    when that hash differs. ``activity_meta.updated_at`` is refreshed on every
    non-empty payload so staleness stays observable.

    Each row keeps its original JSON payload keyed by ``ACTIVITY_NO``;
    ``first_seen`` survives a refresh while ``last_seen`` is the current run.
    Rows absent from this run are deleted, so the table is a snapshot rather
    than an ever-growing archive. A payload with no usable records is a no-op,
    leaving the previous snapshot intact. Returns the number of rows written
    (``0`` means nothing was written).
    """
    rows = _activity_rows(records)
    if not rows:
        return 0
    # I4: a truncated download must not wipe a good 15MB snapshot. The first
    # success has no baseline; afterwards half the stored row count is the
    # floor (a real programme list does not halve between runs).
    stored_rows = conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    if stored_rows and len(rows) < stored_rows * ACTIVITY_MIN_RATIO:
        if log is not None:
            log(
                f"activity rejected suspiciously_small "
                f"records={len(rows)} stored={stored_rows}"
            )
        return 0

    snapshot_hash = _snapshot_hash(rows)
    meta = conn.execute(
        "SELECT hash FROM activity_meta WHERE id = 1"
    ).fetchone()
    if meta is not None and meta["hash"] == snapshot_hash:
        conn.execute(
            "UPDATE activity_meta SET updated_at = ? WHERE id = 1", (now_iso,)
        )
        conn.commit()
        return 0

    first_seen = {
        row["activity_no"]: row["first_seen"]
        for row in conn.execute("SELECT activity_no, first_seen FROM activities")
    }
    with conn:
        conn.execute("DELETE FROM activities")
        conn.executemany(
            """
            INSERT INTO activities (activity_no, payload, first_seen, last_seen)
            VALUES (?, ?, ?, ?)
            """,
            [
                (activity_no, payload, first_seen.get(activity_no, now_iso), now_iso)
                for activity_no, payload in rows
            ],
        )
        conn.execute(
            """
            INSERT INTO activity_meta (id, hash, updated_at)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              hash = excluded.hash,
              updated_at = excluded.updated_at
            """,
            (snapshot_hash, now_iso),
        )
    return len(rows)


def log_sweep(conn: sqlite3.Connection, **kw) -> None:
    """Record one sweep's telemetry; unspecified columns stay NULL."""
    columns = (
        "started_at",
        "finished_at",
        "ms",
        "bytes",
        "ds_ok",
        "ds_total",
        "waf_state",
        "note",
    )
    unknown = set(kw) - set(columns)
    if unknown:
        raise TypeError(f"unknown sweep fields: {sorted(unknown)}")
    conn.execute(
        f"INSERT INTO sweeps ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        [kw.get(col) for col in columns],
    )
    conn.commit()


def prune(conn: sqlite3.Connection, now: datetime | None = None) -> None:
    """Retention (spec §5.2): events 180 days → rollup then delete; sweeps 7 days.

    Expired events are aggregated into ``daily_rollup`` *before* deletion so
    history survives as per-day counts. Comparisons are parameterised string
    comparisons on ISO8601 +08:00 timestamps.
    """
    if now is None:
        now = datetime.now(tz=HK)
    if now.tzinfo is None:
        now = now.replace(tzinfo=HK)
    now = now.astimezone(HK)
    events_cutoff = (now - timedelta(days=EVENT_RETENTION_DAYS)).isoformat()
    sweeps_cutoff = (now - timedelta(days=SWEEP_RETENTION_DAYS)).isoformat()

    conn.execute(
        """
        INSERT INTO daily_rollup (day, sport, venue, kind, n)
        SELECT substr(ts, 1, 10), sport, venue, kind, COUNT(*)
        FROM events
        WHERE ts < ?
        GROUP BY substr(ts, 1, 10), sport, venue, kind
        ON CONFLICT(day, sport, venue, kind) DO UPDATE SET n = n + excluded.n
        """,
        (events_cutoff,),
    )
    conn.execute("DELETE FROM events WHERE ts < ?", (events_cutoff,))
    conn.execute("DELETE FROM sweeps WHERE started_at < ?", (sweeps_cutoff,))
    conn.commit()
