"""Measure the game's real frame rate WITHOUT taking a screenshot.

    python tools/_fps.py            # ~2 s of frame timestamps, prints fps

Why not screenshots
-------------------
Every `takeScreenshot` / `screencap` makes SurfaceFlinger read the composited
buffer back through the GPU.  On this device (Adreno 630, MIUI) a burst of
captures starves the app's buffer queue:

    OpenGLRenderer: dequeueBuffer failed, error = -110; switching to fallback

After that the process renders in software at a few frames per second, its
main thread stops draining MotionEvents, InputDispatcher waits 5 s, and Android
puts up an 「沒有回應」 dialog which then eats every later tap.  That is the
"Unity input is dead" loop.

SurfaceFlinger already records present timestamps for every layer, so the frame
rate can be read from `dumpsys SurfaceFlinger --latency` for free: no pixels,
no GPU readback, no interference.
"""
from __future__ import annotations

import statistics
import subprocess
import sys

SERIAL = "1bbd5689"
PKG = "com.nianticlabs.pokemongo"


def sh(cmd: str) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True)
    return r.stdout or ""


def layer_name() -> str | None:
    out = sh("dumpsys SurfaceFlinger --list")
    cands = [ln.strip() for ln in out.splitlines()
             if "SurfaceView[" in ln and PKG in ln and "(BLAST)" in ln]
    if not cands:
        cands = [ln.strip() for ln in out.splitlines()
                 if "SurfaceView[" in ln and PKG in ln]
    return cands[0] if cands else None


def frames(name: str) -> list[float]:
    """Present timestamps (seconds) of the most recent frames."""
    out = sh(f'dumpsys SurfaceFlinger --latency "{name}"')
    rows = []
    for ln in out.splitlines()[1:]:
        p = ln.split()
        if len(p) != 3:
            continue
        try:
            actual = int(p[1])
        except ValueError:
            continue
        if actual in (0, 9223372036854775807):
            continue
        rows.append(actual / 1e9)
    rows.sort()
    return rows


def main() -> int:
    name = layer_name()
    if not name:
        print("no SurfaceView layer for the game")
        return 1
    ts = frames(name)
    if len(ts) < 5:
        print(f"{name}: only {len(ts)} frames recorded")
        return 2
    gaps = [(b - a) * 1000 for a, b in zip(ts, ts[1:])]
    gaps = [g for g in gaps if g > 0]
    fps = 1000 / statistics.median(gaps) if gaps else 0
    print(f"layer   : {name}")
    print(f"frames  : {len(ts)}")
    print(f"median  : {statistics.median(gaps):.1f} ms  ({fps:.1f} fps)")
    print(f"worst   : {max(gaps):.1f} ms")
    print(f"last gap: {gaps[-1]:.1f} ms" if gaps else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
