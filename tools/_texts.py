"""List every text-bearing node of the current screen (the data-layer surface).

    python tools/_texts.py            # all texts, deduped, with bounds
    python tools/_texts.py --only     # just the strings, one per line
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pgo_layer as L


def main() -> int:
    only = "--only" in sys.argv
    ns = L.nodes()
    print(f"state={L.state(ns)} nodes={len(ns)}")
    seen = set()
    for n in sorted(ns, key=lambda d: (d["t"], d["l"])):
        for s in (n["text"], n["desc"]):
            if not s or s in seen:
                continue
            seen.add(s)
            if only:
                print(s)
            else:
                print("%-14s %-28s %d,%d,%d,%d" % (
                    n["cls"], s[:28], n["l"], n["t"], n["r"], n["b"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
