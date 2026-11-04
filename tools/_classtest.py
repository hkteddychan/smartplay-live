import sys
sys.path.insert(0, "tools")
from PIL import Image
import pgo_auto as A

T = r"C:\Users\Teddy\AppData\Local\Temp"
for p in ["now.png", "m1.png", "r1.png", "nb1.png", "zoom_map.png", "menu.png",
          "map0.png", "th_0.png", "fa.png", "fb.png", "fc.png"]:
    im = Image.open(T + "\\" + p).convert("RGB")
    print(f"{p:14s} {A.classify(im):10s} berry={A.berry_score(im):.3f} "
          f"red={A.red_bottom(im):6d} white={A.white_ratio(im):.3f}")
