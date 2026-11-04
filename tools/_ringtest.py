"""Prototype: detect the white clickable rings on the PGO map.

Rings mark every interactable object (wild spawns, PokéStops, gyms), so this
gives a small candidate list instead of a blind 36-point grid sweep.
"""
import sys

sys.path.insert(0, "tools")
import numpy as np
from PIL import Image, ImageDraw

from pgo_throw import ncc_map

T = r"C:\Users\Teddy\AppData\Local\Temp"


def white_mask(rgb: np.ndarray, v_min=200, s_max=0.18) -> np.ndarray:
    a = rgb.astype(np.float32)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)
    return ((mx >= v_min) & (s <= s_max)).astype(np.float64)


def ring_kernel(r: int, thickness: float = 2.5) -> np.ndarray:
    n = 2 * r + 1
    yy, xx = np.mgrid[0:n, 0:n]
    d = np.sqrt((xx - r) ** 2 + (yy - r) ** 2)
    k = np.exp(-((d - r) ** 2) / (2 * thickness ** 2))
    return k


def detect(img: Image.Image, radii=(38, 46, 54, 64, 76, 90, 105),
           thr=0.30, nms=60):
    scale = 0.5
    small = img.resize((int(img.width * scale), int(img.height * scale)))
    mask = white_mask(np.asarray(small.convert("RGB")))
    best = np.full(mask.shape, -1.0)
    for r in radii:
        k = ring_kernel(r)
        m = ncc_map(mask, k)
        pad = np.full(mask.shape, -1.0)
        pad[r:r + m.shape[0], r:r + m.shape[1]] = m
        best = np.maximum(best, pad)

    # simple NMS
    pts = []
    work = best.copy()
    while True:
        idx = int(np.argmax(work))
        y, x = divmod(idx, work.shape[1])
        s = float(work[y, x])
        if s < thr:
            break
        pts.append((s, x, y))
        y0, y1 = max(0, y - nms), min(work.shape[0], y + nms)
        x0, x1 = max(0, x - nms), min(work.shape[1], x + nms)
        work[y0:y1, x0:x1] = -1
    return [(s, int(x / scale), int(y / scale)) for s, x, y in pts]


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "nb1.png"
    img = Image.open(T + "\\" + name).convert("RGB")
    pts = detect(img)
    print(f"{name}: {len(pts)} candidates")
    d = ImageDraw.Draw(img)
    for s, x, y in pts:
        d.ellipse([x - 18, y - 18, x + 18, y + 18], outline=(0, 255, 0), width=4)
        d.text((x + 20, y - 8), f"{s:.2f}", fill=(0, 255, 0))
        print(f"  {s:.3f}  ({x},{y})")
    img.resize((540, 1080)).save(T + "\\ring_" + name)
    print("saved", T + "\\ring_" + name)
