"""List every Switch in the settings panel with its label and checked state.

    python tools/_settings_switches.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_layer as L


def main() -> int:
    ns = L.nodes()
    labels = [n for n in ns if n["cls"] == "TextView" and n["text"] and n["l"] < 70]
    for s in (n for n in ns if n["cls"] == "Switch"):
        cy = (s["t"] + s["b"]) // 2
        near = [lb for lb in labels if abs((lb["t"] + lb["b"]) // 2 - cy) <= 40]
        name = near[0]["text"] if near else "?"
        print(f"y={cy:>5} checked={'X' in s['flags']!s:<5} "
              f"flags={s['flags']:<5} cx={(s['l']+s['r'])//2:>4} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
