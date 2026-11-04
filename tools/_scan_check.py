"""Draw a layer `scan` result onto a screenshot for visual verification.

    python tools/_scan_check.py tools/pgo_sessions/probe/s2.png

Green = PokéStop available, magenta = PokéStop already spun, cyan = wild spawn.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).parent))
import pgo_layer as L

COLORS = {"spawn": (0, 200, 255), "stop_free": (0, 255, 0), "stop_spun": (255, 0, 255)}


def main() -> int:
    p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/pgo_sessions/probe/s2.png")
    res = L.scan()
    print(f"scan ok={res['ok']} ms={res['ms']} objects={len(res['objects'])}")
    img = Image.open(p).convert("RGB")
    d = ImageDraw.Draw(img)
    for o in res["objects"]:
        col = COLORS[o["kind"]]
        d.ellipse([o["x"] - 42, o["y"] - 42, o["x"] + 42, o["y"] + 42], outline=col, width=4)
        d.text((o["x"] - 40, o["y"] - 60),
               f"{o['kind'][:9]} {o['orange']:.2f}/{o['violet']:.2f}", fill=col)
        print(f"  {o['kind']:<10} {o['x']:>4} {o['y']:>4} var={o['var']:>6} "
              f"o={o['orange']:.2f} v={o['violet']:.2f}")
    out = p.with_name(p.stem + "_check.png")
    img.save(out)
    print("->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
