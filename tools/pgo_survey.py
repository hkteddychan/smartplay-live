"""Spatial observation ledger built from the data layer.

    python tools/pgo_survey.py --minutes 6

What it proves
--------------
Every record is produced without a screenshot for the *data* part:
  - position  : 傳送 panel lat/lng (TextView nodes)
  - encounter : berry row + L/IV/split (TextView nodes)
  - pokestop  : 快速旋轉 / speed / sniping flags (Switch nodes, cached snapshot)

A screenshot is used only to choose where to tap on the Unity map (the map
itself has no nodes), never to decide what we are looking at.

Records go to tools/verify/observations.jsonl:
  {"t":..., "lat":..., "lon":..., "kind":"position"|"encounter", "mon":{...}}
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

import pgo_bot as B
import pgo_direct as D
import pgo_layer as L
from pgo_vision import candidates

LEDGER = Path("tools/verify/observations.jsonl")
AVATAR = (540, 1500)
ORANGE_MAX = 0.25


def orange_ratio(img, x, y, r=55) -> float:
    a = np.asarray(img.crop((max(0, x - r), max(0, y - r),
                             min(img.width, x + r), min(img.height, y + r))), dtype=np.int16)
    px = a.reshape(-1, 3)
    R, G, Bd = px[:, 0], px[:, 1], px[:, 2]
    return float(((R > 150) & (R - Bd > 90) & (G > 60) & (G < 200)).mean())


def log(rec: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=6.0)
    ap.add_argument("--settle", type=float, default=3.0)
    args = ap.parse_args()

    stops = L.stop_status()
    print("stop_status:", json.dumps(stops, ensure_ascii=False), flush=True)
    if not stops.get("sniping_disabled"):
        print("ABORT: sniping toggles not verified off", flush=True)
        return 2

    end = time.time() + args.minutes * 60
    n_pos = n_enc = n_catch = n_walk = 0
    while time.time() < end:
        D.back_to_map()
        pos = L.position()
        n_pos += 1
        log({"t": round(time.time(), 3), "kind": "position", **pos,
             "auto_spin": stops.get("auto_spin"), "speed_kmh": stops.get("speed_kmh")})
        print(f"pos {pos.get('lat')},{pos.get('lon')} @ {pos.get('local')}", flush=True)

        st = L.state()
        if st == "encounter":
            mon = L.mon()
            n_enc += 1
            log({"t": round(time.time(), 3), "kind": "encounter",
                 "lat": pos.get("lat"), "lon": pos.get("lon"), "mon": mon})
            print("  encounter:", mon, flush=True)
            res = L.catch()
            if res.get("caught"):
                n_catch += 1
                log({"t": round(time.time(), 3), "kind": "catch",
                     "lat": pos.get("lat"), "lon": pos.get("lon"),
                     "mon": res.get("mon"), "throws": res.get("throws")})
                print("  CAUGHT", res.get("throws"), flush=True)
            continue

        # map: try a few filtered candidates, then walk on
        D.back_to_map()
        img = B.grab()
        pts = [(v, x, y) for v, x, y in candidates(img, 20)
               if 95 < ((x - AVATAR[0]) ** 2 + (y - AVATAR[1]) ** 2) ** 0.5 < 780
               and y > 600 and orange_ratio(img, x, y) <= ORANGE_MAX]
        pts.sort(key=lambda p: -(p[0] - 0.5 * ((p[1] - AVATAR[0]) ** 2
                                               + (p[2] - AVATAR[1]) ** 2) ** 0.5))
        hit = False
        for _, x, y in pts[:3]:
            if time.time() >= end:
                break
            B.tap(x, y)
            time.sleep(args.settle)
            if L.state() == "encounter":
                hit = True
                break
        if not hit:
            if L.state() != "map":
                D.back_to_map()
            joy = L.joystick()
            if joy is None:
                print("  ! joystick not found in layer, skipping walk", flush=True)
            else:
                B.swipe(joy[0], joy[1], joy[0], joy[1] - 190, 5000)
                n_walk += 1
                print(f"  walk via joystick {joy}", flush=True)
                time.sleep(1.2)

    print(json.dumps({"positions": n_pos, "encounters": n_enc,
                      "catches": n_catch, "walks": n_walk}), flush=True)
    print(f"ledger -> {LEDGER}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
