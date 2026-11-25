"""SQLite persistence for the SmartPLAY poller (spec §5.2).

Single-writer design: ``events.seq`` is assigned by the caller (via the R2
seq allocator) and passed in as ``seq_start`` — never AUTOINCREMENT, so a
primary/fallback handover cannot collide. All timestamps are ISO8601 +08:00,
which makes plain string comparison a valid chronological ordering.

Each write helper commits its own work so a crash between cycles cannot lose
events that were already acknowledged to the caller.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from poller.parse import Session

HK = timezone(timedelta(hours=8))

_SCHEMA = Path(__file__).with_name("schema.sql")

EVENT_RETENTION_DAYS = 180
SWEEP_RETENTION_DAYS = 7


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


def connect(path: str) -> sqlite3.Connection:
    """Open the database with WAL journalling and dict-like rows.

    On ``:memory:`` the WAL pragma reports ``memory`` instead of ``wal``;
    that is expected and harmless.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create the schema if absent (idempotent)."""
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))


def _date_text(value: date | str) -> str:
    """Session.date is a ``date``; diff keys carry ISO strings. Accept both."""
    return value.isoformat() if isinstance(value, date) else str(value)


def upsert_sessions(
    conn: sqlite3.Connection, sessions: list[Session], now_iso: str
) -> None:
    """Insert or refresh sessions; never delete absentees (diff decides that).

    ``first_seen`` is kept from the original insert; ``last_seen`` and
    ``courts`` track the latest sweep.
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


def delete_sessions(conn: sqlite3.Connection, keys: list[tuple]) -> None:
    """Remove sessions by their 6-tuple identity (sport, venue, facility, date, start, end)."""
    conn.executemany(
        """
        DELETE FROM sessions
        WHERE sport = ? AND venue = ? AND facility = ?
          AND date = ? AND start = ? AND "end" = ?
        """,
        [(k[0], k[1], k[2], _date_text(k[3]), k[4], k[5]) for k in keys],
    )
    conn.commit()


def insert_events(
    conn: sqlite3.Connection, events: list[EventLike], seq_start: int
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
    conn.commit()
    return seqs


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
