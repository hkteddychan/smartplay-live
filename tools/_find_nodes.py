"""Dump every node whose text/desc contains a string, with class and bounds.

    python tools/_find_nodes.py 擴大遭遇範圍
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_layer as L


def main() -> int:
    want = sys.argv[1] if len(sys.argv) > 1 else "擴大遭遇範圍"
    ns = L.nodes()
    hits = [n for n in ns if want in (n["text"] or "") or want in (n["desc"] or "")]
    print(f"{len(hits)} match(es) for {want!r} in {len(ns)} nodes")
    for n in hits:
        print(f"  {n['cls']:<14} text={n['text']!r:<18} desc={n['desc']!r:<12} "
              f"flags={n['flags']:<5} box=({n['l']},{n['t']},{n['r']},{n['b']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
