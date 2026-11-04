"""Layer-level driver client + the verified catch loop for PGSharp.

Two things make this fast:

1.  Everything is driven through the *accessibility layer* (our own
    instrumentation APK, com.opencode.pgodrive) instead of screencap:
        - read the node tree with labels and bounds
        - click a node by name with a real ACTION_CLICK
    A node-tree read costs ~0.1 s versus ~2.5 s for `uiautomator dump` and
    ~0.9 s for a screenshot.

2.  The catch flow uses the two gestures that were verified on the device:
        double-click a left floating-bar entry  -> encounter opens
        120 ms flick of the ball               -> the throw
    No map scanning, no ball-tray round trip.

Rules enforced (see pgo_rules.py): never throw a Great Ball, never feed a
Golden Razz.  The default ball is the plain Poké Ball.

Usage:
    python tools/pgo_fast.py --catches 5
    python tools/pgo_fast.py --catches 5 --minutes 20
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import numpy as np
from PIL import Image

from pgo_record import Session
from pgo_rules import DEFAULT_BALL, assert_ball_allowed
from pgo_vision import grab_raw

SERIAL = "1bbd5689"
BASE = "/sdcard/Android/data/com.opencode.pgodrive/files"
CMD = BASE + "/cmd.txt"
OUT = BASE + "/out.txt"

# Left floating bar: the PGSharp "nearby spawn" shortcuts.
FEED_X = 58
FEED_Y = [1048, 1161, 1274, 1387, 1500, 1613]
# The ball is thrown with a fast flick; anything slower opens the ball tray.
BALL = (540, 1990)
THROW_TO = (540, 1000)
THROW_MS = 120


# ------------------------------------------------------------------ driver
def sh(cmd: str) -> str:
    return subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                          capture_output=True, text=True).stdout


def drive(cmd: str, timeout: float = 15.0) -> str:
    sh(f"rm -f {OUT}")
    sh(f"printf '%s' '{cmd}' > {CMD}")
    t0 = time.time()
    while time.time() - t0 < timeout:
        out = sh(f"cat {OUT} 2>/dev/null")
        if out and out.strip():
            return out.strip()
        time.sleep(0.03)
    return "TIMEOUT"


def dclick(x: int, y: int, gap: float = 0.09) -> str:
    drive(f"click {x} {y}")
    time.sleep(gap)
    return drive(f"click {x} {y}")


def click(x: int, y: int) -> str:
    return drive(f"click {x} {y}")


def swipe(x1, y1, x2, y2, ms) -> str:
    return drive(f"swipe {x1} {y1} {x2} {y2} {ms}")


def nodes() -> list[dict]:
    """Layer tree as a list of dicts (parsed from the driver's TSV output)."""
    out = drive("dump")
    rows = []
    for line in out.splitlines()[1:]:
        p = line.split("|")
        if len(p) < 4:
            continue
        try:
            l, t, r, b = (int(v) for v in p[3].split(","))
        except ValueError:
            continue
        rows.append({"cls": p[0], "text": p[1], "desc": p[2],
                     "l": l, "t": t, "r": r, "b": b, "cx": (l + r) // 2,
                     "cy": (t + b) // 2, "flags": p[4] if len(p) > 4 else ""})
    return rows


def texts() -> list[str]:
    return [n["text"] for n in nodes() if n["text"]]


# -------------------------------------------------------------- perception
def red_bottom(img: Image.Image) -> int:
    a = np.asarray(img.crop((250, 1750, 850, 2160)), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return int(((r > 140) & (g < 90) & (b < 95)).sum())


def white_ratio(img: Image.Image) -> float:
    g = np.asarray(img.crop((40, 900, 1040, 1900)).convert("L"), dtype=np.uint8)
    return float((g > 215).mean())


def state(img: Image.Image) -> str:
    if red_bottom(img) > 30000:
        return "encounter"
    if white_ratio(img) > 0.55:
        return "result"
    return "map"


def goto_map(steps: int = 6) -> bool:
    """Universal escape: X / Back until the map is back."""
    for _ in range(steps):
        img = grab_raw()
        st = state(img)
        if st == "map":
            return True
        if st == "result":
            drive("click 120 162")          # cancel on overlays
        else:
            sh("input keyevent KEYCODE_BACK")
        time.sleep(1.0)
    return state(grab_raw()) == "map"


# ------------------------------------------------------------------- bot
class FastBot:
    def __init__(self, sess: Session | None):
        self.sess = sess
        self.catches = 0
        self.throws = 0
        self.feed_clicks = 0
        self.fled = 0
        self.ball = DEFAULT_BALL
        assert_ball_allowed(self.ball)

    def log(self, *a):
        print(*a, flush=True)

    def record(self, img, label, action):
        if self.sess is None:
            return
        small = img.resize((img.width // 2, img.height // 2))
        self.sess.record(img, small, action, 1.0, label)

    def throw_once(self, img) -> str:
        """One flick of the ball; returns caught / free / fled."""
        action = {"type": "swipe", "x1": BALL[0], "y1": BALL[1],
                  "x2": THROW_TO[0], "y2": THROW_TO[1], "ms": THROW_MS,
                  "ball": self.ball}
        self.record(img, "encounter", action)
        swipe(BALL[0], BALL[1], THROW_TO[0], THROW_TO[1], THROW_MS)
        self.throws += 1
        deadline = time.time() + 14
        while time.time() < deadline:
            time.sleep(0.8)
            img2 = grab_raw()
            st = state(img2)
            if st == "result":
                self.record(img2, "result", {"type": "back"})
                sh("input keyevent KEYCODE_BACK")
                self.catches += 1
                return "caught"
            if st == "encounter":
                return "free"
            if red_bottom(img2) < 1500 and white_ratio(img2) < 0.15:
                return "fled"
        return "fled"

    def catch_current(self) -> bool:
        for _ in range(6):
            out = self.throw_once(grab_raw())
            if out == "caught":
                return True
            if out == "fled":
                self.fled += 1
                return False
        return False

    def run(self, budget_s: float, target: int) -> None:
        end = time.time() + budget_s
        idx = 0
        while time.time() < end and self.catches < target:
            img = grab_raw()
            st = state(img)
            if st == "encounter":
                self.log(f"  [catches={self.catches}] already in encounter")
                self.catch_current()
                goto_map()
                continue
            if st == "result":
                sh("input keyevent KEYCODE_BACK")
                time.sleep(0.8)
                continue
            # map: double click a floating-bar entry -> encounter
            y = FEED_Y[idx % len(FEED_Y)]
            idx += 1
            self.feed_clicks += 1
            self.record(img, "map", {"type": "double_click", "x": FEED_X, "y": y,
                                     "reason": "feed_entry"})
            dclick(FEED_X, y)
            time.sleep(2.2)
            img2 = grab_raw()
            st2 = state(img2)
            self.log(f"  feed click ({FEED_X},{y}) -> {st2}")
            if st2 == "encounter":
                self.catch_current()
                goto_map()
            elif st2 == "result":
                sh("input keyevent KEYCODE_BACK")
                time.sleep(0.8)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catches", type=int, default=5)
    ap.add_argument("--minutes", type=float, default=20.0)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args()

    sess = None
    if not args.no_record:
        root = args.out or Path("tools/pgo_sessions") / ("fast_" + time.strftime("%Y%m%d_%H%M%S"))
        root.mkdir(parents=True, exist_ok=True)
        sess = Session(root, {"serial": SERIAL, "policy": "layer_level_fast_catch",
                               "ball": DEFAULT_BALL, "throw_ms": THROW_MS,
                               "feed_entries": FEED_Y, "target_catches": args.catches})
        print(f"[fast] session {root}", flush=True)

    bot = FastBot(sess)
    print(f"[fast] target {args.catches} catches, budget {args.minutes:.0f} min", flush=True)
    try:
        bot.run(args.minutes * 60, args.catches)
    except KeyboardInterrupt:
        print("\n[fast] interrupted", flush=True)
    print(f"[fast] done catches={bot.catches} throws={bot.throws} "
          f"feed_clicks={bot.feed_clicks} fled={bot.fled}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
