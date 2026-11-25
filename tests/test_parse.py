# tests/test_parse.py
"""LCSD row -> compact Session mapping (R19, R20)."""

import json
from datetime import date
from pathlib import Path

from poller.parse import Session, parse_records


def rec(
    d,
    st,
    en,
    c,
    v="測試館",
    f="1號場",
    t="羽毛球場 (空調)(市區)",
):
    # Real LCSD columns: the facility *location* is "1號場"-style; there is
    # no Facility_Name_TC (R19).
    return {
        "Available_Date": d,
        "Session_Start_Time": st + ":00",
        "Session_End_Time": en + ":00",
        "Available_Courts": str(c),
        "Venue_Name_TC": v,
        "Facility_Location_Name_TC": f,
        "Facility_Type_Name_TC": t,
    }


def test_filters_zero_courts_and_out_of_window():
    today = date(2026, 11, 26)
    rows = [
        rec("2026-11-27", "19:00", "20:00", 2),
        rec("2026-11-27", "20:00", "21:00", 0),
        rec("2026-12-31", "19:00", "20:00", 3),
    ]
    out = parse_records("badminton", rows, today)
    assert len(out) == 1 and out[0].courts == 2 and out[0].start == "19:00"


def test_key_is_stable():
    today = date(2026, 11, 26)
    a = parse_records("badminton", [rec("2026-11-27", "19:00", "20:00", 1)], today)[0]
    b = parse_records("badminton", [rec("2026-11-27", "19:00", "20:00", 5)], today)[0]
    assert a.key() == b.key()


def test_facility_is_location_not_type():
    today = date(2026, 11, 26)
    out = parse_records("badminton", [rec("2026-11-27", "19:00", "20:00", 1)], today)
    assert out[0].facility == "1號場"
    assert out[0].facility != out[0].venue


def test_maps_all_fields_and_key_shape():
    today = date(2026, 11, 26)
    out = parse_records("badminton", [rec("2026-11-27", "19:00", "20:00", 4)], today)
    s = out[0]
    assert (s.sport, s.venue, s.facility, s.date, s.start, s.end, s.courts) == (
        "badminton",
        "測試館",
        "1號場",
        date(2026, 11, 27),
        "19:00",
        "20:00",
        4,
    )
    assert s.key() == (
        "badminton",
        "測試館",
        "1號場",
        date(2026, 11, 27),
        "19:00",
        "20:00",
    )


def test_window_is_inclusive_at_both_ends():
    today = date(2026, 11, 26)
    rows = [
        rec("2026-11-25", "19:00", "20:00", 1),
        rec("2026-11-26", "19:00", "20:00", 1),
        rec("2026-12-03", "19:00", "20:00", 1),
        rec("2026-12-04", "19:00", "20:00", 1),
    ]
    out = parse_records("badminton", rows, today, horizon_days=7)
    assert [s.date for s in out] == [date(2026, 11, 26), date(2026, 12, 3)]


def test_strips_venue_and_facility_and_accepts_hhmm_times():
    today = date(2026, 11, 26)
    row = {
        "Available_Date": "2026-11-27",
        "Session_Start_Time": "19:00",
        "Session_End_Time": "20:00",
        "Available_Courts": "3",
        "Venue_Name_TC": " 測試館 ",
        "Facility_Location_Name_TC": " 1號場 ",
        "Facility_Type_Name_TC": "羽毛球場",
    }
    out = parse_records("badminton", [row], today)
    assert len(out) == 1
    assert out[0].venue == "測試館"
    assert out[0].facility == "1號場"
    assert out[0].start == "19:00" and out[0].end == "20:00"


def test_session_has_exactly_six_key_fields():
    assert set(Session.__dataclass_fields__) == {
        "sport",
        "venue",
        "facility",
        "date",
        "start",
        "end",
        "courts",
    }


def test_real_fixture_row_maps_to_location_name():
    rows = json.loads(
        (Path(__file__).parent / "fixtures" / "badminton_sample.json").read_text(
            encoding="utf-8"
        )
    )
    raw = next(r for r in rows if r["Available_Courts"] != "0")
    today = date.fromisoformat(raw["Available_Date"])
    out = parse_records("badminton", [raw], today)
    assert len(out) == 1
    s = out[0]
    assert s.facility == raw["Facility_Location_Name_TC"]
    assert "場" in s.facility
    assert s.start == raw["Session_Start_Time"][:5]
    assert s.end == raw["Session_End_Time"][:5]
    assert s.courts == int(raw["Available_Courts"])
