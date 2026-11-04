"""Game interface primitives + a layout learner that records everything as ML.

Everything here is expressed as *named interface states* so the rest of the
toolchain can reason about the game rather than about raw pixels.

Core contract
-------------
`goto_map()` is the universal escape hatch: whatever we are looking at, it
presses X / Exit / Back until we are back on the map screen.  Every other
routine starts and ends with it.

Recorded layout
---------------
    tools/pgo_layout.py learn   -> walk every interface, record frames+labels
    tools/pgo_layout.py show    -> print the learned layout table
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from pgo_record import Session
from pgo_throw import best_match
from pgo_vision import grab_raw

SERIAL = "1bbd5689"

# ---------------------------------------------------------------- geometry
# Full-res coordinates (1080x2160) measured on the live device.
PG_MAP, PG_SPEED, PG_AUTOWALK, PG_FEEDS, PG_FAV, PG_TP, PG_SETTINGS = (
    (860, 250), (860, 350), (860, 440), (860, 530), (860, 625), (860, 715), (860, 790))
X_CLOSE_BTN = (540, 1990)          # main-menu X
EXIT_BTN = (540, 2020)             # generic overlay X / cancel
TOP_RIGHT_X = (975, 140)           # map-viewer close
BACK_KEY = "KEYCODE_BACK"

JOY_CENTER = (135, 1380)           # virtual joystick centre (measured on map)
BALL_THROW = (540, 1990)           # throwable ball in encounter
BALL_SELECT = (956, 1926)          # ball type selector
BERRY_BTN = (120, 1926)

# ---------------------------------------------------------------- adb layer
def adb(*args, binary=False):
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def tap(x, y):
    adb("shell", "input", "tap", str(int(x)), str(int(y)))


def swipe(x1, y1, x2, y2, ms=400):
    adb("shell", "input", "swipe", str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(int(ms)))


def back():
    adb("shell", "input", "keyevent", BACK_KEY)


def grab() -> Image.Image:
    return grab_raw()


# -------------------------------------------------------------- perception
def gray_small(img, scale=0.5):
    return np.asarray(img.convert("L").resize((int(img.width * scale), int(img.height * scale))),
                       dtype=np.float64)


def white_ratio(img) -> float:
    s = img.width / 1080.0
    g = np.asarray(img.crop((int(40 * s), int(900 * s), int(1040 * s), int(1900 * s))).convert("L"),
                   dtype=np.uint8)
    return float((g > 215).mean())


def bottom_red(img) -> int:
    s = img.width / 1080.0
    a = np.asarray(img.crop((int(250 * s), int(1750 * s), int(850 * s), img.height)), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 140) & (g < 90) & (b < 95)).sum())


def menu_pokeball(img) -> int:
    """Red pixels of the big menu Pokéball at the bottom centre of the map."""
    s = img.width / 1080.0
    a = np.asarray(img.crop((int(480 * s), int(1930 * s), int(600 * s), int(2070 * s))), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 140) & (g < 90) & (b < 95)).sum())


def is_map(img) -> bool:
    """Map screen: the big red menu Pokéball sits at bottom centre."""
    return menu_pokeball(img) > 1200 and white_ratio(img) < 0.5


def is_overlay(img) -> bool:
    return white_ratio(img) > 0.55


# --------------------------------------------------------------- primitives
def goto_map(max_steps=6, dry=False, log=print) -> bool:
    """Universal escape: press X / Exit / Back until the map is visible."""
    for i in range(max_steps):
        img = grab()
        if is_map(img):
            return True
        if is_overlay(img):
            # white overlay: try the top-left / bottom cancel buttons
            if not dry:
                tap(*EXIT_BTN)
                time.sleep(1.2)
                continue
        if not dry:
            back()
            time.sleep(1.2)
        else:
            return False
    return is_map(grab())


def walk(direction="up", ms=2500, dry=False):
    """Drag the virtual joystick; the avatar walks while the finger is held."""
    dx, dy = {"up": (0, -180), "down": (0, 180), "left": (-180, 0), "right": (180, 0)}[direction]
    x1, y1 = JOY_CENTER
    x2, y2 = x1 + dx, y1 + dy
    if not dry:
        swipe(x1, y1, x2, y2, ms)
    return {"type": "walk", "direction": direction, "ms": ms,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def turn(direction="left", ms=600, dry=False):
    """Horizontal drag rotates the camera around the avatar."""
    x1, x2 = (840, 320) if direction == "left" else (320, 840)
    if not dry:
        swipe(x1, 1150, x2, 1150, ms)
    return {"type": "turn", "direction": direction, "ms": ms,
            "x1": x1, "y1": 1150, "x2": x2, "y2": 1150}


def tilt(direction="up", ms=600, dry=False):
    x1, y1, x2, y2 = ((540, 1400, 540, 700) if direction == "up" else (540, 700, 540, 1400))
    if not dry:
        swipe(x1, y1, x2, y2, ms)
    return {"type": "tilt", "direction": direction, "ms": ms,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def zoom_in(ms=120, dry=False):
    """Double tap zooms the map in."""
    if not dry:
        tap(540, 1150)
        time.sleep(0.07)
        tap(540, 1150)
        time.sleep(1.0)
    return {"type": "zoom_in", "x": 540, "y": 1150, "ms": ms}


def zoom_out(ms=120, dry=False):
    """Two concurrent pointers moving apart (SELinux blocks real pinch)."""
    if not dry:
        p1 = subprocess.Popen(["adb", "-s", SERIAL, "shell", "input", "swipe",
                                "450", "1100", "250", "1100", str(ms)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p2 = subprocess.Popen(["adb", "-s", SERIAL, "shell", "input", "swipe",
                                "650", "1100", "850", "1100", str(ms)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p1.wait()
        p2.wait()
        time.sleep(1.0)
    return {"type": "zoom_out", "x1": 450, "y1": 1100, "x2": 250, "y2": 1100, "ms": ms}


def click(x, y, dry=False):
    if not dry:
        tap(x, y)
        time.sleep(1.2)
    return {"type": "click", "x": x, "y": y}


def throw_ball(dry=False):
    """Fast flick of the ball: 120ms, otherwise the client opens the ball tray."""
    if not dry:
        swipe(BALL_THROW[0], BALL_THROW[1], 540, 1000, 120)
        time.sleep(1.5)
    return {"type": "throw", "x1": BALL_THROW[0], "y1": BALL_THROW[1],
            "x2": 540, "y2": 1000, "ms": 120}


# ------------------------------------------------------------------ layout
# Every interface we know how to reach, plus how to get back out.
INTERFACES = [
    ("map",             None,                                   "already"),
    ("pg_side_menu",    PG_MAP,                                 "click"),
    ("pg_map_viewer",   PG_MAP,                                 "click"),
    ("pg_feeds",        PG_FEEDS,                               "click"),
    ("pg_favorites",    PG_FAV,                                 "click"),
    ("pg_settings",     PG_SETTINGS,                            "click"),
    ("pg_autowalk",     PG_AUTOWALK,                            "click"),
    ("main_menu",       (534, 2000),                            "click"),
    ("main_menu_items", (534, 2000),                            "click"),
    ("nearby_panel",    (830, 1930),                            "click"),
    ("journal_panel",   (910, 1930),                            "click"),
    ("profile_panel",   (980, 1930),                            "click"),
    ("research_panel",  (980, 1730),                            "click"),
    ("weather_panel",   (60, 804),                              "click"),
]


def learn(rounds=2, out=None, dry=False):
    root = out or Path("tools/pgo_sessions") / ("layout_" + time.strftime("%Y%m%d_%H%M%S"))
    root.mkdir(parents=True, exist_ok=True)
    sess = Session(root, {"serial": SERIAL, "policy": "interface_layout_learn",
                           "rounds": rounds})
    print(f"[layout] session {root}", flush=True)

    for r in range(rounds):
        for name, coord, kind in INTERFACES:
            goto_map(dry=dry)
            img = grab()
            small = img.resize((img.width // 2, img.height // 2))
            action = {"type": "none"}
            if kind == "click" and coord:
                action = click(coord[0], coord[1], dry=dry)
            sess.record(img, small, action, 1.0, name)
            time.sleep(1.2)
            # capture the opened interface
            img2 = grab()
            sess.record(img2, img2.resize((img2.width // 2, img2.height // 2)),
                        {"type": "none"}, 1.0, f"{name}:open")
            print(f"[{r + 1}/{rounds}] {name}", flush=True)
    print(f"[layout] done -> {root}", flush=True)
    return root


def show():
    path = Path("tools/pgo_layout.json")
    if not path.exists():
        print("no learned layout yet; run `pgo_layout.py learn`")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    for k, v in data.items():
        print(f"{k:20s} {v}")


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("learn")
    c.add_argument("--rounds", type=int, default=2)
    c.add_argument("--out", default=None)
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(func=lambda a: (learn(a.rounds, a.out, a.dry_run), 0)[1])
    s = sub.add_parser("show")
    s.set_defaults(func=lambda a: (show(), 0)[1])
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
