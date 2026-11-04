import sys

sys.path.insert(0, "tools")
import numpy as np
from PIL import Image

from pgo_vision import grab_raw

im = grab_raw()
a = np.asarray(im.convert("RGB"), dtype=np.int16)
r, g, b = a[..., 0], a[..., 1], a[..., 2]

# PGSharp star: saturated yellow/orange, top-right quadrant
reg = np.zeros(a.shape[:2], bool)
reg[0:400, 800:1080] = True
star = reg & (r > 210) & (g > 140) & (g < 215) & (b < 110)
ys, xs = np.nonzero(star)
print("star px:", len(xs))
if len(xs):
    # cluster by simple grid
    from collections import Counter
    c = Counter((int(x) // 20 * 20, int(y) // 20 * 20) for x, y in zip(xs, ys))
    for (cx, cy), n in c.most_common(6):
        print(f"  cluster near ({cx + 10},{cy + 10}) n={n}")
    print(f"  bbox x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}]")

im.crop((820, 40, 1080, 320)).resize((520, 560)).save(
    r"C:\Users\Teddy\AppData\Local\Temp\starbox.png")
print("saved starbox.png")
