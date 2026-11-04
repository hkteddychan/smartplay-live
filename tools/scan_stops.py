"""Record every PokéStop seen by the on-device scan, with its state.

    python tools/scan_stops.py

The scan runs on the phone (screenshot never leaves it) and returns
{x, y, state} per object.  We pair that with the player's lat/lng read from the
傳送 panel, so poke-stop status finally lands in the ledger as real values
instead of null.

Rows go to tools/verify/pokestop_ledger.jsonl:
  {"kind":"stop_observation","lat":..,"lon":..,"sx":..,"sy":..,"state":"free|spun"}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_direct as D
import pgo_layer as L

LEDGER = Path("tools/verify/pokestop_ledger.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    args = ap.parse_args()

    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    for r in range(args.rounds):
        D.back_to_map()
        pos = L.position()
        D.back_to_map()
        if L.state() != "map":                 # the knob/scan only makes sense on map
            D.back_to_map()
        res = L.scan()
        if not res.get("ok"):
            print(f"[{r}] scan failed: {res.get('raw', '')[:120]}")
            continue
        print(f"[{r}] state={L.state()} scan ms={res['ms']} objects={len(res['objects'])} "
              f"pos={pos.get('lat')},{pos.get('lon')}")
        for o in res["objects"]:
            if not o["kind"].startswith("stop"):
                continue
            rec = {"t": round(time.time(), 3), "kind": "stop_observation",
                   "lat": pos.get("lat"), "lon": pos.get("lon"),
                   "local": pos.get("local"),
                   "sx": o["x"], "sy": o["y"],
                   "state": "free" if o["kind"] == "stop_free" else "spun",
                   "orange": o["orange"], "violet": o["violet"]}
            with LEDGER.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total += 1
            print(f"    stop {o['x']:>4},{o['y']:>4} -> {rec['state']}")
    print(f"wrote {total} stop observations -> {LEDGER}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
