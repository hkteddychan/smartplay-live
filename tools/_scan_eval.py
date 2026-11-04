"""Offline port of the driver's `scan` algorithm, for validation without a device.

    python tools/_scan_eval.py tools/pgo_sessions/probe/p9.png

Mirrors Driver.scanMap() exactly (1/4-scale masks, connected components,
tile variance, NMS) so the numbers printed here are what the phone returns.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

T, STEP = 6, 3
VAR_MIN = 350.0
NMS = 34


def scan(path: Path):
    img = Image.open(path).convert("RGB")
    W, H = img.size
    small = img.resize((W // 4, H // 4), Image.BILINEAR)
    a = np.asarray(small, dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    orange = (r > 150) & (r - b > 90) & (g > 60) & (g < 200)
    violet = (b > 110) & (b - r > 45) & (b - g > 10)
    lum = 0.299 * r + 0.587 * g + 0.114 * b

    stops = []
    lbl, n = ndimage.label(orange | violet)
    for i, sl in enumerate(ndimage.find_objects(lbl), start=1):
        if sl is None:
            continue
        bh = sl[0].stop - sl[0].start
        bw = sl[1].stop - sl[1].start
        comp = lbl[sl] == i
        area = int(comp.sum())
        if area < 30 or bh < 8 or bh <= bw or bw < 5 or bw > 45:
            continue
        cy = (sl[0].start + sl[0].stop) // 2
        cx = (sl[1].start + sl[1].stop) // 2
        if cy < 40 or cy > 470:
            continue
        sub_o = int(orange[sl].sum())
        sub_v = int(violet[sl].sum())
        stops.append((cx * 4, cy * 4, "free" if sub_o >= sub_v else "spun"))

    h, w = lum.shape
    cand = []
    for ty in range(40, max(41, h - 40 - T), STEP):
        for tx in range(34, 224 - T, STEP):
            tile = lum[ty:ty + T, tx:tx + T]
            if orange[ty:ty + T, tx:tx + T].mean() > 0.25:
                continue
            v = float(tile.var())
            if v < VAR_MIN:
                continue
            cand.append((v, tx + T // 2, ty + T // 2))
    cand.sort(reverse=True)
    spawns = []
    for v, x, y in cand:
        if all((x - sx) ** 2 + (y - sy) ** 2 >= NMS * NMS for _, sx, sy in spawns):
            spawns.append((v, x, y))
        if len(spawns) >= 6:
            break
    return stops, [(int(v), x * 4, y * 4) for v, x, y in spawns]


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/p9.png")
    stops, spawns = scan(p)
    print(f"{p.name}: stops={len(stops)} spawns={len(spawns)}")
    for x, y, st in stops:
        print(f"  stop  {x:>4} {y:>4} {st}")
    for v, x, y in spawns:
        print(f"  spawn {x:>4} {y:>4} var={v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
