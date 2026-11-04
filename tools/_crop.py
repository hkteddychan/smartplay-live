"""Crop regions of a screenshot for close inspection.

    python tools/_crop.py tools/pgo_sessions/probe/s4.png 700 1250 950 1500 out
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image


def main() -> int:
    p = Path(sys.argv[1])
    x0, y0, x1, y1 = (int(v) for v in sys.argv[2:6])
    name = sys.argv[6] if len(sys.argv) > 6 else "crop"
    img = Image.open(p).convert("RGB")
    box = img.crop((x0, y0, x1, y1))
    box = box.resize((box.width * 3, box.height * 3), Image.LANCZOS)
    out = p.with_name(f"{p.stem}_{name}.png")
    box.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
