import subprocess, io, sys, time
from pathlib import Path
from PIL import Image

SERIAL = "1bbd5689"
TMP = Path(r"C:\Users\Teddy\AppData\Local\Temp")


def sh(*a):
    subprocess.run(["adb", "-s", SERIAL, "shell", *a], capture_output=True)


def grab():
    r = subprocess.run(["adb", "-s", SERIAL, "exec-out", "screencap", "-p"], capture_output=True)
    return Image.open(io.BytesIO(r.stdout)).convert("RGB")


def double_tap(x, y):
    sh("input", "tap", str(x), str(y))
    time.sleep(0.08)
    sh("input", "tap", str(x), str(y))
    time.sleep(1.2)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    zoom_in = "--out" not in sys.argv
    for _ in range(n):
        double_tap(850, 1250)
    time.sleep(2)
    img = grab()
    img.save(TMP / "pgo_last.png")
    # central band at full resolution, split into two halves for inspection
    top = img.crop((0, 600, 1080, 1400))
    bot = img.crop((0, 1400, 1080, 2160))
    top.save(TMP / "band_top.png")
    bot.save(TMP / "band_bot.png")
    print("saved", img.size, "n=", n)


if __name__ == "__main__":
    main()
