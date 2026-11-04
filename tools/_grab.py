import subprocess, io, sys
from pathlib import Path
from PIL import Image

SERIAL = "1bbd5689"

def grab():
    r = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"], capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")

def tap(x, y):
    subprocess.run(["adb", "-s", SERIAL, "shell", "input", "tap", str(x), str(y)])

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Teddy\AppData\Local\Temp")
    img = grab()
    img.save(out / "pgo_last.png")
    print("size", img.size)
    # bottom-centre pokeball button
    img.crop((420, 1880, 660, 2120)).save(out / "tpl_map_ball.png")
    # full bottom strip for inspection
    img.crop((0, 1800, 1080, 2160)).resize((1080, 360)).save(out / "bottom_strip.png")
    print("saved crops")
