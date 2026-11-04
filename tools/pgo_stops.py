"""Find PGSharp map objects (PokéStops) by colour, in true device pixels.

    python tools/pgo_stops.py                # detect + save an annotated frame
    python tools/pgo_stops.py --show 5       # also print the 5 nearest to avatar

PokéStops in this client are the tall orange flame-towers.  They are far more
saturated than the Halloween pumpkins lying on the ground, so a tight RGB
window plus a *height* filter separates the two.  Detection happens on the
full-resolution frame, so the returned coordinates can be tapped directly.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

sys.path.insert(0, str(Path(__file__).parent))
import pgo_bot as B

OUT = Path("tools/pgo_sessions/stops")


def mask_orange(img: Image.Image) -> np.ndarray:
    a = np.asarray(img, dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    # flame-tower orange: very bright red, mid green, low blue
    return (r > 190) & (g > 90) & (g < 185) & (b < 80) & (r - b > 140)


def detect(img: Image.Image, min_area=900, max_area=20000, min_h=45):
    m = mask_orange(img)
    # ignore the top status bar and the bottom UI bar
    m[:100, :] = False
    m[1850:, :] = False
    m[:, :120] = False          # left feed column
    m[:, 900:] = False          # right PGSharp column
    lbl, n = ndimage.label(m)
    out = []
    for sl in ndimage.find_objects(lbl):
        if sl is None:
            continue
        h = sl[0].stop - sl[0].start
        w = sl[1].stop - sl[1].start
        area = int((lbl[sl] > 0).sum())
        if not (min_area <= area <= max_area):
            continue
        if h < min_h or w < 20:
            continue
        if h < w:              # towers are tall; pumpkins are wide/flat
            continue
        cx = (sl[1].start + sl[1].stop) // 2
        cy = (sl[0].start + sl[0].stop) // 2
        out.append({"cx": cx, "cy": cy, "w": w, "h": h, "area": area})
    out.sort(key=lambda d: d["area"], reverse=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--show", type=int, default=0)
    ap.add_argument("--save", action="store_true")
    args = ap.parse_args()

    img = B.grab()
    stops = detect(img)
    OUT.mkdir(parents=True, exist_ok=True)
    avx, avy = 540, 1300     # avatar sits just below screen centre
    print(f"detected {len(stops)} tower candidates")
    for s in stops[:30]:
        s["dist"] = round(((s["cx"] - avx) ** 2 + (s["cy"] - avy) ** 2) ** 0.5)
        print(f"  ({s['cx']:4d},{s['cy']:4d}) w={s['w']:3d} h={s['h']:3d} "
              f"area={s['area']:5d} dist={s['dist']}")

    if args.save:
        ann = img.copy()
        d = ImageDraw.Draw(ann)
        for s in stops:
            d.rectangle([s["cx"] - s["w"] // 2, s["cy"] - s["h"] // 2,
                         s["cx"] + s["w"] // 2, s["cy"] + s["h"] // 2], outline=(0, 255, 0), width=4)
            d.text((s["cx"] - 20, s["cy"] - s["h"] // 2 - 24), f"{s['cx']},{s['cy']}",
                   fill=(0, 255, 0))
        ann.save(OUT / "annotated.png")
        print(f"-> {OUT / 'annotated.png'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
