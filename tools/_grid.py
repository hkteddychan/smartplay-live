"""Draw a labelled coordinate grid on a screenshot so reads are unambiguous.

    python tools/_grid.py tools/pgo_sessions/probe/pick3.png

Grid lines every 100 device pixels with the actual coordinate printed, so the
position of a sprite can be read straight off the picture without any mental
scaling (the preview shown to a human is downscaled, the labels are not).
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

STEP = 100


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/pick3.png")
    out = src.with_name(src.stem + "_grid.png")
    img = Image.open(src).convert("RGB")
    d = ImageDraw.Draw(img)
    for x in range(0, img.width, STEP):
        d.line([(x, 0), (x, img.height)], fill=(255, 0, 255), width=1)
        d.text((x + 3, 6), str(x), fill=(255, 255, 0))
        d.text((x + 3, img.height - 20), str(x), fill=(255, 255, 0))
    for y in range(0, img.height, STEP):
        d.line([(0, y), (img.width, y)], fill=(255, 0, 255), width=1)
        d.text((4, y + 2), str(y), fill=(255, 255, 0))
        d.text((img.width - 60, y + 2), str(y), fill=(255, 255, 0))
    img.save(out)
    print(f"{src} -> {out}  ({img.width}x{img.height}, grid {STEP}px)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
