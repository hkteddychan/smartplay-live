"""Tune a spawn-ring detector on stored frames (offline).

    python tools/_ring_probe2.py tools/pgo_sessions/probe/map8.png

Wild spawns stand inside a thin, bright, low-saturation ellipse.  We look for
hollow bright components of the right size, then rank by ellipse-likeness.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def hsv_mask(img, vmin=190, smax=0.40):
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx = a.max(2) / 255.0
    mn = a.min(2) / 255.0
    s = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    return (mx * 255 > vmin) & (s < smax)


def rings(img, wmin=140, wmax=420, hmin=45, hmax=150, fillmax=0.55):
    m = hsv_mask(img)
    m[:130, :] = False
    m[1850:, :] = False
    m[:, :130] = False          # left feed column
    m[:, 900:] = False          # right PGSharp column
    lbl, n = ndimage.label(m)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lbl), start=1):
        if sl is None:
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        if not (wmin <= w <= wmax and hmin <= h <= hmax):
            continue
        comp = lbl[sl] == i
        area = int(comp.sum())
        fill = area / (w * h)
        if fill > fillmax:
            continue
        # ring-ness: mass should sit near the bbox border
        ys, xs = np.nonzero(comp)
        cy, cx = (sl[0].start + sl[0].stop) / 2, (sl[1].start + sl[1].stop) / 2
        rr = ((xs - (cx - sl[1].start)) / (w / 2)) ** 2 + ((ys - (cy - sl[0].start)) / (h / 2)) ** 2
        on_ring = float(((rr > 0.55) & (rr < 1.9)).mean())
        out.append({"cx": int(cx), "cy": int(cy), "w": w, "h": h,
                    "area": area, "fill": round(fill, 2), "ring": round(on_ring, 2)})
    out.sort(key=lambda d: d["ring"], reverse=True)
    return out


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/map8.png")
    img = Image.open(path).convert("RGB")
    rs = rings(img)
    print(f"{path}  {img.size}  candidates={len(rs)}")
    print(f"{'x':>5} {'y':>5} {'w':>4} {'h':>4} {'area':>6} {'fill':>5} {'ring':>5}")
    for r in rs[:16]:
        print(f"{r['cx']:>5} {r['cy']:>5} {r['w']:>4} {r['h']:>4} {r['area']:>6} "
              f"{r['fill']:>5} {r['ring']:>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
