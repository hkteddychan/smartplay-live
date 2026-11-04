"""Find wild-spawn tap points by their pale-cyan ground swirl.

    python tools/_glow_scan.py tools/pgo_sessions/probe/look.png

Every wild spawn stands inside a pale cyan swirl (concentric rings) that the
event skin draws on the ground.  PokéStops instead stand inside a white ring,
and roads/water are darker and less saturated.  Locating the swirl gives the
point the game actually hit-tests, which is what a tap must target.

This replaces the earlier variance-peak detector, which locked onto road
markings and event pumpkins instead of the sprites.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

BOX = 9           # half-size of the density window, in 1/4-scale pixels
MIN_DENS = 0.30   # fraction of cyan pixels needed inside the window


def cyan_density(img: Image.Image) -> tuple[np.ndarray, float]:
    """1/4-scale density map of pale-cyan pixels, plus the pixels-per-metre."""
    W, H = img.size
    s = img.resize((W // 4, H // 4), Image.BILINEAR)
    a = np.asarray(s, dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    mask = ((b > 130) & (g > 130) & (b - r > 12) & (g - r > 8) & (lum > 128))
    k = 2 * BOX + 1
    dens = ndimage.uniform_filter(mask.astype(np.float32), size=k)
    return dens, 4.0


def find_glows(img: Image.Image, top: int = 14):
    dens, scale = cyan_density(img)
    h, w = dens.shape
    peaks = dens > MIN_DENS
    peaks[: h // 8, :] = False          # top HUD
    peaks[h - h // 8:, :] = False       # bottom bar
    peaks[:, : w // 9] = False          # left sidebar
    lbl, n = ndimage.label(peaks)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lbl), start=1):
        if sl is None:
            continue
        comp = lbl[sl] == i
        area = int(comp.sum())
        if area < 25:
            continue
        ys, xs = np.nonzero(comp)
        cy = sl[0].start + ys.mean()
        cx = sl[1].start + xs.mean()
        peak = float(dens[sl][comp].max())
        out.append((peak, cx * scale, cy * scale, area * scale * scale))
    out.sort(reverse=True)

    kept = []
    for peak, x, y, area in out:
        if any((x - kx) ** 2 + (y - ky) ** 2 < 90 ** 2 for _, kx, ky, _ in kept):
            continue
        kept.append((peak, x, y, area))
        if len(kept) >= top:
            break
    return kept


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/look.png")
    img = Image.open(p).convert("RGB")
    kept = find_glows(img)
    d = ImageDraw.Draw(img)
    print(f"{p.name}: glows={len(kept)}")
    for peak, x, y, area in kept:
        d.ellipse([x - 46, y - 46, x + 46, y + 46], outline=(0, 255, 180), width=4)
        d.text((x - 40, y - 66), f"{peak:.2f}", fill=(0, 255, 180))
        print(f"  glow {int(x):>4} {int(y):>4} peak={peak:.2f} area={int(area)}")
    out = p.with_name(p.stem + "_glow.png")
    img.save(out)
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
