"""Measure how many screen pixels one metre of walking is worth.

    python tools/_calib_scale.py --seconds 4

The camera follows the avatar, so after walking the whole world shifts by the
walked distance times the map scale.  Phase correlation between the before and
after frame gives that shift in pixels; 30 km/h * seconds gives the metres.

Writes tools/verify/scale.json:  {"px_per_m": ..., "t": ...}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
import pgo_bot as B
import pgo_direct as D
import pgo_layer as L

OUT = Path("tools/verify/scale.json")
PROBE = Path("tools/pgo_sessions/probe")
SPEED_KMH = 30.0


def shot(name: str) -> Path:
    p = PROBE / f"{name}.png"
    p.parent.mkdir(parents=True, exist_ok=True)
    B.grab().save(p)
    return p


def gray(p: Path) -> np.ndarray:
    a = np.asarray(Image.open(p).convert("L"), dtype=np.float64)
    # Clean map area only: the left sidebar, joystick, top HUD and the bottom
    # bar are static PGSharp/system overlays and would dominate the correlation.
    return a[320:1250, 210:1010]


def shift_px(a: Path, b: Path) -> tuple[float, float]:
    """Phase correlation -> (dx, dy) translation from a to b."""
    A, Bm = gray(a), gray(b)
    A -= A.mean()
    Bm -= Bm.mean()
    win = np.outer(np.hanning(A.shape[0]), np.hanning(A.shape[1]))
    F = np.fft.rfft2(A * win) * np.conj(np.fft.rfft2(Bm * win))
    F /= np.abs(F) + 1e-9
    c = np.fft.irfft2(F, s=A.shape)
    iy, ix = np.unravel_index(np.argmax(c), c.shape)
    h, w = A.shape
    dy = iy - h if iy > h // 2 else iy
    dx = ix - w if ix > w // 2 else ix
    return float(dx), float(dy)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=4.0)
    args = ap.parse_args()

    if not L.ensure_driver():
        print("driver unavailable")
        return 1
    D.back_to_map()
    knob = L.joystick()
    if not knob:
        print("no joystick node — must be on the bare map")
        return 1
    kx, ky = knob
    print(f"joystick knob at {kx},{ky}")

    a = shot("calib_a")
    # Drag up = walk north.  Hold, then release.
    B.swipe(kx, ky, kx, ky - 120, int(args.seconds * 1000))
    time.sleep(1.2)
    b = shot("calib_b")

    dx, dy = shift_px(a, b)
    metres = SPEED_KMH / 3.6 * args.seconds
    px_per_m = (dx * dx + dy * dy) ** 0.5 / metres
    rec = {"px_per_m": round(px_per_m, 4), "dx": dx, "dy": dy,
           "seconds": args.seconds, "metres": round(metres, 1),
           "t": round(time.time(), 3)}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
