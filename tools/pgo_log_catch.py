"""Log one encounter+catch with the layer-derived coordinates.

    python tools/pgo_log_catch.py --tap 551 1640
    python tools/pgo_log_catch.py --here          # assume an encounter is already open

Writes rows into tools/verify/observations.jsonl:
  {"kind":"encounter","lat":..,"lon":..,"mon":{L,IV,split,...}}
  {"kind":"catch","lat":..,"lon":..,"mon":{...},"throws":n}

lat/lon come from the 傳送 panel (data layer), never from a screenshot.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_direct as D
import pgo_layer as L

LEDGER = Path("tools/verify/observations.jsonl")


def log(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tap", nargs=2, type=int, metavar=("X", "Y"))
    ap.add_argument("--here", action="store_true")
    ap.add_argument("--settle", type=float, default=6.0)
    ap.add_argument("--pos-after", action="store_true",
                    help="tap first, read coordinates after the catch (less drift)")
    args = ap.parse_args()

    # 1. location
    pos = {}
    if not args.pos_after:
        D.back_to_map()
        pos = L.position()
        D.back_to_map()
        print("position:", pos)

    # 2. open the encounter
    if not args.here:
        if not args.tap:
            print("need --tap X Y or --here")
            return 2
        if L.state() == "raid":
            print("R5: raid sheet -> closing")
            L.leave_raid()
            return 1
        B.tap(args.tap[0], args.tap[1])
        time.sleep(args.settle)

    st = L.state()
    print("state:", st)
    if st == "raid":
        print("R5: raid opened by the tap -> closing, not joining")
        L.leave_raid()
        return 1
    if st != "encounter":
        print("no encounter opened")
        return 1

    mon = L.mon()
    res = L.catch()
    print("catch:", json.dumps(res, ensure_ascii=False))

    if args.pos_after:
        D.back_to_map()
        pos = L.position()
        D.back_to_map()
        print("position (read after catch):", pos)

    enc = {"t": round(time.time(), 3), "kind": "encounter",
           "lat": pos.get("lat"), "lon": pos.get("lon"),
           "local": pos.get("local"), "mon": mon}
    log(enc)
    print("logged encounter:", json.dumps(enc, ensure_ascii=False))

    if res.get("caught"):
        log({"t": round(time.time(), 3), "kind": "catch",
             "lat": pos.get("lat"), "lon": pos.get("lon"),
             "mon": res.get("mon"), "throws": res.get("throws"),
             "ball": res.get("ball")})
    return 0 if res.get("caught") else 1


if __name__ == "__main__":
    raise SystemExit(main())
