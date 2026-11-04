"""Find wild-spawn sprites by saturated-colour blobs (event-map safe).

    python tools/_sprites.py tools/pgo_sessions/play/after_restart.png

The pale-cyan swirl detector misses this event's spawns: their ground swirls
are darker blue, and the detector's global cyan filter locks onto roads and
water instead.  Sprites themselves, however, are small and strongly
saturated, while the map is pale grey-blue and the big landmarks are either
huge (gyms, stops) or a known hue (orange power spots, magenta raid eggs).

So: threshold saturation, drop the landmark hue windows and the avatar, then
keep small compact blobs.  A debug PNG is written next to the input.
"""
from __future__ import annotations

import colorsys
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

SCALE = 2                  # work at half resolution
SAT_MIN = 0.42
VAL_MIN = 0.28
AREA_MIN = 30              # half-scale pixels
AREA_MAX = 3500
SIDE_MIN = 6
SIDE_MAX = 70
ASPECT_MIN = 0.35
ASPECT_MAX = 2.8


def _hue_mask(a: np.ndarray) -> np.ndarray:
    r = a[..., 0].astype(np.float32) / 255.0
    g = a[..., 1].astype(np.float32) / 255.0
    b = a[..., 2].astype(np.float32) / 255.0
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    delta = mx - mn
    sat = np.where(mx > 0, delta / np.maximum(mx, 1e-6), 0)
    val = mx
    hue = np.zeros_like(mx)
    nonzero = delta > 1e-6
    idx = nonzero & (mx == r)
    hue[idx] = (60 * ((g[idx] - b[idx]) / delta[idx]) + 360) % 360
    idx = nonzero & (mx == g) & ~((mx == r))
    hue[idx] = 60 * ((b[idx] - r[idx]) / delta[idx]) + 120
    idx = nonzero & (mx == b) & ~((mx == r) | (mx == g))
    hue[idx] = 60 * ((r[idx] - g[idx]) / delta[idx]) + 240
    return sat, val, hue


def find_sprites(img: Image.Image, feet: tuple[int, int] | None = None,
                 exclude_px: int = 95) -> list[tuple]:
    W, H = img.size
    small = img.resize((W // SCALE, H // SCALE), Image.BILINEAR)
    a = np.asarray(small.convert("RGB"))
    sat, val, hue = _hue_mask(a)
    h, w = sat.shape

    mask = (sat > SAT_MIN) & (val > VAL_MIN)
    # landmark hues: orange power spots, magenta raid eggs / gym badges,
    # red avatars / pokéball
    mask &= ~((hue >= 8) & (hue <= 48))
    mask &= ~((hue >= 285) & (hue <= 350))
    mask &= ~((hue <= 6) | (hue >= 352))

    # never look at HUD / sidebars
    mask[: int(h * 0.09), :] = False
    mask[int(h * 0.93):, :] = False
    mask[:, : int(w * 0.07)] = False
    mask[:, int(w * 0.93):] = False

    lbl, n = ndimage.label(mask)
    out = []
    fx = fy = None
    if feet:
        fx, fy = feet[0] / SCALE, feet[1] / SCALE
    for i, sl in enumerate(ndimage.find_objects(lbl), start=1):
        if sl is None:
            continue
        comp = lbl[sl] == i
        area = int(comp.sum())
        if area < AREA_MIN or area > AREA_MAX:
            continue
        bh = sl[0].stop - sl[0].start
        bw = sl[1].stop - sl[1].start
        if bw < SIDE_MIN or bh < SIDE_MIN or bw > SIDE_MAX or bh > SIDE_MAX:
            continue
        aspect = bw / max(1, bh)
        if aspect < ASPECT_MIN or aspect > ASPECT_MAX:
            continue
        ys, xs = np.nonzero(comp)
        cy = sl[0].start + ys.mean()
        cx = sl[1].start + xs.mean()
        # reject blobs inside the avatar's own footprint
        if fx is not None and (cx - fx) ** 2 + (cy - fy) ** 2 < (exclude_px / SCALE) ** 2:
            continue
        # sprite must be reasonably compact (not a thin road marking)
        fill = area / float(bw * bh)
        if fill < 0.18:
            continue
        out.append((int(cx * SCALE), int(cy * SCALE), area, fill))
    out.sort(key=lambda t: -t[2])
    return out


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
        "tools/pgo_sessions/play/after_restart.png")
    img = Image.open(p).convert("RGB")
    feet = None
    try:
        import _avatar as A
        got = A.find_avatar(img)
        if got:
            feet = (got[0], got[1] + A.FEET_OFFSET)
    except Exception:
        pass
    found = find_sprites(img, feet)
    d = ImageDraw.Draw(img)
    if feet:
        d.ellipse([feet[0] - 6, feet[1] - 6, feet[0] + 6, feet[1] + 6],
                  outline=(0, 255, 0), width=3)
    for x, y, area, fill in found:
        d.rectangle([x - 26, y - 30, x + 26, y + 30], outline=(255, 0, 255), width=3)
        d.text((x - 24, y - 46), f"{area}", fill=(255, 0, 255))
    out = p.with_name(p.stem + "_sprite.png")
    img.save(out)
    print(f"{p.name}: feet={feet} sprites={len(found)}")
    for x, y, area, fill in found:
        print(f"  {x:>4} {y:>4} area={area:>5} fill={fill:.2f}")
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
