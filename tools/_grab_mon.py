"""Pick a wild spawn with ONE screenshot, then read it purely from the layer.

    python tools/_grab_mon.py            # choose + tap + read
    python tools/_grab_mon.py --no-tap   # only preview what would be chosen

The screenshot is used for one thing only: deciding *where* to tap.  Everything
about the Pokémon that follows (level, IV, IV-split, weather boost, berry row)
is read from the accessibility layer, and the result is cross-checked against
the internal IV invariant.
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
import pgo_layer as L
from pgo_vision import candidates

OUT = Path("tools/pgo_sessions/mon")
AVATAR = (540, 1500)          # avatar sits just below the screen centre
AVATAR_CLEAR = 150            # ignore candidates on the avatar sprite itself


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-tap", action="store_true")
    ap.add_argument("--max-dist", type=int, default=700)
    args = ap.parse_args()

    if L.state() == "raid":
        print("R5: raid sheet open -> closing, refusing to act")
        L.leave_raid()
        return 1

    img = B.grab()
    pts = candidates(img, 16)
    if not pts:
        print("no candidates on screen")
        return 1
    scored = []
    for v, x, y in pts:
        d = ((x - AVATAR[0]) ** 2 + (y - AVATAR[1]) ** 2) ** 0.5
        if AVATAR_CLEAR < d <= args.max_dist:
            scored.append((d, v, x, y))
    if not scored:
        print("no candidate near the avatar (outside the avatar sprite)")
        return 1
    scored.sort()
    d, v, x, y = scored[0]
    print(f"target ({x},{y}) dist={d:.0f} var={v:.0f}")

    if args.no_tap:
        return 0
    B.tap(x, y)
    time.sleep(7)

    st = L.state()
    print(f"layer state -> {st}")
    if st == "raid":
        print("R5: that tap opened a 團體戰 -> closing it, never joining")
        L.leave_raid()
        return 2
    if st != "encounter":
        print("no encounter opened")
        return 1

    data = L.mon()
    print("layer mon    ->", json.dumps(data, ensure_ascii=False))
    if data.get("consistent") is False:
        print(f"WARNING: IV {data['iv']} != expected {data.get('iv_expected')} from {data['split']}")
    elif data.get("consistent"):
        print(f"IV invariant OK: {data['split']} -> {data['iv_expected']}% == IV {data['iv']}")

    OUT.mkdir(parents=True, exist_ok=True)
    img2 = B.grab()
    img2.save(OUT / "encounter.png")
    (OUT / "mon.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"screenshot saved for cross-check -> {OUT / 'encounter.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
