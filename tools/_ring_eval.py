"""Ground-ring test: PokéStops stand inside a pale ellipse, wild spawns do not.

    python tools/_ring_eval.py tools/pgo_sessions/probe/s4.png

For each scan candidate we search a small family of ellipses centred slightly
below the candidate and report the best fraction of sample points that land on
a pale (high-luminance, low-saturation) pixel.  A real stop scores high; a
Pokémon sprite scores low because the ground under it is dark asphalt/grass.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import pgo_layer as L

ANGLES = 72


def pale_mask(img: Image.Image) -> np.ndarray:
    a = np.asarray(img, dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    return (mx > 150) & ((mx - mn) < 55)


def ring_score(mask: np.ndarray, x: int, y: int) -> float:
    h, w = mask.shape
    best = 0.0
    for dy in (-10, 10, 30, 50, 70):
        for rx in (50, 70, 90, 110, 130, 150):
            ry = rx * 0.42
            cy = y + dy
            if cy + ry >= h or cy - ry < 0:
                continue
            hit = 0
            for i in range(ANGLES):
                t = 2 * math.pi * i / ANGLES
                px = int(x + rx * math.cos(t))
                py = int(cy + ry * math.sin(t))
                if 0 <= px < w and 0 <= py < h and mask[py, px]:
                    hit += 1
            best = max(best, hit / ANGLES)
    return best


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/s4.png")
    res = L.scan()
    img = Image.open(p).convert("RGB")
    mask = pale_mask(img)
    d = ImageDraw.Draw(img)
    print(f"objects={len(res['objects'])}")
    for o in res["objects"]:
        s = ring_score(mask, o["x"], o["y"])
        col = (0, 255, 0) if s >= 0.45 else (255, 140, 0)
        d.ellipse([o["x"] - 34, o["y"] - 34, o["x"] + 34, o["y"] + 34], outline=col, width=4)
        d.text((o["x"] - 30, o["y"] - 52), f"{s:.2f} {o['kind'][:5]}", fill=col)
        print(f"  ring={s:.2f}  {o['kind']:<10} {o['x']:>4} {o['y']:>4} "
              f"o={o['orange']:.2f} v={o['violet']:.2f}")
    out = p.with_name(p.stem + "_ring_eval.png")
    img.save(out)
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
