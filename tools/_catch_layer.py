"""Catch the current encounter using ONLY the data layer for decisions.

    python tools/_catch_layer.py

No screenshots, no pixel classifier.  `pgo_layer.catch()` handles the loop:
- throws with the verified 120 ms flick, 精靈球 only (R1)
- decides "broke free" vs "resolved" with a debounced layer read
- dismisses the Unity reward card, which is the one screen with no nodes
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_layer as L
from pgo_rules import describe


def main() -> int:
    print(describe())
    print("state:", L.state())
    if L.state() != "encounter":
        print("not in an encounter")
        return 1
    print("layer mon:", json.dumps(L.mon(), ensure_ascii=False))
    res = L.catch()
    print("result:", json.dumps(res, ensure_ascii=False))
    return 0 if res["caught"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
