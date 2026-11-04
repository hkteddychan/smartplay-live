import sys
sys.path.insert(0, "tools")
import numpy as np
from PIL import Image
from pgo_throw import best_match

T = r"C:\Users\Teddy\AppData\Local\Temp"

# avatar / bottom-left trainer button, present only on the map screen
Image.open(T + r"\m1.png").crop((30, 1790, 210, 2030)).save(T + r"\tpl_avatar.png")
Image.open(T + r"\nb1.png").crop((30, 1790, 210, 2030)).save(T + r"\tpl_avatar2.png")


def sc(tpl, img, region=None, scale=0.5):
    ti = Image.open(T + "\\" + tpl).convert("L")
    im = Image.open(T + "\\" + img).convert("L")
    small = np.asarray(im.resize((int(im.width * scale), int(im.height * scale))), dtype=np.float64)
    t = np.asarray(ti.resize((max(8, int(ti.width * scale)), max(8, int(ti.height * scale))), Image.BILINEAR), dtype=np.float64)
    if region:
        rx, ry, rw, rh = region
        sx, sy = int(rx * scale), int(ry * scale)
        s, x, y, w, h = best_match(small[sy:sy + int(rh * scale), sx:sx + int(rw * scale)], t, (1.0,))
    else:
        s, x, y, w, h = best_match(small, t, (1.0,))
    return round(s, 3)


for img in ["now.png", "m1.png", "r1.png", "nb1.png", "zoom_map.png", "menu.png", "map0.png"]:
    a1 = sc("tpl_avatar.png", img, (0, 1750, 300, 410))
    a2 = sc("tpl_avatar2.png", img, (0, 1750, 300, 410))
    print(f"{img:14s} avatar_m1={a1:6} avatar_nb1={a2:6}")
