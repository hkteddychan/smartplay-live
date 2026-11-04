"""Offline tuning of the map spawn picker (no device access).

    python tools/_target_tune.py tools/pgo_sessions/probe/map2.png

Prints every variance candidate together with its colour make-up, so we can
tell Pokémon (blue / white / dark) from the Halloween props (orange pumpkins,
orange PokéStop towers, orange leaves).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from pgo_vision import candidates

AVATAR = (540, 1500)


def colour_profile(img: Image.Image, x: int, y: int, r: int = 55):
    a = np.asarray(img.crop((max(0, x - r), max(0, y - r),
                             min(img.width, x + r), min(img.height, y + r))), dtype=np.int16)
    px = a.reshape(-1, 3)
    R, G, B = px[:, 0], px[:, 1], px[:, 2]
    orange = ((R > 150) & (R - B > 90) & (G > 60) & (G < 200)).mean()
    blue = ((B > 120) & (B - R > 25)).mean()
    white = ((R > 200) & (G > 200) & (B > 200)).mean()
    dark = ((R < 90) & (G < 90) & (B < 90)).mean()
    return {"orange": round(float(orange), 3), "blue": round(float(blue), 3),
            "white": round(float(white), 3), "dark": round(float(dark), 3)}


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/map2.png")
    img = Image.open(path).convert("RGB")
    print(f"{path}  size={img.size}")
    print(f"{'x':>5} {'y':>5} {'var':>7} {'dist':>5} {'orange':>7} {'blue':>6} {'white':>6} {'dark':>6}")
    for v, x, y in candidates(img, 24):
        d = int(((x - AVATAR[0]) ** 2 + (y - AVATAR[1]) ** 2) ** 0.5)
        c = colour_profile(img, x, y)
        print(f"{x:>5} {y:>5} {v:>7.0f} {d:>5} {c['orange']:>7} {c['blue']:>6} "
              f"{c['white']:>6} {c['dark']:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
