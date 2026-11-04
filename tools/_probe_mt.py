"""Probe multi-touch-ish gestures: two concurrent `input` pointers.

SELinux blocks /dev/input writes, so a true pinch is impossible. But two
`input` commands running concurrently create two independent injected
pointers, which the game may read as a two-finger gesture.

Usage:
    python tools/_probe_mt.py pinch_out
    python tools/_probe_mt.py pinch_in
    python tools/_probe_mt.py two_finger_tap
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image, ImageDraw

from pgo_vision import grab_raw

SERIAL = "1bbd5689"
TMP = Path(r"C:\Users\Teddy\AppData\Local\Temp")


def sh(*a):
    return subprocess.Popen(["adb", "-s", SERIAL, "shell", *a],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def both(p1, p2):
    a = sh(*p1)
    b = sh(*p2)
    a.wait()
    b.wait()


def main():
    name = sys.argv[1]
    before = grab_raw()

    if name == "pinch_out":       # zoom out: fingers move apart
        both(["input", "swipe", "450", "1100", "250", "1100", "400"],
             ["input", "swipe", "650", "1100", "850", "1100", "400"])
    elif name == "pinch_in":      # zoom in: fingers move together
        both(["input", "swipe", "300", "1100", "500", "1100", "400"],
             ["input", "swipe", "800", "1100", "600", "1100", "400"])
    elif name == "two_finger_tap":
        both(["input", "tap", "420", "1100"], ["input", "tap", "680", "1100"])
    else:
        raise SystemExit("unknown gesture")

    time.sleep(1.5)
    after = grab_raw()
    a = np.asarray(before.convert("L"), dtype=np.int16)
    b = np.asarray(after.convert("L"), dtype=np.int16)
    diff = float(np.abs(a - b).mean())

    sheet = Image.new("RGB", (before.width // 2 * 2 + 12, before.height // 2), (30, 30, 30))
    sheet.paste(before.resize((before.width // 2, before.height // 2)), (0, 0))
    sheet.paste(after.resize((after.width // 2, after.height // 2)), (before.width // 2 + 12, 0))
    d = ImageDraw.Draw(sheet)
    d.text((8, 8), f"BEFORE {name}", fill=(255, 255, 0))
    d.text((before.width // 2 + 20, 8), f"AFTER diff={diff:.1f}", fill=(255, 255, 0))
    out = TMP / f"mt_{name}.png"
    sheet.save(out)
    print(f"{name} diff={diff:.2f} -> {out}")


if __name__ == "__main__":
    main()
