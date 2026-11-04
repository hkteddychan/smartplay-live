"""Collect encounter samples + catches by probing the ground around the avatar.

    python tools/pgo_collect.py --target 3

Wild spawns cluster next to the player, so instead of trying to recognise
sprites we probe a ring of offsets around the avatar.  Every probe is decided
from the data layer afterwards:

  * state becomes "encounter" -> read mon() from the layer, catch, log
  * anything else              -> next offset

No screenshot is needed at all.  R1/R2/R5 guards apply as everywhere else.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_layer as L

AVATAR = (540, 1500)
# ring of probe offsets, nearest first
OFFSETS = [
    (0, -150), (-140, -110), (140, -110),
    (-190, 40), (190, 40), (0, 120),
    (-260, -180), (260, -180), (0, -280),
    (-320, 120), (320, 120), (0, 260),
]
SETTLE = 3.5


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=6)
    ap.add_argument("--settle", type=float, default=SETTLE)
    args = ap.parse_args()

    got, throws = 0, 0
    for r in range(args.rounds):
        if got >= args.target:
            break
        st = L.state()
        print(f"[{r + 1}/{args.rounds}] state={st} got={got}", flush=True)
        if st == "raid":
            print("  R5: closing raid sheet")
            L.leave_raid()
            time.sleep(args.settle)
            continue
        if st in ("mon_detail", "settings", "pg_side_menu"):
            B.back()
            time.sleep(args.settle)
            continue
        if st == "encounter":
            res = L.catch()
            throws += res.get("throws", 0)
            if res.get("caught"):
                got += 1
                print(f"  CAUGHT {res['mon']} in {res['throws']} throw(s)", flush=True)
            time.sleep(args.settle)
            continue

        for dx, dy in OFFSETS:
            x, y = AVATAR[0] + dx, AVATAR[1] + dy
            B.tap(x, y)
            time.sleep(args.settle)
            st = L.state()
            if st == "encounter":
                data = L.mon()
                print(f"  hit at ({x},{y}) -> L{data.get('level')} "
                      f"IV{data.get('iv')} {data.get('split')} "
                      f"consistent={data.get('consistent')}", flush=True)
                res = L.catch()
                throws += res.get("throws", 0)
                if res.get("caught"):
                    got += 1
                    print(f"  CAUGHT in {res['throws']} throw(s)", flush=True)
                time.sleep(args.settle)
                break
            if st == "raid":
                print("  R5: raid opened by probe -> closing")
                L.leave_raid()
                time.sleep(args.settle)
                break
            if st != "map":
                B.back()
                time.sleep(args.settle)
                break

    print(json.dumps({"caught": got, "throws": throws}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
