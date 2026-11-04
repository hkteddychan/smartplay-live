import numpy as np
from PIL import Image

T = r"C:\Users\Teddy\AppData\Local\Temp"


def feats(p):
    im = Image.open(T + "\\" + p).convert("RGB")
    # menu pokeball at the bottom centre of the map screen
    a = np.asarray(im.crop((450, 1920, 620, 2090)), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mapball = int(((r > 140) & (g < 70) & (b < 70)).sum())
    # whole bottom band
    c = np.asarray(im.crop((250, 1750, 850, 2160)), dtype=np.int16)
    r2, g2, b2 = c[..., 0], c[..., 1], c[..., 2]
    bottom = int(((r2 > 140) & (g2 < 70) & (b2 < 70)).sum())
    w = np.asarray(im.crop((40, 900, 1040, 1900)).convert("L"), dtype=np.uint8)
    white = float((w > 215).mean())
    return mapball, bottom, white


for p in ["now.png", "m1.png", "r1.png", "nb1.png", "zoom_map.png", "menu.png", "map0.png"]:
    mb, bt, wh = feats(p)
    print(f"{p:14s} mapball={mb:6d} bottom_red={bt:7d} white={wh:.3f}")
