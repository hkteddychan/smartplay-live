"""Read PGSharp's nearby-Pokémon bar (the left-edge sprite column).

    python tools/_bar.py tools/pgo_sessions/play/map_again.png

Why this is the right way to target a spawn
-------------------------------------------
The bar is drawn by PGSharp's own overlay service (`:pgp`), not by Unity.  A tap
on one of its icons is handled by PGSharp and opens that spawn's encounter
directly, so targeting never depends on guessing a sprite's pixel position on
the Unity surface — and it never queues a MotionEvent into the game's input
channel, which is what used to wedge the device.

Geometry (measured on this device, 1080x2160)
---------------------------------------------
The panel occupies x ≈ 0..110 and starts under the status bar.  Icons are
stacked with a ~105 px pitch, each about 60x70 px.  The panel is a translucent
dark scrim, so the map behind it is dimmed: icons are the only *bright*,
*saturated* blobs in the strip, which is what the detector keys on.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

X0, X1 = 16, 112          # the icon column (the scrim's right edge is ~110)
Y_TOP, Y_BOT = 130, 900   # below the top HUD, above the compass
SAT_MIN = 0.50
VAL_MIN = 0.55            # icons are drawn at full brightness over the scrim
AREA_MIN, AREA_MAX = 700, 7000
W_MIN, W_MAX = 30, 100
H_MIN, H_MAX = 30, 100
BAR_X = 64


def find_icons(img: Image.Image) -> list[tuple[int, int, int]]:
    """[(x, y, height)] of the bar icons, top to bottom."""
    a = np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0
    strip = a[Y_TOP:Y_BOT, X0:X1]
    mx = strip.max(axis=2)
    mn = strip.min(axis=2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    mask = (sat > SAT_MIN) & (mx > VAL_MIN)
    # close small holes (eyes, highlights) so one sprite is one component
    mask = ndimage.binary_closing(mask, np.ones((5, 5)))
    lbl, _ = ndimage.label(mask)
    out: list[tuple[int, int, int]] = []
    for i, sl in enumerate(ndimage.find_objects(lbl), start=1):
        if sl is None:
            continue
        comp = lbl[sl] == i
        area = int(comp.sum())
        if not (AREA_MIN <= area <= AREA_MAX):
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if not (H_MIN <= h <= H_MAX and W_MIN <= w <= W_MAX):
            continue
        ys, xs = np.nonzero(comp)
        cy = Y_TOP + sl[0].start + int(ys.mean())
        out.append((BAR_X, cy, h))
    out.sort(key=lambda t: t[1])
    # merge neighbours closer than half a pitch
    merged: list[tuple[int, int, int]] = []
    for x, y, h in out:
        if merged and y - merged[-1][1] < 55:
            if h > merged[-1][2]:
                merged[-1] = (x, y, h)
        else:
            merged.append((x, y, h))
    return merged


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "tools/pgo_sessions/play/map_again.png")
    img = Image.open(p).convert("RGB")
    icons = find_icons(img)
    d = ImageDraw.Draw(img)
    for i, (x, y, h) in enumerate(icons, 1):
        d.rectangle([x - 34, y - h // 2 - 4, x + 34, y + h // 2 + 4],
                    outline=(0, 255, 0), width=3)
        d.text((x + 38, y - 8), str(i), fill=(0, 255, 0))
    out = p.with_name(p.stem + "_bar.png")
    img.save(out)
    print(f"{p.name}: icons={len(icons)}")
    for i, (x, y, h) in enumerate(icons, 1):
        print(f"  {i}: ({x},{y}) h={h}")
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
