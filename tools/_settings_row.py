"""Show the settings rows around a label, so the switch layout is visible.

    python tools/_settings_row.py 擴大遭遇範圍
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_layer as L


def main() -> int:
    want = sys.argv[1] if len(sys.argv) > 1 else "擴大遭遇範圍"
    ns = L.nodes()
    for i, n in enumerate(ns):
        if want in (n["text"] or ""):
            print(f"--- rows around {want!r} ---")
            for m in ns[max(0, i - 3):i + 5]:
                print(f"{m['cls']:<14} text={m['text']!r:<18} "
                      f"flags={m['flags']:<4} box=({m['l']},{m['t']},{m['r']},{m['b']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
