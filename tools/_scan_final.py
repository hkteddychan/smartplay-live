"""Unified object scan: locate by variance, classify by interior colour.

    python tools/_scan_final.py tools/pgo_sessions/probe/p9.png

Pipeline (same as the driver's `scan` after porting):
  1. variance peaks inside the avatar's interaction radius   -> candidates
  2. orange/violet ratio in a small box around each candidate -> object kind
         orange  -> PokéStop available (free)
         violet  -> PokéStop already spun
         neither -> wild spawn
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from pgo_vision import candidates

AVATAR = (540, 1450)
R_IN, R_OUT = 90, 480
STOP_ORANGE = 0.20
STOP_VIOLET = 0.18


def ratios(img: Image.Image, x: int, y: int, r: int = 45):
    """Max orange/violet ratio over the centre and four offsets.

    A variance peak on a tall PokéStop lands on its edge, so sampling only the
    centre misses the tower body; taking the max over offsets fixes that.
    """
    best_o = best_v = 0.0
    for dx, dy in ((0, 0), (0, -35), (0, 35), (-35, 0), (35, 0)):
        a = np.asarray(img.crop((max(0, x + dx - r), max(0, y + dy - r),
                                 min(img.width, x + dx + r),
                                 min(img.height, y + dy + r))), dtype=np.int16)
        px = a.reshape(-1, 3)
        R, G, B = px[:, 0], px[:, 1], px[:, 2]
        o = float(((R > 150) & (R - B > 90) & (G > 60) & (G < 200)).mean())
        v = float(((B > 110) & (B - R > 45) & (B - G > 10)).mean())
        best_o = max(best_o, o)
        best_v = max(best_v, v)
    return best_o, best_v


def scan(img: Image.Image, top: int = 10):
    out = []
    for v, x, y in candidates(img, 26):
        d = ((x - AVATAR[0]) ** 2 + (y - AVATAR[1]) ** 2) ** 0.5
        if not (R_IN < d < R_OUT):
            continue
        o, vi = ratios(img, x, y)
        if o >= STOP_ORANGE:
            kind = "stop_free"
        elif vi >= STOP_VIOLET:
            kind = "stop_spun"
        else:
            kind = "spawn"
        out.append({"v": v, "x": x, "y": y, "d": d, "orange": o, "violet": vi, "kind": kind})
    out.sort(key=lambda r: -r["v"])
    return out[:top]


COLORS = {"spawn": (0, 200, 255), "stop_free": (0, 255, 0), "stop_spun": (255, 0, 255)}


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/p9.png")
    img = Image.open(p).convert("RGB")
    hits = scan(img)
    d = ImageDraw.Draw(img)
    print(f"{p.name}: objects={len(hits)}")
    for h in hits:
        col = COLORS[h["kind"]]
        d.ellipse([h["x"] - 42, h["y"] - 42, h["x"] + 42, h["y"] + 42], outline=col, width=4)
        d.text((h["x"] - 40, h["y"] - 60), f"{h['kind'][:9]}", fill=col)
        print(f"  {h['kind']:<10} {h['x']:>4} {h['y']:>4} var={h['v']:>5.0f} "
              f"orange={h['orange']:.2f} violet={h['violet']:.2f}")
    out = p.with_name(p.stem + "_final.png")
    img.save(out)
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
