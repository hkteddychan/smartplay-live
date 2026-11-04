"""Throw the ball once, with rapid post-throw capture, binary-safe.

Usage:
    python tools/_throw_test.py            # straight drag, 540,1940 -> 540,950
    python tools/_throw_test.py curve      # curved drag via motionevent
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


def grab(name):
    r = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"],
                       capture_output=True)
    img = Image.open(io.BytesIO(r.stdout)).convert("RGB")
    img.save(TMP / name)
    return img


def straight():
    sh("input", "swipe", "540", "1940", "540", "950", "300")


def curve():
    """Arc: down on ball, drag up and slightly right, then up-left, release."""
    pts = [(540, 1940), (548, 1780), (562, 1620), (578, 1460),
           (592, 1300), (598, 1160), (596, 1040), (588, 950)]
    sh("input", "motionevent", "DOWN", str(pts[0][0]), str(pts[0][1]))
    for x, y in pts[1:]:
        time.sleep(0.03)
        sh("input", "motionevent", "MOVE", str(x), str(y))
    time.sleep(0.05)
    sh("input", "motionevent", "UP", str(pts[-1][0]), str(pts[-1][1]))


def sheet(names, out):
    ims = [Image.open(TMP / n).convert("RGB").resize((270, 540)) for n in names]
    s = Image.new("RGB", (270 * len(ims), 540))
    for i, im in enumerate(ims):
        s.paste(im, (270 * i, 0))
    s.save(TMP / out)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "straight"
    grab("th_before.png")
    t0 = time.time()
    curve() if mode == "curve" else straight()
    print(f"gesture {mode} took {time.time() - t0:.2f}s")

    names = []
    for i in range(4):
        time.sleep(0.45)
        n = f"th_{i}.png"
        grab(n)
        names.append(n)
        print("  captured", n, f"t+{time.time() - t0:.2f}s")
    sheet(["th_before.png"] + names, "th_sheet.png")
    print("sheet ->", TMP / "th_sheet.png")
