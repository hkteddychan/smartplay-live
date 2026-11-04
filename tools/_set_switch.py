"""Set one PGSharp settings switch, verifying it actually changed.

    python tools/_set_switch.py 快速捕捉 On
    python tools/_set_switch.py 擴大遭遇範圍 On

Why this exists: `layer.toggle()` presses ACTION_CLICK on the checkable node
found from the row label, which works for most rows but silently does nothing
for a few (observed on 擴大遭遇範圍).  This helper therefore verifies the
result and falls back to an injected tap on the switch centre, then to a tap on
the row itself.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_layer as L


def find_switch(label: str):
    """(cx, cy, checked) of the Switch whose row is `label`."""
    ns = L.nodes()
    labels = [n for n in ns if n["cls"] == "TextView"
              and n["text"] and n["l"] < 70]
    best = None
    for s in (n for n in ns if n["cls"] == "Switch"):
        cy = (s["t"] + s["b"]) // 2
        near = [lb for lb in labels if abs((lb["t"] + lb["b"]) // 2 - cy) <= 40]
        if not near:
            continue
        lb = min(near, key=lambda d: abs((d["t"] + d["b"]) // 2 - cy))
        if lb["text"] == label:
            best = ((s["l"] + s["r"]) // 2, cy, "X" in s["flags"])
    return best


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    label = sys.argv[1]
    want = (sys.argv[2].lower() in ("on", "1", "true")) if len(sys.argv) > 2 else True

    if L.state() != "settings":
        print(f"open 設置 first (state={L.state()})")
        return 1

    got = find_switch(label)
    if not got:
        print(f"row not visible: {label}")
        return 1
    cx, cy, checked = got
    print(f"{label}: switch at ({cx},{cy}) currently {'On' if checked else 'Off'}")
    if checked == want:
        print("already in the requested state")
        return 0

    # 1) semantic click on the checkable node
    print("try toggle ->", L.toggle(label))
    time.sleep(1.2)
    got = find_switch(label)
    if got and got[2] == want:
        print(f"OK {label} -> {'On' if want else 'Off'} (semantic click)")
        return 0

    # 2) injected tap on the switch itself
    print("try switch tap ->", L.drive(f"click {cx} {cy}"))
    time.sleep(1.2)
    got = find_switch(label)
    if got and got[2] == want:
        print(f"OK {label} -> {'On' if want else 'Off'} (switch tap)")
        return 0

    # 3) injected tap on the row label
    print("try row tap ->", L.drive(f"click {max(120, cx - 500)} {cy}"))
    time.sleep(1.2)
    got = find_switch(label)
    if got and got[2] == want:
        print(f"OK {label} -> {'On' if want else 'Off'} (row tap)")
        return 0

    got = find_switch(label)
    print(f"FAILED {label} still {'On' if got and got[2] else 'Off'}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
