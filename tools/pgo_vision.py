"""Fast perception helpers shared by the auto-catcher.

Two speed wins over the naive loop:
  * raw screencap (no PNG encode on the device): ~1.9s vs ~4.2s
  * one screenshot per decision instead of two

Candidate generation uses local pixel variance: wild spawns, PokéStops and
power spots are all detailed 3D models sitting on flat ground, so a variance
map with non-maximum suppression gives a short list of worth-tapping points.
"""
from __future__ import annotations

import subprocess

import numpy as np
from PIL import Image

SERIAL = "1bbd5689"


def adb_raw(*args) -> bytes:
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout


def grab_raw() -> Image.Image:
    """Screenshot straight from the framebuffer, no PNG encode (~1.9s)."""
    data = adb_raw("exec-out", "screencap")
    w = int.from_bytes(data[0:4], "little")
    h = int.from_bytes(data[4:8], "little")
    need = w * h * 4
    # Android 12+ prepends a 16-byte header (w, h, format, dataspace);
    # older builds use 12. Derive the offset instead of guessing.
    off = len(data) - need
    if off < 12 or off > 32:
        raise RuntimeError(f"unexpected screencap size {len(data)} for {w}x{h}")
    buf = np.frombuffer(data, dtype=np.uint8, offset=off, count=need)
    arr = buf.reshape(h, w, 4)[:, :, :3]
    return Image.fromarray(np.ascontiguousarray(arr))


def _box_mean(a: np.ndarray, k: int) -> np.ndarray:
    ii = np.zeros((a.shape[0] + 1, a.shape[1] + 1), dtype=np.float64)
    ii[1:, 1:] = a.cumsum(0).cumsum(1)
    s = ii[k:, k:] - ii[:-k, k:] - ii[k:, :-k] + ii[:-k, :-k]
    return s / (k * k)


def candidates(img: Image.Image, max_n: int = 14, scale: float = 0.5,
               area=(0.14, 0.10, 0.72, 0.78), k: int = 13,
               nms: int = 55) -> list[tuple[float, int, int]]:
    """Rank points by local pixel variance inside the play area.

    Excluded regions:
      x < 0.14  -> PGSharp nearby-feed column (sprite icons) + joystick
      x > 0.72  -> PGSharp side menu
      y > 0.78  -> bottom UI bar (menu ball, nearby/journal/profile)
    """
    small = img.resize((int(img.width * scale), int(img.height * scale)))
    g = np.asarray(small.convert("L"), dtype=np.float64)
    mean = _box_mean(g, k)
    var = np.maximum(_box_mean(g * g, k) - mean * mean, 0.0)

    h, w = var.shape
    x0, y0 = int(w * area[0]), int(h * area[1])
    x1, y1 = int(w * area[2]), int(h * area[3])
    work = np.full_like(var, -1.0)
    work[y0:y1, x0:x1] = var[y0:y1, x0:x1]

    out = []
    for _ in range(max_n):
        idx = int(np.argmax(work))
        y, x = divmod(idx, work.shape[1])
        v = float(work[y, x])
        if v <= 25.0:
            break
        out.append((v, int(x / scale), int(y / scale)))
        work[max(0, y - nms):y + nms, max(0, x - nms):x + nms] = -1
    return out
