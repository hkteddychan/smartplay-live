"""Vision-based ball thrower for the Mix2S test device.

Pipeline: adb screencap -> downscale -> multi-scale NCC template match -> tap
the best hit (dry-run by default, so you can calibrate before it touches anything).

Usage:
    # 1. calibrate: capture what you want tapped, crop it as a template
    python tools/pgo_throw.py --capture            # saves a full screenshot
    python tools/pgo_throw.py --crop X Y W H       # crop template out of the last capture

    # 2. detect only (no taps)
    python tools/pgo_throw.py --template tpl.png --dry-run

    # 3. actually throw
    python tools/pgo_throw.py --template tpl.png --serial 1bbd5689 --tap
"""
from __future__ import annotations

import argparse
import io
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

# ---------------------------------------------------------------- adb helpers

def adb(serial: str | None, *args: str, binary: bool = False):
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def grab(serial: str | None) -> Image.Image:
    """Binary-safe screenshot (never go through a shell redirection)."""
    data = adb(serial, "exec-out", "screencap", "-p", binary=True)
    return Image.open(io.BytesIO(data)).convert("RGB")


def tap(serial: str | None, x: int, y: int) -> None:
    adb(serial, "shell", "input", "tap", str(int(x)), str(int(y)))


def swipe(serial: str | None, x1: int, y1: int, x2: int, y2: int, ms: int = 220) -> None:
    adb(serial, "shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(ms))


# ------------------------------------------------------------------- matching

def _box_sums(a: np.ndarray, h: int, w: int) -> np.ndarray:
    """Sum of every h x w window of `a`, via integral image."""
    ii = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    ii[1:, 1:] = a.cumsum(0).cumsum(1)
    return (ii[h:, w:] - ii[:-h, w:] - ii[h:, :-w] + ii[:-h, :-w])


def ncc_map(img: np.ndarray, tmpl: np.ndarray) -> np.ndarray:
    """Normalised cross-correlation of `tmpl` over `img` (both float grayscale)."""
    h, w = tmpl.shape
    if img.shape[0] < h or img.shape[1] < w:
        return np.zeros((1, 1))

    t = tmpl - tmpl.mean()
    t_norm = np.sqrt((t * t).sum())
    if t_norm == 0:
        return np.zeros((img.shape[0] - h + 1, img.shape[1] - w + 1))

    fh, fw = h, w
    fft_h = 1
    while fft_h < img.shape[0] + h:
        fft_h *= 2
    fft_w = 1
    while fft_w < img.shape[1] + w:
        fft_w *= 2

    F_img = np.fft.rfft2(img, s=(fft_h, fft_w))
    F_t = np.fft.rfft2(t[::-1, ::-1], s=(fft_h, fft_w))
    cc = np.fft.irfft2(F_img * F_t, s=(fft_h, fft_w))[h - 1: img.shape[0], w - 1: img.shape[1]]

    s1 = _box_sums(img, h, w)
    s2 = _box_sums(img * img, h, w)
    n = float(h * w)
    var = np.maximum(s2 - (s1 * s1) / n, 1e-6)
    return (cc - (s1 / n) * t.mean()) / (np.sqrt(var) * t_norm)


def best_match(img_gray: np.ndarray, tmpl_gray: np.ndarray, scales=(1.0, 0.9, 1.1, 1.2)):
    """Best (score, x, y, w, h) over a set of template scales."""
    best = (-1.0, 0, 0, 0, 0)
    for s in scales:
        th = max(8, int(tmpl_gray.shape[0] * s))
        tw = max(8, int(tmpl_gray.shape[1] * s))
        if th >= img_gray.shape[0] or tw >= img_gray.shape[1]:
            continue
        t = np.asarray(Image.fromarray(tmpl_gray).resize((tw, th), Image.BILINEAR), dtype=np.float64)
        m = ncc_map(img_gray, t)
        idx = int(np.argmax(m))
        y, x = divmod(idx, m.shape[1])
        score = float(m[y, x])
        if score > best[0]:
            best = (score, x, y, tw, th)
    return best


# ---------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="1bbd5689")
    ap.add_argument("--template", type=Path)
    ap.add_argument("--capture", type=Path, help="save a full screenshot here")
    ap.add_argument("--crop", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                    help="crop a template out of the last capture")
    ap.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                    help="restrict the search area (full-res pixels)")
    ap.add_argument("--scale", type=float, default=0.5, help="analysis downscale factor")
    ap.add_argument("--threshold", type=float, default=0.80)
    ap.add_argument("--scales", default="1.0,0.9,1.1,1.2")
    ap.add_argument("--interval", type=float, default=1.0)
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--tap", action="store_true", help="actually tap (else dry-run)")
    ap.add_argument("--swipe", action="store_true", help="swipe instead of tap (curve throw)")
    ap.add_argument("--debug-dir", type=Path, default=Path("tools/pgo_debug"))
    args = ap.parse_args()

    if args.capture:
        args.capture.parent.mkdir(parents=True, exist_ok=True)
        img = grab(args.serial)
        img.save(args.capture)
        print(f"[capture] {args.capture} {img.size}")
        return 0

    if args.crop:
        src = Path("tools/pgo_last.png")
        if not src.exists():
            print("no tools/pgo_last.png -- run --capture first", file=sys.stderr)
            return 2
        x, y, w, h = args.crop
        img = Image.open(src)
        img.crop((x, y, x + w, y + h)).save("tools/pgo_tpl.png")
        print(f"[crop] tools/pgo_tpl.png {w}x{h} @ ({x},{y})")
        return 0

    if not args.template:
        ap.print_help()
        return 2

    tmpl_img = Image.open(args.template).convert("L")
    scales = tuple(float(s) for s in args.scales.split(","))
    args.debug_dir.mkdir(parents=True, exist_ok=True)

    hits = 0
    for i in range(args.count):
        img = grab(args.serial)
        img.save(Path("tools/pgo_last.png"))
        full = np.asarray(img.convert("L"), dtype=np.float64)
        scale = args.scale
        small = np.asarray(img.convert("L").resize((int(img.width * scale), int(img.height * scale))),
                           dtype=np.float64)
        ts = tmpl_img.resize((max(8, int(tmpl_img.width * scale)), max(8, int(tmpl_img.height * scale))),
                             Image.BILINEAR)
        tpl_small = np.asarray(ts, dtype=np.float64)

        if args.region:
            rx, ry, rw, rh = args.region
            sx0, sy0 = int(rx * scale), int(ry * scale)
            sub = small[sy0:sy0 + int(rh * scale), sx0:sx0 + int(rw * scale)]
            score, x, y, w, h = best_match(sub, tpl_small, scales)
            x += sx0
            y += sy0
        else:
            score, x, y, w, h = best_match(small, tpl_small, scales)

        cx = int((x + w / 2) / scale)
        cy = int((y + h / 2) / scale)
        print(f"[{i}] score={score:.3f} centre=({cx},{cy}) size={int(w/scale)}x{int(h/scale)} "
              f"-> {'HIT' if score >= args.threshold else 'miss'}")

        dbg = img.copy()
        from PIL import ImageDraw
        d = ImageDraw.Draw(dbg)
        d.rectangle([int(x / scale), int(y / scale), int((x + w) / scale), int((y + h) / scale)],
                    outline=(0, 255, 0), width=5)
        d.ellipse([cx - 12, cy - 12, cx + 12, cy + 12], outline=(255, 0, 255), width=5)
        dbg.save(args.debug_dir / f"frame_{i:03d}.png")

        if score >= args.threshold:
            hits += 1
            if args.tap:
                if args.swipe:
                    swipe(args.serial, cx, cy, cx, cy - 420, 200)
                else:
                    tap(args.serial, cx, cy)
                print(f"    -> {'swiped' if args.swipe else 'tapped'} ({cx},{cy})")
        if i + 1 < args.count:
            time.sleep(args.interval)

    print(f"done: {hits}/{args.count} above threshold {args.threshold}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
