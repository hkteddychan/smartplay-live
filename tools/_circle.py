"""Find PGSharp's interaction-radius circle: the avatar's position and the scale.

    python tools/_circle.py tools/pgo_sessions/probe/s6.png

The client draws a thin translucent pink circle of radius ~40 m (the PokéStop /
catch interaction range) around the avatar.  Detecting it gives, in one shot:

  * the avatar's screen position (circle centre)
  * pixels-per-metre (circle radius / 40 m)

so the hunt loop can tell "visible" from "actually reachable" without any
hard-coded camera assumption.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

RADIUS_M = 40.0


def pink_mask(img: Image.Image) -> np.ndarray:
    a = np.asarray(img, dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return (r > 185) & (b > 140) & (r - g > 45) & (b - g > 10) & (g < 210)


def fit_circle(mask: np.ndarray) -> tuple[float, float, float] | None:
    """Centroid + mean radius of the pink ring (ignores the small event hearts)."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 500:
        return None
    cx, cy = xs.mean(), ys.mean()
    d = np.hypot(xs - cx, ys - cy)
    # the ring is the dominant radius; discard hearts/petals near the centre
    hist, edges = np.histogram(d, bins=60, range=(0, d.max() + 1))
    peak = int(np.argmax(hist[5:])) + 5
    r0 = (edges[peak] + edges[peak + 1]) / 2
    keep = np.abs(d - r0) < 25
    if keep.sum() < 200:
        return None
    cx, cy = xs[keep].mean(), ys[keep].mean()
    r = np.hypot(xs[keep] - cx, ys[keep] - cy).mean()
    return float(cx), float(cy), float(r)


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/s6.png")
    img = Image.open(p).convert("RGB")
    m = pink_mask(img)
    print(f"pink pixels: {int(m.sum())}")
    got = fit_circle(m)
    if not got:
        print("no circle found")
        return 1
    cx, cy, r = got
    ppm = r / RADIUS_M
    print(f"avatar=({cx:.0f},{cy:.0f}) radius={r:.0f}px -> {ppm:.2f} px/m")
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(0, 255, 0), width=3)
    d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline=(0, 255, 0), width=3)
    out = p.with_name(p.stem + "_circle.png")
    img.save(out)
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
