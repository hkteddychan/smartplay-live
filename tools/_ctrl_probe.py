"""Ad-hoc control probe: run one primitive, measure the screen change.

    python tools/_ctrl_probe.py walk up 2500
    python tools/_ctrl_probe.py turn left 600
    python tools/_ctrl_probe.py tilt up 600
    python tools/_ctrl_probe.py click 540 1000
    python tools/_ctrl_probe.py throw
    python tools/_ctrl_probe.py double 540 1150
    python tools/_ctrl_probe.py state

Prints the mean absolute pixel delta plus the screen-state signature before and
after, and writes /tmp before/after PNGs under tools/pgo_sessions/probe/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B

OUT = Path("tools/pgo_sessions/probe")


def diff(a, b):
    x = np.asarray(a, dtype=np.int16)
    y = np.asarray(b, dtype=np.int16)
    return float(np.abs(x - y).mean())


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    cmd = sys.argv[1:] or ["state"]

    if cmd[0] == "state":
        img = B.grab()
        print(f"state={B.screen_state(img)} red_bottom={B.red_bottom(img)} "
              f"white={B.white_ratio(img):.3f}")
        return 0

    before = B.grab()
    before.save(OUT / "before.png")

    name = cmd[0]
    if name == "walk":
        act = B.walk(cmd[1] if len(cmd) > 1 else "up",
                     int(cmd[2]) if len(cmd) > 2 else 2500)
    elif name == "turn":
        act = B.turn(cmd[1] if len(cmd) > 1 else "left",
                     int(cmd[2]) if len(cmd) > 2 else 600)
    elif name == "tilt":
        act = B.tilt(cmd[1] if len(cmd) > 1 else "up",
                     int(cmd[2]) if len(cmd) > 2 else 600)
    elif name == "click":
        B.tap(int(cmd[1]), int(cmd[2]))
        act = {"type": "click", "x": int(cmd[1]), "y": int(cmd[2])}
    elif name == "double":
        B.double_tap(int(cmd[1]), int(cmd[2]))
        act = {"type": "double", "x": int(cmd[1]), "y": int(cmd[2])}
    elif name == "zoom_in":
        act = B.zoom_in()
    elif name == "zoom_out":
        act = B.zoom_out()
    elif name == "throw":
        act = B.throw_ball()
    else:
        print(f"unknown probe {name}")
        return 2

    after = B.grab()
    after.save(OUT / "after.png")
    print(f"action={act}")
    print(f"state {B.screen_state(before)} -> {B.screen_state(after)}")
    print(f"red_bottom {B.red_bottom(before)} -> {B.red_bottom(after)}")
    print(f"white {B.white_ratio(before):.3f} -> {B.white_ratio(after):.3f}")
    print(f"mean_abs_delta={diff(before, after):.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
