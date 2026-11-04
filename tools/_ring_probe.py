"""Detect wild-spawn rings on the map (offline, full-resolution pixels).

    python tools/_ring_probe.py tools/pgo_sessions/probe/map2.png

Wild Pokémon in this client stand inside a thin pale ellipse ring.  PokéStop
base rings look similar, but their interior is orange, so the ring's *inside*
colour separates them.  Prints every ring and whether it passes the colour test.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def rings(img: Image.Image, min_w=140, max_w=380, min_h=45, max_h=120):
    a = np.asarray(img, dtype=np.int16)
    R, G, B = a[..., 0], a[..., 1], a[..., 2]
    m = (R > 215) & (G > 215) & (B > 215)
    m[:120, :] = False
    m[1900:, :] = False
    lbl, n = ndimage.label(m)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lbl), start=1):
        if sl is None:
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if not (min_w <= w <= max_w and min_h <= h <= max_h):
            continue
        comp = lbl[sl] == i
        area = int(comp.sum())
        bbox = w * h
        fill = area / bbox
        if fill > 0.45:            # solid blob, not a ring
            continue
        cy = (sl[0].start + sl[0].stop) // 2
        cx = (sl[1].start + sl[1].stop) // 2
        # colour inside the ring
        r = max(10, min(w, h) // 3)
        sub = a[max(0, cy - r):cy + r, max(0, cx - r):cx + r].reshape(-1, 3)
        if not len(sub):
            continue
        SR, SG, SB = sub[:, 0], sub[:, 1], sub[:, 2]
        orange = float(((SR > 150) & (SR - SB > 90) & (SG > 60) & (SG < 200)).mean())
        out.append({"cx": cx, "cy": cy, "w": w, "h": h, "area": area,
                    "fill": round(fill, 2), "orange": round(orange, 2)})
    out.sort(key=lambda d: d["cy"])
    return out


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/map2.png")
    img = Image.open(path).convert("RGB")
    print(f"{path}  {img.size}")
    print(f"{'x':>5} {'y':>5} {'w':>4} {'h':>4} {'area':>6} {'fill':>5} {'orange':>6}  spawn?")
    for r in rings(img):
        ok = r["orange"] < 0.25
        print(f"{r['cx']:>5} {r['cy']:>5} {r['w']:>4} {r['h']:>4} {r['area']:>6} "
              f"{r['fill']:>5} {r['orange']:>6}  {'YES' if ok else 'no (stop/prop)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
