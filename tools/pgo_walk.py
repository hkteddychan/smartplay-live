"""Walk the avatar toward a point on screen — program-level reach extension.

    python tools/pgo_walk.py --to 480 1095          # walk toward that screen point
    python tools/pgo_walk.py --north 40             # walk 40 m north
    python tools/pgo_walk.py --toward-stop          # walk to the nearest detected stop

Why this exists
---------------
PGSharp's 「擴大遭遇範圍」 widens the client-side catch radius.  We cannot set it
from code (the switch ignores ACTION_CLICK and injected taps), and it is a
client hack anyway.  The legitimate program-level equivalent is to *walk*: the
avatar is moved with the virtual joystick, which is pure data-layer input, and
the catch radius is then satisfied by distance actually covered.

Scale is measured, not assumed: 4.1 px/m (33.3 m of walking moved the world
136 px).  Direction is derived from the joystick knob, whose screen position is
cached by `pgo_layer.joystick()`.

No teleport, no sniping — that is explicitly out of bounds (使用者明令).
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_direct as D
import pgo_layer as L

PX_PER_M = 4.1          # measured 2026-11-02
AVATAR = (535, 1315)    # measured while standing still on the bare map
KNOB_DX = 190           # drag distance that selects full speed
MPS = 30.0 / 3.6        # 30.0 km/h from the settings panel


def _knob() -> tuple[int, int]:
    k = L.joystick()
    if not k:
        raise RuntimeError("joystick position unknown (tool_verify/joystick.json)")
    return k


def walk(dx_m: float, dy_m: float, settle: float = 1.5) -> dict:
    """Walk dx_m east / dy_m south (screen axes) at full speed."""
    kx, ky = _knob()
    dist = math.hypot(dx_m, dy_m)
    if dist < 0.5:
        return {"moved_m": 0.0, "ms": 0}
    ux, uy = dx_m / dist, dy_m / dist
    ms = int(dist / MPS * 1000)
    ex, ey = kx + ux * KNOB_DX, ky + uy * KNOB_DX
    t0 = time.time()
    B.swipe(kx, ky, ex, ey, ms)
    time.sleep(settle)
    return {"moved_m": round(dist, 1), "ms": int((time.time() - t0) * 1000),
            "drag_ms": ms}


def walk_to_screen(x: int, y: int, max_m: float = 80.0,
                   avatar: tuple[int, int] = AVATAR) -> dict:
    """Walk so that the screen point (x, y) comes within catch range.

    Screen distance is converted to metres with the measured scale, then the
    joystick is held just long enough to cover it (minus a 25 m stop distance,
    which is comfortably inside the catch radius).
    """
    dx_px, dy_px = x - avatar[0], y - avatar[1]
    dx_m, dy_m = dx_px / PX_PER_M, dy_px / PX_PER_M
    dist_m = math.hypot(dx_m, dy_m)
    target = dist_m - 25.0
    if target <= 0:
        return {"walked_m": 0.0, "needed_m": round(dist_m, 1), "in_range": True}
    target = min(target, max_m)
    scale = target / dist_m if dist_m else 0
    out = walk(dx_m * scale, dy_m * scale)
    out.update({"needed_m": round(dist_m, 1), "in_range": False})
    return out


def position() -> dict:
    D.back_to_map()
    p = L.position()
    D.back_to_map()
    return p


def metres_between(a: dict, b: dict) -> float | None:
    if not (a.get("lat") and b.get("lat")):
        return None
    dlat = (b["lat"] - a["lat"]) * 111320.0
    dlon = (b["lon"] - a["lon"]) * 111320.0 * math.cos(math.radians(a["lat"]))
    return round(math.hypot(dlat, dlon), 1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", nargs=2, type=int, metavar=("X", "Y"))
    ap.add_argument("--north", type=float)
    ap.add_argument("--toward-stop", action="store_true")
    args = ap.parse_args()

    if not L.ensure_driver():
        print("driver unavailable")
        return 1
    D.back_to_map()

    before = position()
    if args.north:
        out = walk(0.0, -args.north)
    elif args.toward_stop:
        res = L.scan()
        stops = [o for o in res["objects"] if o["kind"].startswith("stop")]
        if not stops:
            print("no stop detected")
            return 1
        s = min(stops, key=lambda o: (o["x"] - AVATAR[0]) ** 2 + (o["y"] - AVATAR[1]) ** 2)
        print(f"nearest stop at screen ({s['x']},{s['y']})")
        out = walk_to_screen(s["x"], s["y"])
    elif args.to:
        out = walk_to_screen(args.to[0], args.to[1])
    else:
        print(__doc__)
        return 2

    after = position()
    out["measured_m"] = metres_between(before, after)
    out["from"] = (before.get("lat"), before.get("lon"))
    out["to"] = (after.get("lat"), after.get("lon"))
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
