import sys

sys.path.insert(0, "tools")
import numpy as np
from PIL import Image, ImageDraw

from pgo_throw import ncc_map

T = r"C:\Users\Teddy\AppData\Local\Temp"


def white_mask(rgb, v_min, s_max):
    a = rgb.astype(np.float32)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    s = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1.0), 0.0)
    return ((mx >= v_min) & (s <= s_max)).astype(np.float64)


def ring_kernel(r, thickness):
    n = 2 * r + 1
    yy, xx = np.mgrid[0:n, 0:n]
    d = np.sqrt((xx - r) ** 2 + (yy - r) ** 2)
    return np.exp(-((d - r) ** 2) / (2 * thickness ** 2))


def detect(img, radii, thr, v_min, s_max, thickness, scale=0.5, nms=55):
    small = img.resize((int(img.width * scale), int(img.height * scale)))
    mask = white_mask(np.asarray(small.convert("RGB")), v_min, s_max)
    best = np.full(mask.shape, -1.0)
    for r in radii:
        k = ring_kernel(r, thickness)
        m = ncc_map(mask, k)
        pad = np.full(mask.shape, -1.0)
        pad[r:r + m.shape[0], r:r + m.shape[1]] = m
        best = np.maximum(best, pad)
    pts = []
    work = best.copy()
    while True:
        idx = int(np.argmax(work))
        y, x = divmod(idx, work.shape[1])
        s = float(work[y, x])
        if s < thr:
            break
        pts.append((s, int(x / scale), int(y / scale)))
        work[max(0, y - nms):y + nms, max(0, x - nms):x + nms] = -1
    return pts


if __name__ == "__main__":
    img = Image.open(T + "\\nb1.png").convert("RGB")
    radii = (30, 36, 42, 48, 56, 64, 74, 86)
    for v_min, s_max, th, thick in [
        (200, 0.18, 0.30, 2.5),
        (180, 0.25, 0.25, 2.0),
        (160, 0.35, 0.22, 1.6),
        (150, 0.45, 0.20, 1.5),
        (140, 0.55, 0.18, 1.2),
    ]:
        pts = detect(img, radii, th, v_min, s_max, thick)
        print(f"v>={v_min} s<={s_max} thr={th} th={thick} -> {len(pts)} pts; "
              f"top5={[round(p[0], 2) for p in pts[:5]]}")
        if v_min == 160:
            dbg = img.copy()
            d = ImageDraw.Draw(dbg)
            for s, x, y in pts:
                d.ellipse([x - 14, y - 14, x + 14, y + 14], outline=(0, 255, 0), width=3)
            dbg.resize((540, 1080)).save(T + "\\ring_dbg.png")
            print("  saved ring_dbg.png")
