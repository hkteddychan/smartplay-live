import numpy as np
from PIL import Image

T = r"C:\Users\Teddy\AppData\Local\Temp"


def feats(im):
    s = im.width / 1080.0
    a = np.asarray(im.convert("RGB"), dtype=np.int16)

    def band(y0, y1, x0, x1):
        return a[int(y0 * s):int(y1 * s), int(x0 * s):int(x1 * s)]

    b = band(1740, 1900, 60, 1020)
    r, g, bl = b[..., 0], b[..., 1], b[..., 2]
    cyan = int(((r < 130) & (g > 150) & (bl > 200)).sum())

    c = band(1950, 2100, 60, 1020)
    r2, g2, b2 = c[..., 0], c[..., 1], c[..., 2]
    grey = int(((np.abs(r2 - g2) < 14) & (np.abs(g2 - b2) < 14) & (r2 > 190) & (r2 < 248)).sum())
    return cyan, grey, s


for p in ["stuck.png", "r1.png", "menu.png", "m1.png", "now.png"]:
    im = Image.open(T + "\\" + p)
    cy, gr, s = feats(im)
    print(f"{p:12s} scale={s:.2f} cyan={cy:7d} grey={gr:7d}")
