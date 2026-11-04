"""Track the avatar's position from the data layer while walking.

    python tools/track.py --samples 4 --walk 6000

Each sample opens the 傳送 panel and parses the current lat/lng (no screenshot),
so the result is a real position track built purely from accessibility nodes.
The track is appended to tools/verify/position_track.jsonl together with the
automation flags that decide PokéStop behaviour (快速旋轉 / speed / sniping).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_direct as D
import pgo_layer as L

LEDGER = Path("tools/verify/position_track.jsonl")


def metres(a, b) -> float:
    """Great-circle distance in metres between two (lat, lon) pairs."""
    if not a or not b or a[0] is None or b[0] is None:
        return 0.0
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = p2 - p1
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=4)
    ap.add_argument("--walk", type=int, default=6000)
    args = ap.parse_args()

    stops = L.stop_status()
    print("stop_status:", json.dumps(stops, ensure_ascii=False))
    LEDGER.parent.mkdir(parents=True, exist_ok=True)

    prev = None
    total = 0.0
    for i in range(args.samples):
        D.back_to_map()
        p = L.position()
        print(f"[{i}] {p}")
        rec = {"i": i, "t": round(time.time(), 3), **p,
               "auto_spin": stops.get("auto_spin"),
               "speed_kmh": stops.get("speed_kmh")}
        if prev:
            d = metres((prev.get("lat"), prev.get("lon")), (p.get("lat"), p.get("lon")))
            rec["moved_m"] = round(d, 1)
            total += d
            print(f"     moved {d:.1f} m")
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        prev = p

        if i + 1 < args.samples:
            D.back_to_map()
            joy = L.joystick()
            print(f"     joystick from layer: {joy}")
            if joy:
                print(f"     walking up {args.walk} ms ...")
                B.swipe(joy[0], joy[1], joy[0], joy[1] - 190, args.walk)
            time.sleep(1.5)

    print(f"total moved: {total:.1f} m -> {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
