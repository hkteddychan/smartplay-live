"""Gesture practice on the map: rotate / tilt / zoom, all recorded as ML data.

The Mix2S build has no multi-touch pinch available over adb (SELinux blocks
/dev/input), so zoom is done the way the client itself supports it: double-tap.
Rotation and tilt are single-finger drags on the map body.

Usage:
    python tools/pgo_practice.py --rounds 12
    python tools/pgo_practice.py --rounds 12 --out tools/pgo_sessions/practice
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

from pgo_record import Session

SERIAL = "1bbd5689"


def adb(*args, binary=False):
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def grab() -> Image.Image:
    return Image.open(io.BytesIO(adb("exec-out", "screencap", "-p", binary=True))).convert("RGB")


def swipe(x1, y1, x2, y2, ms):
    adb("shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))


def double_tap(x, y):
    adb("shell", "input", "tap", str(x), str(y))
    time.sleep(0.07)
    adb("shell", "input", "tap", str(x), str(y))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--serial", default=SERIAL)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = args.out or Path("tools/pgo_sessions") / ("practice_" + time.strftime("%Y%m%d_%H%M%S"))
    root.mkdir(parents=True, exist_ok=True)
    sess = Session(root, {
        "serial": SERIAL, "policy": "manual_gesture_practice",
        "note": "rotate / tilt / zoom gestures on the map, recorded for imitation learning",
        "rounds": args.rounds,
    })
    print(f"[practice] session {root}", flush=True)

    # (name, action) — coordinates chosen to avoid the UI chrome
    gestures = [
        ("rotate_left",  {"type": "swipe", "x1": 820, "y1": 1150, "x2": 260, "y2": 1150, "ms": 420}),
        ("rotate_right", {"type": "swipe", "x1": 260, "y1": 1150, "x2": 820, "y2": 1150, "ms": 420}),
        ("tilt_up",      {"type": "swipe", "x1": 540, "y1": 1350, "x2": 540, "y2": 700,  "ms": 420}),
        ("tilt_down",    {"type": "swipe", "x1": 540, "y1": 700,  "x2": 540, "y2": 1350, "ms": 420}),
        ("zoom_in",      {"type": "tap", "x": 540, "y": 1150, "double": True}),
        ("pan_ne",       {"type": "swipe", "x1": 700, "y1": 1400, "x2": 400, "y2": 900,  "ms": 380}),
        ("pan_sw",       {"type": "swipe", "x1": 400, "y1": 900,  "x2": 700, "y2": 1400, "ms": 380}),
    ]

    for r in range(args.rounds):
        for name, a in gestures:
            img = grab()
            small = img.resize((img.width // 2, img.height // 2))
            sess.record(img, small, a, 1.0, name)
            if not args.dry_run:
                if a.get("double"):
                    double_tap(a["x"], a["y"])
                else:
                    swipe(a["x1"], a["y1"], a["x2"], a["y2"], a.get("ms", 400))
            time.sleep(0.8)
            print(f"[{r + 1}/{args.rounds}] {name}", flush=True)

    print(f"[practice] done -> {root}", flush=True)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    raise SystemExit(main())
