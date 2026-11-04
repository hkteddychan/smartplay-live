"""Offline check of pgo_run's pick_target scoring on a stored frame.

    python tools/_pick_eval.py tools/pgo_sessions/probe/map8.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import pgo_run as R
from pgo_vision import candidates

AVATAR = R.AVATAR


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/map8.png")
    img = Image.open(path).convert("RGB")
    rows = []
    for v, x, y in candidates(img, 24):
        d = ((x - AVATAR[0]) ** 2 + (y - AVATAR[1]) ** 2) ** 0.5
        skip = []
        if not (R.AVATAR_CLEAR < d < 780):
            skip.append("dist")
        if y < 600:
            skip.append("too-high")
        if 900 < x < 1060 and y > 1700:
            skip.append("right-col")
        if x < 130 and 400 < y < 1300:
            skip.append("feed-col")
        o = R.orange_ratio(img, x, y)
        if o > R.ORANGE_MAX:
            skip.append(f"orange{o:.2f}")
        score = v - 0.5 * d
        rows.append((score, x, y, v, d, o, skip))
    rows.sort(reverse=True)
    print(f"{'score':>7} {'x':>5} {'y':>5} {'var':>6} {'dist':>5} {'orange':>6}  verdict")
    for score, x, y, v, d, o, skip in rows[:14]:
        print(f"{score:>7.0f} {x:>5} {y:>5} {v:>6.0f} {d:>5.0f} {o:>6.2f}  "
              f"{'PICK' if not skip else ','.join(skip)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
