"""Ring-based object detection: find the pale ellipse under every spawn/stop.

    python tools/_ring_scan.py tools/pgo_sessions/probe/p9.png

Every world object (wild spawn AND PokéStop) stands inside a thin pale ellipse.
Locating the ellipse gives the object's centre; the colour *inside* the ring then
classifies it (orange = PokéStop available, violet = spun, other = wild spawn).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))

SCALE = 0.5
W_OUT, H_OUT = 200, 84      # ellipse outer size in full-res pixels
THICK = 14


def ring_template(scale: float) -> np.ndarray:
    """Synthetic pale-ellipse annulus, white on black, at the given scale."""
    w, h = int(W_OUT * scale), int(H_OUT * scale)
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = (w - 1) / 2, (h - 1) / 2
    rx, ry = cx, cy
    r = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    thr = 1.0 - THICK / min(rx, ry) * 0.5
    t = np.zeros((h, w), dtype=np.float64)
    t[(r <= 1.0) & (r >= thr)] = 1.0
    return t - t.mean()


def ncc_map(gray: np.ndarray, tpl: np.ndarray, stride: int = 2):
    """Normalised cross-correlation of a zero-mean template, strided."""
    th, tw = tpl.shape
    H, W = gray.shape
    tn = np.sqrt((tpl ** 2).sum())
    out = []
    for y in range(0, H - th, stride):
        for x in range(0, W - tw, stride):
            win = gray[y:y + th, x:x + tw]
            wc = win - win.mean()
            denom = np.sqrt((wc ** 2).sum()) * tn
            if denom <= 1e-6:
                continue
            out.append((float((wc * tpl).sum() / denom), x + tw // 2, y + th // 2))
    out.sort(reverse=True)
    return out


def detect(path: Path, top: int = 14, min_score=0.30):
    img = Image.open(path).convert("RGB")
    W, H = img.size
    small = img.resize((int(W * SCALE), int(H * SCALE)), Image.BILINEAR)
    a = np.asarray(small, dtype=np.float64)
    gray = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    tpl = ring_template(SCALE)
    raw = ncc_map(gray, tpl, stride=2)

    # keep peaks well separated, inside the play area
    kept = []
    for score, x, y in raw:
        if score < min_score:
            break
        fx, fy = x / SCALE, y / SCALE
        if fy < 220 or fy > 1900 or fx < 150 or fx > 900:
            continue
        if any((fx - kx) ** 2 + (fy - ky) ** 2 < 150 ** 2 for _, kx, ky in kept):
            continue
        kept.append((score, fx, fy))
        if len(kept) >= top:
            break
    return img, kept


def classify(img: Image.Image, fx: float, fy: float) -> str:
    r = 46
    box = img.crop((int(fx - r), int(fy - r), int(fx + r), int(fy + r)))
    a = np.asarray(box, dtype=np.int16).reshape(-1, 3)
    R, G, B = a[:, 0], a[:, 1], a[:, 2]
    orange = float(((R > 150) & (R - B > 90) & (G > 60) & (G < 200)).mean())
    violet = float(((B > 110) & (B - R > 45) & (B - G > 10)).mean())
    if orange > 0.12:
        return "stop_free"
    if violet > 0.12:
        return "stop_spun"
    return "spawn"


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/p9.png")
    img, kept = detect(p)
    d = ImageDraw.Draw(img)
    print(f"{p.name}: rings={len(kept)}")
    for score, x, y in kept:
        kind = classify(img, x, y)
        col = {"spawn": (0, 200, 255), "stop_free": (0, 255, 0),
               "stop_spun": (255, 0, 255)}[kind]
        d.rectangle([x - 55, y - 32, x + 55, y + 32], outline=col, width=4)
        d.text((x - 50, y - 52), f"{kind[:9]} {score:.2f}", fill=col)
        print(f"  {kind:<10} {int(x):>4} {int(y):>4} score={score:.2f}")
    out = p.with_name(p.stem + "_ring.png")
    img.save(out)
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
