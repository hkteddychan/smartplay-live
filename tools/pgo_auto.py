"""Autonomous catch loop for the Mix2S PGO build, with ML recording.

State machine per iteration (one screenshot per decision):

    ENCOUNTER -> flick the ball, poll for the outcome, retry if it breaks free
    RESULT    -> white overlay: onboarding dialog -> cancel, catch card -> BACK
    STOP      -> close the PokéStop / gym photo disc
    MAP       -> tap the next candidate point (local-variance ranking)
    OTHER     -> wait (throw animation, transitions)

Every decision writes a frame + action pair into the session (events.jsonl),
so the run can be replayed later over adb without any vision.

Usage:
    python tools/pgo_auto.py --catches 10 --minutes 30
    python tools/pgo_auto.py --catches 10 --dry-run
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from pgo_record import Session
from pgo_throw import best_match
from pgo_vision import candidates, grab_raw

SERIAL = "1bbd5689"
TPL_DIR = Path(__file__).parent / "templates"
BERRY_TPL = TPL_DIR / "tpl_berry.png"

# Encounter layout (1080x2160), measured on the real device.
BALL = (540, 1990)
THROW_END = (540, 1000)
THROW_MS = 120

# Fallback grid, used only when the variance ranking finds nothing.
GRID_X = list(range(130, 1000, 140))
GRID_Y = list(range(360, 1800, 200))

CANCEL_XY = (540, 2024)

# Thresholds measured on real frames.
T_BERRY = 0.65
T_WHITE = 0.60
T_RED_STOP = 40000
T_RED_MAP = 4500
T_CYAN = 3000


# ------------------------------------------------------------------ adb layer
def adb(*args, binary=False):
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def grab() -> Image.Image:
    return grab_raw()


def tap(x, y):
    adb("shell", "input", "tap", str(int(x)), str(int(y)))


def swipe(x1, y1, x2, y2, ms):
    adb("shell", "input", "swipe", str(int(x1)), str(int(y1)),
        str(int(x2)), str(int(y2)), str(int(ms)))


def back():
    adb("shell", "input", "keyevent", "KEYCODE_BACK")


# -------------------------------------------------------------- perception
_BERRY = None


def berry_score(img: Image.Image, scale: float = 0.5) -> float:
    global _BERRY
    if _BERRY is None:
        t = Image.open(BERRY_TPL).convert("L")
        _BERRY = np.asarray(t.resize((max(8, int(t.width * scale)), max(8, int(t.height * scale))),
                                    Image.BILINEAR), dtype=np.float64)
    g = img.convert("L")
    small = np.asarray(g.resize((int(img.width * scale), int(img.height * scale))), dtype=np.float64)
    s = img.width / 1080.0
    rx, ry, rw, rh = 0, 1800 * s, 300 * s, 360 * s
    sub = small[int(ry * scale):int((ry + rh) * scale), int(rx * scale):int((rx + rw) * scale)]
    score, _, _, _, _ = best_match(sub, _BERRY, (1.0,))
    return float(score)


def red_bottom(img: Image.Image) -> int:
    s = img.width / 1080.0
    a = np.asarray(img.crop((int(250 * s), int(1750 * s), int(850 * s), img.height)), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 140) & (g < 90) & (b < 95)).sum())


def white_ratio(img: Image.Image) -> float:
    s = img.width / 1080.0
    g = np.asarray(img.crop((int(40 * s), int(900 * s), int(1040 * s), int(1900 * s))).convert("L"),
                   dtype=np.uint8)
    return float((g > 215).mean())


def cyan_count(img: Image.Image) -> int:
    s = img.width / 1080.0
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    b = a[int(1740 * s):int(1900 * s), int(60 * s):int(1020 * s)]
    r, g, bl = b[..., 0], b[..., 1], b[..., 2]
    return int(((r < 130) & (g > 150) & (bl > 200)).sum())


def classify(img: Image.Image) -> str:
    if berry_score(img) > T_BERRY:
        return "encounter"
    if white_ratio(img) > T_WHITE:
        return "result"
    red = red_bottom(img)
    if red > T_RED_STOP:
        return "stop"
    if red > T_RED_MAP:
        return "map"
    return "other"


# ------------------------------------------------------------------- policy
class Catcher:
    def __init__(self, session: Session | None, dry: bool, verbose=True):
        self.sess = session
        self.dry = dry
        self.verbose = verbose
        self.catches = 0
        self.throws = 0
        self.taps = 0
        self.fled = 0
        self.stops = 0
        self.refills = 0

    def log(self, *a):
        if self.verbose:
            print(*a, flush=True)

    def do(self, img, state, action, score=1.0):
        if self.sess is not None:
            small = img.resize((img.width // 2, img.height // 2))
            self.sess.record(img, small, action, score, state)
        if self.dry:
            return
        t = action["type"]
        if t == "tap":
            tap(action["x"], action["y"])
        elif t == "swipe":
            swipe(action["x1"], action["y1"], action["x2"], action["y2"], action.get("ms", 200))
        elif t == "back":
            back()

    def dismiss_white(self, img, state="result"):
        """White overlay: dialog -> cancel button (top-left), catch card -> BACK."""
        # catch card: white bg with ~90%+ white in lower band -> BACK
        if white_ratio(img) > T_WHITE:
            self.do(img, state, {"type": "back"})
            time.sleep(1.4)
        else:
            # filter dialog / other white overlay: tap top-left cancel (120,162)
            self.do(img, "dialog", {"type": "tap", "x": 120, "y": 162})
            time.sleep(1.2)

    # ---------------------------------------------------------------- states
    def throw_and_wait(self, img) -> str:
        self.do(img, "encounter", {"type": "swipe", "x1": BALL[0], "y1": BALL[1],
                                   "x2": THROW_END[0], "y2": THROW_END[1], "ms": THROW_MS})
        self.throws += 1
        t_end = time.time() + 18.0
        while time.time() < t_end:
            time.sleep(2.0)
            st = classify(grab())
            if st == "result":
                self.log("      -> caught")
                return "caught"
            if st == "encounter":
                self.log("      -> broke free")
                return "free"
            if st == "map":
                self.log("      -> fled / back to map")
                return "fled"
        self.log("      -> timeout")
        return "fled"

    def handle_encounter(self, img) -> None:
        for _ in range(10):
            out = self.throw_and_wait(img)
            if out == "caught":
                self.dismiss_white(grab(), "result")
                self.catches += 1
                return
            if out == "fled":
                self.fled += 1
                time.sleep(0.8)
                return
            img = grab()
        self.do(img, "encounter", {"type": "back"})
        time.sleep(1.4)

    def sweep(self, budget_seconds: float, target: int) -> None:
        t_end = time.time() + budget_seconds
        queue: list[tuple[int, int]] = []
        img = grab()
        while time.time() < t_end and self.catches < target:
            st = classify(img)

            if st == "encounter":
                self.handle_encounter(img)
                self.log(f"  [catches={self.catches}] throws={self.throws} taps={self.taps} "
                         f"fled={self.fled} stops={self.stops}")
                img = grab()
                continue

            if st == "result":
                self.dismiss_white(img)
                img = grab()
                continue

            if st == "stop":
                self.stops += 1
                self.do(img, st, {"type": "tap", "x": CANCEL_XY[0], "y": CANCEL_XY[1]})
                time.sleep(1.3)
                img = grab()
                continue

            if st == "other":
                time.sleep(1.2)
                img = grab()
                continue

            # map: tap the next ranked candidate
            if not queue:
                self.refills += 1
                if self.refills % 4 == 0:
                    # walk forward with the virtual joystick to reach new spawns
                    self.do(img, "map", {"type": "swipe", "x1": 153, "y1": 720,
                                         "x2": 153, "y2": 560, "ms": 2500})
                    time.sleep(0.7)
                    img = grab()
                elif self.refills % 2 == 0:
                    # spin the camera to reveal a new scene
                    self.do(img, "map", {"type": "swipe", "x1": 840, "y1": 1150,
                                         "x2": 320, "y2": 1150, "ms": 600})
                    time.sleep(0.9)
                    img = grab()
                queue = [(x, y) for _, x, y in candidates(img, 16)]
                if not queue:
                    queue = [(x, y) for y in GRID_Y for x in GRID_X]
            x, y = queue.pop(0)
            self.taps += 1
            self.do(img, "map", {"type": "tap", "x": x, "y": y})
            time.sleep(1.0)
            img = grab()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catches", type=int, default=10)
    ap.add_argument("--minutes", type=float, default=60.0)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    sess = None
    if not args.no_record:
        root = args.out or Path("tools/pgo_sessions") / time.strftime("%Y%m%d_%H%M%S")
        root.mkdir(parents=True, exist_ok=True)
        sess = Session(root, {
            "serial": SERIAL,
            "policy": "variance_candidates + flick_throw",
            "ball": BALL, "throw_end": THROW_END, "throw_ms": THROW_MS,
            "fallback_grid_x": GRID_X, "fallback_grid_y": GRID_Y,
            "thresholds": {"berry": T_BERRY, "white": T_WHITE, "red_stop": T_RED_STOP,
                           "red_map": T_RED_MAP, "cyan": T_CYAN},
            "target_catches": args.catches,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
        print(f"[session] {root}", flush=True)

    c = Catcher(sess, args.dry_run)
    print(f"[auto] target {args.catches} catches, budget {args.minutes:.0f} min", flush=True)
    try:
        c.sweep(args.minutes * 60, args.catches)
    except KeyboardInterrupt:
        print("\n[auto] interrupted", flush=True)
    print(f"[auto] done: catches={c.catches} throws={c.throws} taps={c.taps} "
          f"fled={c.fled} stops={c.stops}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
