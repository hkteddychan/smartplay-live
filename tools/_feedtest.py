import subprocess
import sys
import time

sys.path.insert(0, "tools")
from pgo_vision import grab_raw
import numpy as np
from PIL import Image

S = "1bbd5689"


def sh(c):
    return subprocess.run(["adb", "-s", S, "shell", c], capture_output=True, text=True).stdout


def red_bottom(img):
    a = np.asarray(img.crop((250, 1750, 850, 2160)), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 140) & (g < 90) & (b < 95)).sum())


def white_ratio(img):
    g = np.asarray(img.crop((40, 900, 1040, 1900)).convert("L"), dtype=np.uint8)
    return float((g > 215).mean())


def drive(cmd):
    sh(f"rm -f /sdcard/Android/data/com.opencode.pgodrive/files/out.txt")
    sh(f"printf '%s' '{cmd}' > /sdcard/Android/data/com.opencode.pgodrive/files/cmd.txt")
    t0 = time.time()
    while time.time() - t0 < 20:
        out = sh("cat /sdcard/Android/data/com.opencode.pgodrive/files/out.txt 2>/dev/null")
        if out and out.strip():
            return out.strip()
        time.sleep(0.05)
    return "TIMEOUT"


entries = [1048, 1161, 1274, 1387, 1500, 1613, 1747]
for y in entries:
    r = drive(f"click 58 {y}")
    time.sleep(4.0)
    img = grab_raw()
    rb, wr = red_bottom(img), white_ratio(img)
    st = "ENCOUNTER" if rb > 30000 else ("WHITE" if wr > 0.55 else "map")
    print(f"entry y={y}: {r[:30]} -> {st} red={rb} white={wr:.2f}")
    if st == "ENCOUNTER":
        img.resize((540, 1080)).save(r"C:\Users\Teddy\AppData\Local\Temp\feed_enc.png")
        print("  -> saved encounter screenshot")
        break
