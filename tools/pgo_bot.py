"""PGSharp auto-catcher for the Mix2S, driven at the UI-hierarchy layer.

Why the UI layer
----------------
`uiautomator dump` exposes the game's labels (Feeds / 自動行走 / 設置 /
蔓莓果 / L23 / IV62 / 10-12-6 ...) with exact bounds.  That is far more
robust than pixel templates and lets us read the game's *data* (level, IV,
IV split) instead of guessing from the picture.  Screenshots are still used,
but only where Unity draws sprites without labels (the map).

Primitives (all verified on the real device)
---------------------------------------------
  walk(dir, ms)     drag the virtual joystick        -> avatar moves
  turn(dir)         horizontal drag                  -> camera orbits
  tilt(dir)         vertical drag                    -> camera pitches
  zoom_in()         double tap                       -> map zoom in
  zoom_out()        two concurrent pointers          -> map zoom out
  click(x, y)       tap                              -> generic
  pick_best_ball()  open tray, choose the top ball   -> correct ball
  throw_ball()      120ms flick of the ball          -> the throw
  goto_map()        press X/Back until the map shows -> universal escape

Every decision is recorded to a session (frames + events.jsonl) so it can be
replayed over adb later, or used as imitation-learning data.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from pgo_record import Session
from pgo_rules import (DEFAULT_BALL, assert_ball_allowed, assert_berry_allowed,
                       describe as describe_rules)
from pgo_vision import grab_raw

SERIAL = "1bbd5689"

# ---------------------------------------------------------------- geometry
JOY = (135, 1380)            # virtual joystick centre (measured on the map)
STAR = (981, 153)            # PGSharp menu toggle
PG_MENU = {                  # PGSharp side menu entries (UI dump)
    "map": (928, 252), "speed": (977, 341), "autowalk": (967, 430),
    "feeds": (942, 519), "favorites": (947, 608),
    "teleport": (928, 697), "settings": (928, 786),
}
BALL_TRAY_BTN = (947, 1925)  # small ball icon bottom-right of encounter
BALL_THROW = (540, 1990)     # the throwable ball
# Tray slots, left -> right: 精靈球 / 超級球 / 高級球.  超級球 is banned (R1).
BALL_SLOTS = {"精靈球": (200, 1780), "超級球": (540, 1780), "高級球": (880, 1780)}
# We only ever select 精靈球 or 高級球; 超級球 never appears in this list.
BALL_SELECTABLE = ["高級球", "精靈球"]
MENU_X = (540, 1990)         # main-menu X
BACK = "KEYCODE_BACK"

# Fast screen signature: the encounter shows a BIG red ball at bottom centre
# (~70k red pixels) while the map only shows the small menu ball (~1-7k).
RED_ENCOUNTER = 30000
RED_MAP_MIN = 700


# ---------------------------------------------------------------- adb layer
def adb(*args, binary=False):
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def tap(x, y):
    adb("shell", "input", "tap", str(int(x)), str(int(y)))


def swipe(x1, y1, x2, y2, ms=400):
    adb("shell", "input", "swipe", str(int(x1)), str(int(y1)),
        str(int(x2)), str(int(y2)), str(int(ms)))


def back():
    adb("shell", "input", "keyevent", BACK)


def double_tap(x, y, gap=0.06):
    """Two taps close enough in time to register as a double tap."""
    tap(x, y)
    time.sleep(gap)
    tap(x, y)
    time.sleep(0.9)


def grab() -> Image.Image:
    return grab_raw()


def ensure_not_raid(dry=False) -> bool:
    """R5 guard, evaluated before any action on the field.

    Reads the interface from the data layer; if a 團體戰 sheet is open we close
    it with its X and never touch 對戰 / 私人小組 / 使用250MP.
    """
    try:
        from pgo_layer import leave_raid, state
    except Exception:
        return True
    st = state()
    if st != "raid":
        return True
    if not dry:
        leave_raid()
    return False


# ------------------------------------------------------------- UI hierarchy
def ui_nodes():
    """All nodes of the current view, with labels and bounds."""
    try:
        adb("shell", "uiautomator", "dump", "/sdcard/pgo_ui.xml")
        xml = adb("shell", "cat", "/sdcard/pgo_ui.xml")
    except RuntimeError:
        return []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return []
    out = []
    for n in root.iter("node"):
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds") or "")
        if not m:
            continue
        x1, y1, x2, y2 = (int(v) for v in m.groups())
        out.append({
            "text": n.get("text") or "", "desc": n.get("content-desc") or "",
            "cls": (n.get("class") or "").split(".")[-1],
            "clickable": n.get("clickable") == "true",
            "checked": n.get("checked") == "true",
            "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
            "w": x2 - x1, "h": y2 - y1,
        })
    return out


def ui_find(label, exact=False):
    want = label.lower()
    for n in ui_nodes():
        t = (n["text"] or n["desc"]).lower()
        if not t:
            continue
        if (t == want) if exact else (want in t):
            return n
    return None


def ui_texts():
    return [n["text"] for n in ui_nodes() if n["text"]]


def ui_click(label, exact=False):
    n = ui_find(label, exact)
    if not n:
        return None
    tap(n["cx"], n["cy"])
    time.sleep(1.2)
    return n


# -------------------------------------------------------------- perception
def read_mon_data():
    """Level / IV / IV-split straight out of the UI hierarchy."""
    texts = ui_texts()
    lvl = iv = split = None
    for i, t in enumerate(texts):
        if t == "L" and i + 1 < len(texts):
            lvl = texts[i + 1]
        if t == "IV" and i + 1 < len(texts):
            iv = texts[i + 1]
        if re.fullmatch(r"\d+/\d+/\d+", t):
            split = t
    return {"level": lvl, "iv": iv, "split": split}


def red_bottom(img) -> int:
    """Red pixels in the bottom band: big ball (encounter) vs menu ball (map)."""
    a = np.asarray(img.crop((250, 1750, 850, 2160)), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 140) & (g < 90) & (b < 95)).sum())


def white_ratio(img) -> float:
    g = np.asarray(img.crop((40, 900, 1040, 1900)).convert("L"), dtype=np.uint8)
    return float((g > 215).mean())


def screen_state(img) -> str:
    """Fast classification straight from one screenshot (no UI dump)."""
    if red_bottom(img) > RED_ENCOUNTER:
        return "encounter"
    if white_ratio(img) > 0.55:
        return "result"
    return "map"


def is_encounter() -> bool:
    """Encounter screen (fast path: one 0.9s screenshot)."""
    return screen_state(grab()) == "encounter"


def on_map() -> bool:
    img = grab()
    return red_bottom(img) > RED_MAP_MIN and white_ratio(img) < 0.5


# --------------------------------------------------------------- primitives
def goto_map(steps=6, dry=False) -> bool:
    """Universal escape: X / Back until the map is visible again."""
    for _ in range(steps):
        img = grab()
        st = screen_state(img)
        if st == "map" and red_bottom(img) > RED_MAP_MIN:
            return True
        if not dry:
            if st == "result":
                tap(120, 162)      # top-left cancel on overlays
            elif st == "encounter":
                back()
            else:
                back()
            time.sleep(1.1)
        else:
            return False
    return on_map()


def walk(direction="up", ms=2500, dry=False):
    d = {"up": (0, -180), "down": (0, 180), "left": (-180, 0), "right": (180, 0)}[direction]
    x1, y1 = JOY
    x2, y2 = x1 + d[0], y1 + d[1]
    if not dry:
        swipe(x1, y1, x2, y2, ms)
        time.sleep(0.5)
    return {"type": "walk", "direction": direction, "ms": ms,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def turn(direction="left", ms=600, dry=False):
    x1, x2 = (840, 320) if direction == "left" else (320, 840)
    if not dry:
        swipe(x1, 1150, x2, 1150, ms)
        time.sleep(0.6)
    return {"type": "turn", "direction": direction, "ms": ms,
            "x1": x1, "y1": 1150, "x2": x2, "y2": 1150}


def tilt(direction="up", ms=600, dry=False):
    x1, y1, x2, y2 = ((540, 1400, 540, 700) if direction == "up" else (540, 700, 540, 1400))
    if not dry:
        swipe(x1, y1, x2, y2, ms)
        time.sleep(0.6)
    return {"type": "tilt", "direction": direction, "ms": ms,
            "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def zoom_in(dry=False):
    if not dry:
        tap(540, 1150)
        time.sleep(0.07)
        tap(540, 1150)
        time.sleep(1.0)
    return {"type": "zoom_in", "x": 540, "y": 1150}


def zoom_out(dry=False):
    if not dry:
        p1 = subprocess.Popen(["adb", "-s", SERIAL, "shell", "input", "swipe",
                                "450", "1100", "250", "1100", "120"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p2 = subprocess.Popen(["adb", "-s", SERIAL, "shell", "input", "swipe",
                                "650", "1100", "850", "1100", "120"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p1.wait()
        p2.wait()
        time.sleep(1.0)
    return {"type": "zoom_out", "x1": 450, "y1": 1100, "x2": 250, "y2": 1100}


def select_default_ball(dry=False) -> str:
    """Open the tray once and select the default ball.

    R1: 超級球 (Great Ball) is never selected.
    The client keeps the selection, so every later throw uses this ball and
    we never have to pay the ~2.5 s tray round-trip again.
    """
    assert_ball_allowed(DEFAULT_BALL)
    if not dry:
        tap(*BALL_TRAY_BTN)
        time.sleep(1.3)
    x, y = BALL_SLOTS[DEFAULT_BALL]
    if not dry:
        tap(x, y)
        time.sleep(1.2)
    return DEFAULT_BALL


def throw_ball(dry=False):
    """120 ms flick of the ball.  Slower flicks open the ball tray instead."""
    if not dry:
        swipe(BALL_THROW[0], BALL_THROW[1], 540, 1000, 120)
        time.sleep(1.2)
    return {"type": "throw", "x1": BALL_THROW[0], "y1": BALL_THROW[1],
            "x2": 540, "y2": 1000, "ms": 120, "ball": DEFAULT_BALL}


# ------------------------------------------------------------------- policy
class Bot:
    def __init__(self, sess: Session | None, dry=False, read_data=False):
        self.sess = sess
        self.dry = dry
        self.read_data = read_data   # extra 3.5s UI dump for L/IV labels
        self.catches = 0
        self.throws = 0
        self.taps = 0
        self.fled = 0
        self.seen = 0
        self.ball = DEFAULT_BALL

    def log(self, *a):
        print(*a, flush=True)

    def act(self, img, state, action, extra=None):
        rec = dict(action)
        if extra:
            rec.update(extra)
        if self.sess is not None:
            small = img.resize((img.width // 2, img.height // 2))
            self.sess.record(img, small, rec, 1.0, state)
        t = rec.get("type")
        if self.dry:
            return
        if t == "tap":
            tap(rec["x"], rec["y"])
            time.sleep(1.3)
        elif t == "swipe":
            swipe(rec["x1"], rec["y1"], rec["x2"], rec["y2"], rec.get("ms", 400))
            time.sleep(rec.get("after", 0.6))
        elif t == "back":
            back()
            time.sleep(1.3)
        elif t == "walk":
            walk(rec.get("direction", "up"), rec.get("ms", 2500))
        elif t == "turn":
            turn(rec.get("direction", "left"), rec.get("ms", 600))
        elif t == "tilt":
            tilt(rec.get("direction", "up"), rec.get("ms", 600))
        elif t == "zoom_in":
            zoom_in()
        elif t == "zoom_out":
            zoom_out()
        elif t == "throw":
            throw_ball()
        elif t == "pick_ball":
            pick_best_ball()
        elif t == "ui_tap":
            ui_click(rec.get("label", ""))

    # ---------------------------------------------------------------- catch
    def do_encounter(self, img) -> bool:
        """Throw the moment we are in the encounter, then poll for the result."""
        # Optional: read the game's own data (level / IV) for the dataset.
        data = {}
        if self.read_data:
            data = read_mon_data()
        ball = self.ball
        self.log(f"    encounter {data} ball={ball}")
        for attempt in range(6):
            self.act(img, "encounter", throw_ball(), {"ball": ball, **data})
            self.throws += 1
            deadline = time.time() + 14
            while time.time() < deadline:
                time.sleep(0.9)
                img2 = grab()
                st = screen_state(img2)
                if st == "result":
                    self.log("    -> caught")
                    self.act(img2, "result", {"type": "back"})
                    self.catches += 1
                    return True
                if st == "encounter":
                    self.log("    -> broke free, re-throw")
                    break
                if red_bottom(img2) < 2000 and white_ratio(img2) < 0.2:
                    self.log("    -> fled")
                    self.fled += 1
                    return False
            else:
                self.log("    -> timeout")
                self.fled += 1
                return False
        return False

    # ---------------------------------------------------------------- sweep
    def sweep(self, budget_s: float, target: int) -> None:
        end = time.time() + budget_s
        turns = 0
        while time.time() < end and self.catches < target:
            if not ensure_not_raid(self.dry):      # R5: never enter a raid
                self.log("    raid sheet found -> closed (R5)")
                continue
            if is_encounter():
                self.do_encounter(grab())
                self.log(f"  [catches={self.catches} throws={self.throws} taps={self.taps}]")
                goto_map(dry=self.dry)
                continue

            img = grab()
            if white_ratio(img) > 0.55:
                self.act(img, "overlay", {"type": "tap", "x": 120, "y": 162})
                time.sleep(1.2)
                continue

            # on the map: try a nearby spawn from the left feed column,
            # otherwise sweep the map by clicking high-variance points
            txts = ui_texts()
            feed = [n for n in ui_nodes()
                    if n["cls"] == "ImageView" and 1000 < n["cy"] < 1700 and n["cx"] < 120]
            if feed:
                n = feed[0]
                self.taps += 1
                self.act(img, "map", {"type": "tap", "x": n["cx"], "y": n["cy"]},
                         {"reason": "feed_entry"})
                time.sleep(3.5)
                continue

            from pgo_vision import candidates
            pts = candidates(img, 12)
            if not pts:
                turns += 1
                self.act(img, "map", turn("left"), {"reason": "no_candidates"})
                continue
            _, x, y = pts[0]
            self.taps += 1
            self.act(img, "map", {"type": "tap", "x": x, "y": y}, {"reason": "spawn_probe"})
            time.sleep(2.2)
            turns += 1
            if turns % 4 == 0:
                self.act(grab(), "map", walk("up", 2500), {"reason": "explore"})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catches", type=int, default=10)
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = args.out or Path("tools/pgo_sessions") / ("bot_" + time.strftime("%Y%m%d_%H%M%S"))
    root.mkdir(parents=True, exist_ok=True)
    sess = Session(root, {"serial": SERIAL, "policy": "ui_layer_catch",
                           "ball_priority": BALL_PRIORITY,
                           "target_catches": args.catches})
    print(f"[bot] session {root}", flush=True)
    bot = Bot(sess, args.dry_run)
    try:
        bot.sweep(args.minutes * 60, args.catches)
    except KeyboardInterrupt:
        print("\n[bot] interrupted", flush=True)
    print(f"[bot] done catches={bot.catches} throws={bot.throws} taps={bot.taps} "
          f"fled={bot.fled}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
