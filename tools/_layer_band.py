"""Print the layer tree in a given screen band, for inspection.

    python tools/_layer_band.py 700 1000
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pgo_layer as L


def main() -> int:
    y0 = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    y1 = int(sys.argv[2]) if len(sys.argv) > 2 else 2160
    ns = L.nodes()
    print(f"nodes={len(ns)} band={y0}..{y1}")
    for n in sorted(ns, key=lambda d: (d["t"], d["l"])):
        if y0 <= n["t"] <= y1:
            print("%-14s %-24s %d,%d,%d,%d flags=%s" % (
                n["cls"], n["text"][:24], n["l"], n["t"], n["r"], n["b"], n["flags"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
