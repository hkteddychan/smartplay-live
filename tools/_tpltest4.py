import numpy as np
from PIL import Image

T = r"C:\Users\Teddy\AppData\Local\Temp"


def feats(p):
    im = Image.open(T + "\\" + p).convert("RGB")
    a = np.asarray(im.crop((250, 1750, 850, 2160)), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    bottom = int(((r > 140) & (g < 90) & (b < 95)).sum())
    w = np.asarray(im.crop((40, 900, 1040, 1900)).convert("L"), dtype=np.uint8)
    return bottom, float((w > 215).mean())


for p in ["now.png", "m1.png", "r1.png", "nb1.png", "zoom_map.png", "menu.png", "map0.png",
          "th_0.png", "th_1.png", "th_2.png", "th_3.png", "fa.png", "fb.png", "fc.png"]:
    bt, wh = feats(p)
    print(f"{p:14s} bottom_red={bt:7d} white={wh:.3f}")
