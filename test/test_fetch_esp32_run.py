"""End-to-end test: run the patched feed generator and check its output files.

Builds a throwaway repo layout (data/*.json + esp32/), runs
patches/fetch_esp32.py in it, and asserts the generated files are correct —
especially esp32/evening-7d.json, which the ESP32 browse page consumes.

Run:  python -m pytest test/test_fetch_esp32_run.py -v
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
PATCHES = os.path.join(_ROOT, "patches")

SPORTS = ["badminton", "basketball", "volleyball", "tennis", "turf-soccer-pitch"]


def rec(date, start, end, courts, venue, district):
    return {
        "Available_Date": date,
        "Available_Courts": str(courts),
        "Venue_Name_TC": venue,
        "District_Name_TC": district,
        "Facility_Location_Name_TC": "主場",
        "Session_Start_Time": start,
        "Session_End_Time": end,
    }


class GeneratorRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="fetch_esp32_")
        os.makedirs(os.path.join(cls.tmp, "data"))
        os.makedirs(os.path.join(cls.tmp, "esp32"))
        for name in ("fetch_esp32.py", "evening_feed.py"):
            shutil.copy(os.path.join(PATCHES, name), os.path.join(cls.tmp, "esp32", name))

        # two districts, one of them only has daytime slots
        with open(os.path.join(cls.tmp, "data", "badminton.json"), "w", encoding="utf-8") as f:
            json.dump([
                rec("2026-11-04", "18:00", "19:00", 3, "香港單車館", "九龍城區"),
                rec("2026-11-05", "19:30", "21:00", 1, "蒲崗村道體育館", "黃大仙區"),
                rec("2026-11-04", "07:00", "08:00", 7, "柏立灣公園", "灣仔區"),
            ], f)
        for sport in SPORTS[1:]:
            with open(os.path.join(cls.tmp, "data", f"{sport}.json"), "w", encoding="utf-8") as f:
                json.dump([], f)

        cls.proc = subprocess.run(
            [sys.executable, os.path.join(cls.tmp, "esp32", "fetch_esp32.py")],
            capture_output=True, text=True, cwd=cls.tmp, timeout=120,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def out(self, name):
        with open(os.path.join(self.tmp, "esp32", name), encoding="utf-8") as f:
            return json.load(f)

    def test_generator_ran(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stdout + self.proc.stderr)

    def test_evening_file_exists(self):
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "esp32", "evening-7d.json")))

    def test_evening_file_content(self):
        data = self.out("evening-7d.json")
        self.assertEqual(len(data["r"]), 2, "只有兩個夜晚時段")
        for r in data["r"]:
            self.assertGreaterEqual(r[4], 1080)
            self.assertEqual(len(r), 7)
        self.assertIn("灣仔區", data["s"], "只有日場嘅區都要喺區表入面")
        self.assertEqual(len(data["d"]), 7)

    def test_index_lists_the_new_file(self):
        idx = self.out("index.json")
        self.assertIn("evening-7d.json", idx["files"])

    def test_today_file_still_generated(self):
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "esp32", "today.json")))

    def test_evening_file_is_small(self):
        size = os.path.getsize(os.path.join(self.tmp, "esp32", "evening-7d.json"))
        self.assertLess(size, 40 * 1024, "新 feed 要細，唔可以重過 today.json")


if __name__ == "__main__":
    unittest.main()
