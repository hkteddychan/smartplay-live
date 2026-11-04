"""Contract tests for the SmartPLAY feed generator's evening-7d.json output.

The ESP32 browse page consumes esp32/evening-7d.json.  This test pins the
shape of that file so the firmware and the source can never drift apart:

  r rows = [districtIdx, venueIdx, sportIdx, dateIdx, startMin, endMin, courts]
  s       = all districts (even the ones with no evening slots)
  d       = 7 dates
  only rows with startMin >= 1080 (18:00) and courts >= 1

Run:  python -m pytest test/test_evening_feed.py -v
"""
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "patches"))

from evening_feed import build_evening_feed  # noqa: E402

DATES7 = ["2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07",
          "2026-11-08", "2026-11-09", "2026-11-10"]

# 18 districts — two of them never have an evening slot
DISTRICTS = [
    "離島區", "北區", "東區", "南區", "黃大仙區", "觀塘區", "西貢區", "深水埗區",
    "屯門區", "大埔區", "元朗區", "九龍城區", "油尖旺區", "荃灣區", "沙田區",
    "中西區", "灣仔區", "油尖旺區",
]


def rec(date, start, end, courts, venue="香港單車館", district="九龍城區"):
    return {
        "Available_Date": date,
        "Available_Courts": str(courts),
        "Venue_Name_TC": venue,
        "District_Name_TC": district,
        "Facility_Location_Name_TC": "主場",
        "Session_Start_Time": start,
        "Session_End_Time": end,
    }


FAKE = {
    "badminton": [
        rec("2026-11-04", "18:00", "19:00", 3),
        rec("2026-11-05", "19:30", "21:00", 1, venue="蒲崗村道體育館", district="黃大仙區"),
        rec("2026-11-04", "07:00", "08:00", 7),          # daytime -> filtered out
        rec("2026-11-04", "07:00", "09:00", 4, district="灣仔區"),  # daytime only district
        rec("2026-11-04", "18:00", "19:00", 0),          # no courts -> filtered out
        rec("2026-11-20", "18:00", "19:00", 2),          # outside the 7 day window
    ],
    "basketball": [
        rec("2026-11-06", "20:00", "21:00", 2, venue="佛光街體育館", district="九龍城區"),
    ],
    "volleyball": [],
    "tennis": [],
    "turf-soccer-pitch": [],
}


class EveningFeedTests(unittest.TestCase):
    def setUp(self):
        self.out = build_evening_feed(FAKE, "2026-11-04 09:00", DATES7)

    def test_only_keeps_evening_rows(self):
        for r in self.out["r"]:
            self.assertGreaterEqual(r[4], 1080, "只准留 18:00 之後嘅時段")

    def test_drops_rows_with_no_courts(self):
        for r in self.out["r"]:
            self.assertGreaterEqual(r[6], 1, "冇場嘅時段唔應該出現")

    def test_keeps_all_seven_dates(self):
        self.assertEqual(self.out["d"], DATES7)
        for r in self.out["r"]:
            self.assertIn(r[3], range(7), "日期 index 必須喺 0..6")

    def test_row_shape_and_indices(self):
        for r in self.out["r"]:
            self.assertEqual(len(r), 7)
            self.assertLess(r[0], len(self.out["s"]), "區 index 越界")
            self.assertLess(r[1], len(self.out["v"]), "場地 index 越界")
            self.assertLess(r[2], len(self.out["sports"]), "運動 index 越界")
            self.assertLess(r[3], 7)
            self.assertLess(r[4], r[5], "完場時間要遲過開場")

    def test_keeps_districts_that_only_have_daytime_slots(self):
        # 夜晚冇場嘅區都要喺選擇器出現（但唔會有夜晚行）
        self.assertIn("灣仔區", self.out["s"])
        evening_districts = {self.out["s"][r[0]] for r in self.out["r"]}
        self.assertNotIn("灣仔區", evening_districts, "灣仔區夜晚冇場，唔應該有夜晚行")

    def test_version_fingerprint(self):
        self.assertEqual(self.out["g"], "2026-11-04 09:00")

    def test_sport_table_is_flat(self):
        self.assertIsInstance(self.out["sports"], list)
        self.assertIn("badminton", self.out["sports"])

    def test_venue_and_district_tables_are_deduped(self):
        self.assertEqual(len(self.out["v"]), len(set(self.out["v"])), "場地名表要 dedup")
        self.assertEqual(len(self.out["s"]), len(set(self.out["s"])), "區名表要 dedup")

    def test_evening_rows_are_actually_kept(self):
        self.assertGreaterEqual(len(self.out["r"]), 3,
                                "18:00 之後嘅時段一定要留低")


if __name__ == "__main__":
    unittest.main()
