"""Scan candidate joystick points: drag each and measure scene change.

    python tools/_walk_scan.py            # default candidate list
    python tools/_walk_scan.py 135 1385   # explicit point

A real walk scrolls the whole map (large delta + big joystick-adjacent change);
a miss barely changes anything.  Writes before/after PNGs per candidate.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import pgo_bot as B

OUT = Path("tools/pgo_sessions/scan")


def delta(a, b):
    return float(np.abs(np.asarray(a, dtype=np.int16) - np.asarray(b, dtype=np.int16)).mean())


def try_point(x, y, dist=200, ms=1800, tag=""):
    B.goto_map()
    before = B.grab()
    B.swipe(x, y, x, y - dist, ms)
    time.sleep(0.6)
    after = B.grab()
    d = delta(before, after)
    OUT.mkdir(parents=True, exist_ok=True)
    before.save(OUT / f"{x}_{y}_before.png")
    after.save(OUT / f"{x}_{y}_after.png")
    print(f"joy=({x},{y}) {tag} delta={d:.2f} state={B.screen_state(after)}", flush=True)
    return d


def main() -> int:
    if len(sys.argv) >= 3:
        cands = [(int(sys.argv[1]), int(sys.argv[2]))]
    else:
        cands = [(135, 1385), (140, 1400), (150, 660), (73, 636), (135, 1300)]
    for x, y in cands:
        try_point(x, y)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
