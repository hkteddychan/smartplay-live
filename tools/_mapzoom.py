"""Zoom the map in/out and capture, binary-safe.

Usage: python tools/_mapzoom.py [in|out] [n]
"""
import io
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

SERIAL = "1bbd5689"
TMP = Path(r"C:\Users\Teddy\AppData\Local\Temp")


def sh(*a):
    return subprocess.run(["adb", "-s", SERIAL, "shell", *a], capture_output=True)


def grab():
    r = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"],
                       capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def double_tap(x, y):
    sh("input", "tap", str(x), str(y))
    time.sleep(0.06)
    sh("input", "tap", str(x), str(y))
    time.sleep(0.9)


def pinch(zoom_in: bool, x=540, y=1100, span=260, steps=8):
    """Two-finger pinch via motionevent is not supported; use swipe-based zoom
    only if the client supports it. Kept for completeness."""
    pass


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "in"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    for _ in range(n):
        double_tap(540, 1100)
    time.sleep(2.0)
    img = grab()
    img.save(TMP / "zoom_map.png")
    img.convert("RGB").resize((540, 1080)).save(TMP / "zoom_map_small.png")
    print("saved", img.size, "mode", mode, "n", n)


if __name__ == "__main__":
    main()
