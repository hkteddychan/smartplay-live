"""Verify the double-click flow on the left floating bar.

    double-click feed entry   -> player moves onto that spawn
    double-click again        -> encounter starts

Both steps are done through the layer-level driver.
"""
import subprocess
import sys
import time

sys.path.insert(0, "tools")
import numpy as np

from pgo_vision import grab_raw

S = "1bbd5689"
BASE = "/sdcard/Android/data/com.opencode.pgodrive/files"


def sh(c):
    return subprocess.run(["adb", "-s", S, "shell", c], capture_output=True, text=True).stdout


def drive(cmd):
    sh(f"rm -f {BASE}/out.txt")
    sh(f"printf '%s' '{cmd}' > {BASE}/cmd.txt")
    t0 = time.time()
    while time.time() - t0 < 20:
        out = sh(f"cat {BASE}/out.txt 2>/dev/null")
        if out and out.strip():
            return out.strip()
        time.sleep(0.04)
    return "TIMEOUT"


def dbl(x, y, gap=0.10):
    drive(f"click {x} {y}")
    time.sleep(gap)
    drive(f"click {x} {y}")


def state(img):
    a = np.asarray(img.crop((250, 1750, 850, 2160)), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    rb = int(((r > 140) & (g < 90) & (b < 95)).sum())
    gr = np.asarray(img.crop((40, 900, 1040, 1900)).convert("L"), dtype=np.uint8)
    wr = float((gr > 215).mean())
    if rb > 30000:
        return "ENCOUNTER", rb, wr
    if wr > 0.55:
        return "WHITE", rb, wr
    return "map", rb, wr


entries = [1048, 1161, 1274, 1387, 1500, 1613]
for y in entries:
    dbl(58, y)
    time.sleep(3.5)
    img = grab_raw()
    st, rb, wr = state(img)
    print(f"dbl y={y}: after 1st -> {st} red={rb}", flush=True)
    if st == "ENCOUNTER":
        img.resize((540, 1080)).save(r"C:\Users\Teddy\AppData\Local\Temp\feed_dbl.png")
        print("  -> ENCOUNTER after single double-click")
        break
    # second double click, on the map body where the spawn should now be
    dbl(540, 1450)
    time.sleep(3.5)
    img = grab_raw()
    st, rb, wr = state(img)
    print(f"         after 2nd -> {st} red={rb} white={wr:.2f}", flush=True)
    if st == "ENCOUNTER":
        img.resize((540, 1080)).save(r"C:\Users\Teddy\AppData\Local\Temp\feed_dbl.png")
        print("  -> ENCOUNTER after two double-clicks")
        break
