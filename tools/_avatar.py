"""Locate the avatar on screen by its bright-red cap.

    python tools/_avatar.py tools/pgo_sessions/probe/look.png
    python tools/_avatar.py --all

The camera pans, so the avatar is NOT at a fixed screen position (observed at
(535,1315) in one frame and (150,1790) in another).  Every sweep that assumed a
constant wasted its taps.  The red cap is small, saturated and unlike anything
else on the map (stop markers are orange, Rocket grunts are dark red), so it is
a cheap and stable anchor.

Returns the cap centre; the feet — the point the game actually uses for
distance — sit about 55 px below it at this camera angle.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

MIN_AREA = 60          # cap is roughly 30x20 px at 1080 wide
FEET_OFFSET = 55       # cap centre -> ground position


def cap_mask(a: np.ndarray) -> np.ndarray:
    r, g, b = a[..., 0].astype(np.int16), a[..., 1].astype(np.int16), a[..., 2].astype(np.int16)
    return (r > 135) & (g < 95) & (b < 95) & (r - g > 60) & (r - b > 55)


def find_avatar(img: Image.Image) -> tuple[int, int, int] | None:
    """(cap_x, cap_y, area) of the largest red blob in the play area."""
    a = np.asarray(img.convert("RGB"))
    m = cap_mask(a)
    h, w = m.shape
    m[: h // 12, :] = False           # status bar
    m[h - h // 8:, :] = False         # bottom UI, ball, trainer portrait
    m[:, : w // 4] = False            # left sidebar + portrait column
    m[:, w - w // 8:] = False         # right edge buttons
    lbl, n = ndimage.label(m)
    best = None
    for i, sl in enumerate(ndimage.find_objects(lbl), start=1):
        if sl is None:
            continue
        area = int((lbl[sl] == i).sum())
        if area < MIN_AREA:
            continue
        bh = sl[0].stop - sl[0].start
        bw = sl[1].stop - sl[1].start
        if bw > 90 or bh > 70:        # too big to be a cap
            continue
        cy = (sl[0].start + sl[0].stop) // 2
        cx = (sl[1].start + sl[1].stop) // 2
        if best is None or area > best[2]:
            best = (cx, cy, area)
    return best


def main() -> int:
    if "--all" in sys.argv:
        paths = sorted(Path("tools/pgo_sessions/probe").glob("*.png"))
        paths = [p for p in paths if not p.stem.endswith(("_grid", "_scan", "_check",
                                                          "_glow", "_ring", "_spawn",
                                                          "_final", "_eval"))]
    elif len(sys.argv) > 1:
        paths = [Path(sys.argv[1])]
    else:
        print(__doc__)
        return 2

    for p in paths:
        img = Image.open(p).convert("RGB")
        got = find_avatar(img)
        if not got:
            print(f"{p.name:<16} no cap found")
            continue
        cx, cy, area = got
        print(f"{p.name:<16} cap=({cx},{cy}) area={area} feet=({cx},{cy + FEET_OFFSET})")
        d = ImageDraw.Draw(img)
        d.rectangle([cx - 22, cy - 16, cx + 22, cy + 16], outline=(0, 255, 0), width=3)
        d.ellipse([cx - 8, cy + FEET_OFFSET - 8, cx + 8, cy + FEET_OFFSET + 8],
                  outline=(0, 255, 0), width=3)
        out = p.with_name(p.stem + "_av.png")
        img.save(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
