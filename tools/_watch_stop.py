"""Watch the data layer for *transient* native texts while something happens.

    python tools/_watch_stop.py                 # walk north, watch for new texts
    python tools/_watch_stop.py --seconds 15

Purpose: discover whether any action (walking near a PokéStop, a spin, a catch)
produces a **native** node that the layer could key on.  Anything printed here
is a text that appeared after the baseline snapshot, so it is a signal the bot
could use without a screenshot.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_layer as L


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=12.0)
    ap.add_argument("--walk-ms", type=int, default=6000)
    ap.add_argument("--no-walk", action="store_true")
    args = ap.parse_args()

    print("baseline state:", L.state())
    base = set(L.texts())
    print(f"baseline texts: {len(base)}")

    walk = None
    if not args.no_walk:
        walk = subprocess.Popen(
            ["adb", "-s", B.SERIAL, "shell", "input", "swipe",
             "129", "1587", "129", "1487", str(args.walk_ms)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"walking north for {args.walk_ms} ms")

    t0 = time.time()
    seen = set()
    while time.time() - t0 < args.seconds:
        cur = set(L.texts())
        new = cur - base - seen
        for t in sorted(new):
            print(f"  t={time.time() - t0:5.1f}s  NEW: {t!r}   state={L.state()}")
            seen.add(t)
        time.sleep(0.25)

    if walk is not None:
        walk.wait()
    print(f"total new texts: {len(seen)}")
    print("final state:", L.state())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
