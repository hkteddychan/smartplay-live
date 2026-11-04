"""Evening-session feed for the ESP32 browse page.

Builds `esp32/evening-7d.json`: the next 7 days of *evening* slots only,
as a flat table so the ESP32 can hold it in RAM without a DOM.

Schema
------
{
  "g": "2026-11-04 09:00",          # generated-at (HKT) — version fingerprint
  "d": ["2026-11-04", ...],         # the 7 dates, index 0 = today
  "sports": ["badminton", ...],     # sport index table
  "v": ["場地名", ...],              # venue index table
  "s": ["區名", ...],                # district index table
  "r": [[districtIdx, venueIdx, sportIdx, dateIdx, startMin, endMin, courts], ...]
}

Only rows with startMin >= 18:00 and courts >= 1 are kept.
Every district that appears in the source data is listed in "s" — including
districts with no evening slots — so the ESP32's district picker can show
them as empty rather than missing.
"""
from __future__ import annotations

EVE_START_MIN = 18 * 60   # 1080 — 18:00


def _to_min(t: str) -> int:
    h, m = t.split(':')
    return int(h) * 60 + int(m)


def build_evening_feed(records_by_sport: dict, gen_hk: str, dates: list) -> dict:
    """Build the evening-7d.json payload.

    records_by_sport : {sport_name: [record, ...]} — raw LCSD records
    gen_hk           : generation timestamp (HKT) used as the version fingerprint
    dates            : the date window, index 0 = today

    Record fields used: Available_Date, Available_Courts, Venue_Name_TC,
    District_Name_TC, Session_Start_Time, Session_End_Time.
    """
    date_idx = {d: i for i, d in enumerate(dates)}

    sportlist: list[str] = []
    vlist: list[str] = []
    dlist: list[str] = []
    venues: dict[str, int] = {}
    districts: dict[str, int] = {}
    rows: list[list] = []

    # District table first — every district in the source data, even those
    # with no evening slots, so the picker can list them.
    for records in records_by_sport.values():
        for r in records:
            dist = (r.get('District_Name_TC') or '').strip()
            if dist and dist not in districts:
                districts[dist] = len(dlist)
                dlist.append(dist)

    for sport, records in records_by_sport.items():
        si = len(sportlist)
        sportlist.append(sport)
        for r in records:
            d = (r.get('Available_Date') or '').strip()
            if d not in date_idx:
                continue
            try:
                courts = int(r.get('Available_Courts') or 0)
            except (TypeError, ValueError):
                continue
            if courts <= 0:
                continue
            st = (r.get('Session_Start_Time') or '')[:5]
            en = (r.get('Session_End_Time') or '')[:5]
            v = (r.get('Venue_Name_TC') or '').strip()
            dist = (r.get('District_Name_TC') or '').strip()
            if not v or not dist or len(st) != 5 or len(en) != 5:
                continue
            try:
                sm, em = _to_min(st), _to_min(en)
            except ValueError:
                continue
            if sm < EVE_START_MIN:
                continue          # 淨係夜晚
            if em <= sm:
                continue          # 跨午夜嘅時段唔處理
            vi = venues.get(v)
            if vi is None:
                vi = len(vlist)
                venues[v] = vi
                vlist.append(v)
            di = districts[dist]
            rows.append([di, vi, si, date_idx[d], sm, em, courts])

    rows.sort(key=lambda x: (x[3], x[4], x[1]))
    return {
        'g': gen_hk,
        'd': list(dates),
        'sports': sportlist,
        'v': vlist,
        's': dlist,
        'r': rows,
    }
