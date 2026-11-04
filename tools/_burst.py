"""Tap a point and capture a burst of frames, to see what a gesture opens.

    python tools/_burst.py 555 1235 3        # tap, 3 frames
    python tools/_burst.py 555 1235 3 dbl    # double tap first

Frames land in tools/pgo_sessions/burst/0.png, 1.png, ...
Each frame prints its screen signature so short-lived screens are visible even
if they are gone by the time the next grab starts.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pgo_bot as B

OUT = Path("tools/pgo_sessions/burst")


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    x, y = int(sys.argv[1]), int(sys.argv[2])
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    mode = sys.argv[4] if len(sys.argv) > 4 else "tap"

    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.png"):
        f.unlink()

    t0 = time.time()
    if mode == "dbl":
        B.double_tap(x, y)
    else:
        B.tap(x, y)

    for i in range(n):
        img = B.grab()
        img.save(OUT / f"{i}.png")
        print(f"[{i}] t={time.time() - t0:5.2f}s state={B.screen_state(img)} "
              f"red={B.red_bottom(img)} white={B.white_ratio(img):.3f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
