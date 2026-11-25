"""Pure change detection: previous availability counts vs current counts.

This module is deliberately IO-free. ``diff_sessions`` only looks at the two
count dictionaries and the timestamp it is given, which keeps the product's
truth (what counts as a change) testable without HTTP or SQLite.

R25: the diff emits **only** ``new``/``inc``/``dec``/``gone``. ``sale7`` and
``resync`` are classifications added later by the cycle layer, which has the
cross-event context the pure function lacks.

R26: ``Event.date`` stays a ``date`` object (same as ``Session.date``) so the
database layer can format it; ``Event.ts`` is the caller's ISO8601 +08:00
string. ``seq`` is assigned by ``db.insert_events``, never here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass
class Event:
    sport: str
    venue: str
    facility: str
    date: date
    start: str
    end: str
    kind: str
    before: int
    after: int
    ts: str
    seq: int = 0


def _as_date(value: date | str) -> date:
    """Keys arrive with a ``date`` (parse) or an ISO string (SQLite rows)."""
    return value if isinstance(value, date) else date.fromisoformat(value)


def _normalise(key: tuple) -> tuple[str, str, str, date, str, str]:
    sport, venue, facility, day, start, end = key
    return (sport, venue, facility, _as_date(day), start, end)


def diff_sessions(
    prev: dict[tuple, int], cur: dict[tuple, int], ts: str
) -> list[Event]:
    """Turn two count snapshots into events.

    ``new``/``inc``/``dec`` follow ``cur`` insertion order, then ``gone``
    follows ``prev`` insertion order, so the result is reproducible for a
    given pair of dicts. A key that is unchanged, or that was already absent,
    emits nothing; ``gone`` requires ``before > 0`` so a zero-count entry in
    ``prev`` cannot produce a spurious removal.
    """
    prev_counts = {_normalise(k): n for k, n in prev.items()}
    cur_counts = {_normalise(k): n for k, n in cur.items()}

    events: list[Event] = []
    for (sport, venue, facility, day, start, end), after in cur_counts.items():
        before = prev_counts.get((sport, venue, facility, day, start, end))
        if before is None:
            kind = "new"
            before = 0
        elif after > before:
            kind = "inc"
        elif after < before:
            kind = "dec"
        else:
            continue
        events.append(
            Event(
                sport=sport,
                venue=venue,
                facility=facility,
                date=day,
                start=start,
                end=end,
                kind=kind,
                before=before,
                after=after,
                ts=ts,
            )
        )

    for (sport, venue, facility, day, start, end), before in prev_counts.items():
        if (sport, venue, facility, day, start, end) in cur_counts or before <= 0:
            continue
        events.append(
            Event(
                sport=sport,
                venue=venue,
                facility=facility,
                date=day,
                start=start,
                end=end,
                kind="gone",
                before=before,
                after=0,
                ts=ts,
            )
        )
    return events


def is_alerting(event: Event) -> bool:
    """Only availability appearing is worth waking a phone (spec §5.3)."""
    return event.kind in ("new", "inc")


def is_evening(event: Event) -> bool:
    """True for slots starting at or after 18:00; ``HH:MM`` compares as text."""
    return event.start >= "18:00"
