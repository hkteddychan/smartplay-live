"""PokéStop ledger: traversal samples tied to the auto-spin setting.

    python tools/pokestop_ledger.py --samples 3 --walk 4000

Honest scope: the accessibility layer exposes **no per-stop node** (a PokéStop is
a Unity sprite), so per-stop spun/available cannot be read.  What we can record
is exactly what decides spinning for us:

    position (傳送 panel lat/lng) + time + 快速旋轉 (Switch) + speed

Each row is written to tools/verify/pokestop_ledger.jsonl with
`per_stop_state: null` to make the limitation explicit rather than implied.
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

LEDGER = Path("tools/verify/pokestop_ledger.jsonl")


def metres(a, b) -> float:
    if not a or not b or a[0] is None or b[0] is None:
        return 0.0
    R = 6371000.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--walk", type=int, default=4000)
    args = ap.parse_args()

    stops = L.stop_status()
    print("stop_status:", json.dumps(stops, ensure_ascii=False), flush=True)
    if not stops.get("sniping_disabled"):
        print("ABORT: sniping not verified off", flush=True)
        return 2

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    prev, total = None, 0.0
    for i in range(args.samples):
        D.back_to_map()
        pos = L.position()
        D.back_to_map()
        moved = metres((prev or {}).get("lat") and (prev["lat"], prev["lon"]),
                       pos.get("lat") and (pos["lat"], pos["lon"])) if prev else 0.0
        total += moved
        rec = {
            "t": round(time.time(), 3),
            "i": i,
            "kind": "pokestop_traversal",
            "lat": pos.get("lat"), "lon": pos.get("lon"), "local": pos.get("local"),
            "auto_spin": stops.get("auto_spin"),
            "speed_kmh": stops.get("speed_kmh"),
            "moved_m": round(moved, 1),
            "per_stop_state": None,
            "why_null": "PokéStop is a Unity sprite; the accessibility layer has no node for it",
        }
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"[{i}] {pos.get('lat')},{pos.get('lon')} moved={moved:.1f} m "
              f"auto_spin={rec['auto_spin']}", flush=True)
        prev = pos

        if i + 1 < args.samples:
            D.back_to_map()
            joy = L.joystick()
            if joy is None:                 # the knob only exists on the bare map
                B.tap(*L.STAR)
                time.sleep(1.5)
                D.back_to_map()
                joy = L.joystick()
            print(f"     joystick={joy}", flush=True)
            if joy:
                B.swipe(joy[0], joy[1], joy[0], joy[1] - 190, args.walk)
                time.sleep(1.5)

    print(f"total moved: {total:.1f} m -> {LEDGER}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
