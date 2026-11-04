"""Annotate a screenshot with the scan detections, for visual verification.

    python tools/_scan_annotate.py tools/pgo_sessions/probe/p9.png
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
from _scan_eval import scan


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/p9.png")
    stops, spawns = scan(p)
    img = Image.open(p).convert("RGB")
    d = ImageDraw.Draw(img)
    for x, y, st in stops:
        col = (0, 255, 0) if st == "free" else (255, 0, 255)
        d.rectangle([x - 40, y - 55, x + 40, y + 55], outline=col, width=4)
        d.text((x - 38, y - 80), f"{st}", fill=col)
    for v, x, y in spawns:
        d.ellipse([x - 45, y - 45, x + 45, y + 45], outline=(0, 200, 255), width=4)
        d.text((x - 40, y - 66), str(v), fill=(0, 200, 255))
    out = p.with_name(p.stem + "_scan.png")
    img.save(out)
    print(f"stops={len(stops)} spawns={len(spawns)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
