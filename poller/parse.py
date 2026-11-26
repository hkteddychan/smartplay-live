"""Map raw LCSD availability rows onto compact, diffable sessions.

Downstream change detection keys entirely on ``Session.key()``, so the six
dimensions here (sport, venue, facility, date, start, end) must be stable:
``courts`` is deliberately excluded because it is the value being watched,
not part of the identity.

The facility is the *location* column (``Facility_Location_Name_TC``, e.g.
``1號場``), never the facility type (R19). Type suffixes such as
``(空調)(市區)`` are legitimate and are left untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

_TIME_FORMATS = ("%H:%M:%S", "%H:%M")


@dataclass
class Session:
    sport: str
    venue: str
    facility: str
    date: date
    start: str
    end: str
    courts: int

    def key(self) -> tuple[str, str, str, date, str, str]:
        """Identity without availability: a court-count change is not a new slot."""
        return (self.sport, self.venue, self.facility, self.date, self.start, self.end)


def _hhmm(value: str) -> str:
    """Normalise an LCSD time (``19:00`` or ``19:00:00``) to ``HH:MM``."""
    text = value.strip()
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    raise ValueError(f"unrecognised session time: {value!r}")


def parse_records(
    sport: str,
    records: list[dict],
    today_hk: date,
    horizon_days: int = 7,
) -> list[Session]:
    """Keep bookable rows inside the inclusive HK-local booking window."""
    window_end = today_hk + timedelta(days=horizon_days)
    sessions: list[Session] = []
    for record in records:
        courts = int(record["Available_Courts"])
        if courts <= 0:
            continue
        day = date.fromisoformat(record["Available_Date"])
        if not today_hk <= day <= window_end:
            continue
        sessions.append(
            Session(
                sport=sport,
                venue=record["Venue_Name_TC"].strip(),
                facility=record["Facility_Location_Name_TC"].strip(),
                date=day,
                start=_hhmm(record["Session_Start_Time"]),
                end=_hhmm(record["Session_End_Time"]),
                courts=courts,
            )
        )
    return sessions
