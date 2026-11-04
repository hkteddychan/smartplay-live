"""Record the game *controls* as imitation-learning data.

The bot's job is not only to catch, it is also to demonstrate every control
the game exposes (walk, turn, tilt, zoom in/out, click, feed navigation), so
that a policy can later be trained on `frames -> action` pairs.

Every step stores the frame *before* the action together with the action that
was executed, which is exactly the (observation, action) pair a behavioural
clone needs.

Usage:
    python tools/pgo_control.py --rounds 12
    python tools/pgo_control.py --rounds 12 --out tools/pgo_sessions/ctrl
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
from pgo_record import Session


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=12)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    root = args.out or Path("tools/pgo_sessions") / ("ctrl_" + time.strftime("%Y%m%d_%H%M%S"))
    root.mkdir(parents=True, exist_ok=True)
    sess = Session(root, {"serial": B.SERIAL, "policy": "control_primitives",
                           "rounds": args.rounds, "seed": args.seed})
    print(f"[control] session {root}", flush=True)

    def record(img, label, action):
        small = img.resize((img.width // 2, img.height // 2))
        sess.record(img, small, action, 1.0, label)

    # curriculum: the game exposes these controls in this order
    curriculum = [
        ("walk_up",    lambda: B.walk("up", 2500, args.dry_run)),
        ("walk_down",  lambda: B.walk("down", 2000, args.dry_run)),
        ("walk_left",  lambda: B.walk("left", 2000, args.dry_run)),
        ("walk_right", lambda: B.walk("right", 2000, args.dry_run)),
        ("turn_left",  lambda: B.turn("left", 600, args.dry_run)),
        ("turn_right", lambda: B.turn("right", 600, args.dry_run)),
        ("tilt_up",    lambda: B.tilt("up", 600, args.dry_run)),
        ("tilt_down",  lambda: B.tilt("down", 600, args.dry_run)),
        ("zoom_in",    lambda: B.zoom_in(args.dry_run)),
        ("zoom_out",   lambda: B.zoom_out(args.dry_run)),
    ]

    for r in range(args.rounds):
        for name, fn in curriculum:
            B.goto_map(dry=args.dry_run)
            img = B.grab()
            action = fn()
            record(img, name, action)
            time.sleep(0.6)
            after = B.grab()
            record(after, f"{name}:after", {"type": "none"})
            print(f"[{r + 1}/{args.rounds}] {name}", flush=True)

            # one random click somewhere on the map, to learn click->consequence
        B.goto_map(dry=args.dry_run)
        if not B.ensure_not_raid(args.dry_run):
            print(f"[{r + 1}/{args.rounds}] raid sheet closed (R5), skipping click")
            continue
        img = B.grab()
        x = rng.randint(150, 900)
        y = rng.randint(500, 1700)
        action = {"type": "tap", "x": x, "y": y}
        if not args.dry_run:
            B.tap(x, y)
            time.sleep(2.0)
        record(img, "random_click", action)
        print(f"[{r + 1}/{args.rounds}] random_click({x},{y})", flush=True)

    print(f"[control] done -> {root}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
