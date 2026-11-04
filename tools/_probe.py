"""One-off gesture probe: capture before/after and quantify the change.

Usage:
    python tools/_probe.py joystick_up
    python tools/_probe.py rotate_left
    python tools/_probe.py tilt_up
    python tools/_probe.py custom x1 y1 x2 y2 ms
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

GESTURES = {
    "joystick_up": (150, 660, 150, 470, 3000),
    "joystick_right": (150, 660, 300, 660, 3000),
    "rotate_left": (820, 1100, 300, 1100, 500),
    "rotate_right": (300, 1100, 820, 1100, 500),
    "tilt_up": (540, 1400, 540, 700, 500),
    "tilt_down": (540, 700, 540, 1400, 500),
}


def swipe(a, b, c, d, ms):
    subprocess.run(["adb", "-s", SERIAL, "shell", "input", "swipe",
                    str(a), str(b), str(c), str(d), str(ms)], capture_output=True)


def main():
    name = sys.argv[1]
    if name == "custom":
        g = tuple(int(v) for v in sys.argv[2:6]) + (int(sys.argv[6]),)
    else:
        g = GESTURES[name]

    before = grab_raw()
    t0 = time.time()
    swipe(*g)
    dt = time.time() - t0
    time.sleep(1.2)
    after = grab_raw()

    a = np.asarray(before.convert("L"), dtype=np.int16)
    b = np.asarray(after.convert("L"), dtype=np.int16)
    diff = float(np.abs(a - b).mean())

    sheet = Image.new("RGB", (before.width // 2 * 2 + 12, before.height // 2), (30, 30, 30))
    sheet.paste(before.resize((before.width // 2, before.height // 2)), (0, 0))
    sheet.paste(after.resize((after.width // 2, after.height // 2)), (before.width // 2 + 12, 0))
    d = ImageDraw.Draw(sheet)
    d.text((8, 8), f"BEFORE  {name} {g}", fill=(255, 255, 0))
    d.text((before.width // 2 + 20, 8), f"AFTER   diff={diff:.1f}", fill=(255, 255, 0))
    out = TMP / f"probe_{name}.png"
    sheet.save(out)
    print(f"{name} {g} gesture={dt:.2f}s  mean_abs_diff={diff:.2f}")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
