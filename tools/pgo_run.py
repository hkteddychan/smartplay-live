"""Layer-first autonomous loop: walk, spin by proximity, catch, record.

Design rules baked in
---------------------
* Every decision is made from the accessibility layer (pgo_layer).  A
  screenshot is taken only to *pick a tap target* on the Unity map, never to
  decide what screen we are on.
* R1/R2/R3: only 精靈球 is thrown; the ball is asserted before every throw and
  no berry is ever fed.
* R5: a 團體戰 sheet is detected and closed; the bot never joins a raid.
* The device hangs if MotionEvents arrive faster than Unity can consume them,
  so every input is followed by a settle delay and the loop is single-input.

Usage
-----
    python tools/pgo_run.py --catches 5 --minutes 20
    python tools/pgo_run.py --catches 3 --no-record
    python tools/pgo_run.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

import pgo_bot as B
import pgo_layer as L
from pgo_record import Session
from pgo_rules import DEFAULT_BALL, assert_ball_allowed, describe
from pgo_vision import candidates

AVATAR = (540, 1500)
AVATAR_CLEAR = 95      # only skip the avatar sprite itself
SETTLE = 3.0           # seconds to let Unity breathe after every input
MAX_MAP_TAPS = 3       # failed target taps before we walk instead
ORANGE_MAX = 0.25      # PokéStops / pumpkins / leaves are orange; spawns are not


def orange_ratio(img, x: int, y: int, r: int = 55) -> float:
    """Fraction of strongly-orange pixels around a point (Halloween props)."""
    a = np.asarray(img.crop((max(0, x - r), max(0, y - r),
                             min(img.width, x + r), min(img.height, y + r))),
                   dtype=np.int16)
    px = a.reshape(-1, 3)
    R, B = px[:, 0], px[:, 2]
    G = px[:, 1]
    return float(((R > 150) & (R - B > 90) & (G > 60) & (G < 200)).mean())


class Runner:
    def __init__(self, sess: Session | None, dry=False, settle=SETTLE):
        self.sess = sess
        self.dry = dry
        self.settle = settle
        self.catches = 0
        self.throws = 0
        self.spins = 0
        self.taps = 0
        self.raids_closed = 0
        self.walks = 0
        self.ball = assert_ball_allowed(DEFAULT_BALL)

    # ------------------------------------------------------------------ util
    def log(self, *a):
        print(time.strftime("[%H:%M:%S]"), *a, flush=True)

    def record(self, label, action, img=None):
        if self.sess is None:
            return
        if img is None:
            img = B.grab()
        small = img.resize((img.width // 2, img.height // 2))
        self.sess.record(img, small, action, 1.0, label)

    def tap(self, x, y, why=""):
        self.taps += 1
        if not self.dry:
            B.tap(x, y)
        time.sleep(self.settle)
        return {"type": "tap", "x": x, "y": y, "why": why}

    def walk(self, direction="up", ms=8000):
        self.walks += 1
        before = B.grab() if self.sess else None
        act = B.walk(direction, ms, self.dry)
        self.record("map:walk", act, before)
        self.log(f"walk {direction} {ms}ms")
        time.sleep(1.5)

    def safe_state(self) -> str:
        st = L.state()
        if st == "raid":                       # R5
            self.log("raid sheet -> closing (R5)")
            if not self.dry:
                L.leave_raid()
            self.raids_closed += 1
            time.sleep(self.settle)
            return "raid"
        return st

    # ----------------------------------------------------------------- loop
    def pick_target(self):
        """One screenshot, used only to choose where to tap."""
        img = B.grab()
        pts = candidates(img, 18)
        best = None
        for v, x, y in pts:
            d = ((x - AVATAR[0]) ** 2 + (y - AVATAR[1]) ** 2) ** 0.5
            if not (AVATAR_CLEAR < d < 780):
                continue
            if y < 600:                        # too far up the map
                continue
            if 900 < x < 1060 and y > 1700:    # right-hand PGSharp column
                continue
            if x < 130 and 400 < y < 1300:     # left feed column
                continue
            if orange_ratio(img, x, y) > ORANGE_MAX:
                continue                       # PokéStop / pumpkin / leaves
            score = v - 0.5 * d
            if best is None or score > best[0]:
                best = (score, x, y)
        return best, img

    def run(self, budget_s: float, target: int) -> None:
        end = time.time() + budget_s
        misses = 0
        while time.time() < end and self.catches < target:
            st = self.safe_state()
            self.log(f"state={st} catches={self.catches} throws={self.throws}")

            if self.dry:
                return

            if st == "encounter":
                data = L.mon()
                self.log(f"  mon L{data.get('level')} IV{data.get('iv')} "
                         f"{data.get('split')} consistent={data.get('consistent')}")
                res = L.catch()
                self.throws += res.get("throws", 0)
                if res.get("caught"):
                    self.catches += 1
                    self.log(f"  CAUGHT in {res.get('throws')} throw(s) -> {res.get('mon')}")
                    self.record("catch:result", {"type": "caught", **res})
                else:
                    self.log(f"  not caught: {res}")
                misses = 0
                continue

            if st == "mon_detail":
                if not self.dry:
                    B.back()
                time.sleep(self.settle)
                continue

            if st == "pg_side_menu":
                m = L.menu_items()
                if "地圖" in m:
                    self.tap(*m["地圖"], why="close menu")
                continue

            if st in ("settings", "safety_dialog", "anr_dialog"):
                if not self.dry:
                    B.back()
                time.sleep(self.settle)
                continue

            # ---- on the map: pick a spawn, otherwise walk (proximity spins)
            best, img = self.pick_target()
            if best is None or misses >= MAX_MAP_TAPS:
                self.record("map:idle", {"type": "none"}, img)
                self.walk("up", 8000)
                misses = 0
                continue
            _, x, y = best
            self.record("map:target", {"type": "tap", "x": x, "y": y}, img)
            self.tap(x, y, why="spawn probe")
            misses += 1
        self.log(f"done: catches={self.catches} throws={self.throws} "
                 f"taps={self.taps} walks={self.walks} raids_closed={self.raids_closed}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catches", type=int, default=5)
    ap.add_argument("--minutes", type=float, default=20.0)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-record", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--settle", type=float, default=SETTLE)
    args = ap.parse_args()

    sess = None
    if not args.no_record:
        root = args.out or Path("tools/pgo_sessions") / ("run_" + time.strftime("%Y%m%d_%H%M%S"))
        root.mkdir(parents=True, exist_ok=True)
        sess = Session(root, {"serial": B.SERIAL, "policy": "layer_first",
                              "ball": DEFAULT_BALL, "target": args.catches,
                              "rules": describe()})
        print(f"[run] session {root}", flush=True)

    print(describe(), flush=True)
    r = Runner(sess, args.dry_run, args.settle)
    try:
        r.run(args.minutes * 60, args.catches)
    except KeyboardInterrupt:
        print("\n[run] interrupted", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
