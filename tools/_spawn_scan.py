"""Variance spawn detection restricted to the avatar's interaction radius.

    python tools/_spawn_scan.py tools/pgo_sessions/probe/p9.png

Rationale: a wild spawn only renders at full size close to the player, while
gyms, Rocket balloons and HUD icons are either far away or pinned to the screen
edge.  Restricting to a radius around the avatar removes almost all of the false
positives the unconstrained variance scan produced.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from pgo_vision import candidates

AVATAR = (540, 1450)
R_IN, R_OUT = 90, 470
ORANGE_MAX = 0.25


def orange_ratio(img: Image.Image, x: int, y: int, r: int = 45) -> float:
    a = np.asarray(img.crop((max(0, x - r), max(0, y - r),
                             min(img.width, x + r), min(img.height, y + r))), dtype=np.int16)
    px = a.reshape(-1, 3)
    R, G, B = px[:, 0], px[:, 1], px[:, 2]
    return float(((R > 150) & (R - B > 90) & (G > 60) & (G < 200)).mean())


def detect(img: Image.Image, top: int = 8):
    out = []
    for v, x, y in candidates(img, 26):
        d = ((x - AVATAR[0]) ** 2 + (y - AVATAR[1]) ** 2) ** 0.5
        if not (R_IN < d < R_OUT):
            continue
        if orange_ratio(img, x, y) > ORANGE_MAX:
            continue
        out.append((v, x, y, d))
    out.sort(key=lambda t: -t[0])
    return out[:top]


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/p9.png")
    img = Image.open(p).convert("RGB")
    hits = detect(img)
    d = ImageDraw.Draw(img)
    print(f"{p.name}: spawn candidates={len(hits)}")
    for v, x, y, dist in hits:
        d.ellipse([x - 42, y - 42, x + 42, y + 42], outline=(0, 200, 255), width=4)
        d.text((x - 40, y - 60), f"{v:.0f}", fill=(0, 200, 255))
        print(f"  spawn {x:>4} {y:>4} var={v:>5.0f} dist={dist:>3.0f}")
    out = p.with_name(p.stem + "_spawn.png")
    img.save(out)
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
