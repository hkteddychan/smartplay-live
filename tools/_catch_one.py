"""Catch whatever is currently in front of the camera, recorded as ML data.

    python tools/_catch_one.py            # record + throw
    python tools/_catch_one.py --dry-run  # record only

Throws with the verified 120 ms flick using 精靈球 only (R1).  Ground truth
(L / IV / split) is read from the layer tree, not guessed from pixels.
Rule checks come from pgo_rules, so a banned ball can never be thrown.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
from pgo_record import Session
from pgo_rules import assert_ball_allowed, describe as describe_rules


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    root = args.out or Path("tools/pgo_sessions") / ("catch_" + time.strftime("%Y%m%d_%H%M%S"))
    root.mkdir(parents=True, exist_ok=True)
    sess = Session(root, {"serial": B.SERIAL, "policy": "single_catch",
                          "ball": B.DEFAULT_BALL, "rules": describe_rules()})
    print(f"[catch] session {root}")
    print(describe_rules())

    img = B.grab()
    st = B.screen_state(img)
    print(f"[catch] state={st} red={B.red_bottom(img)} white={B.white_ratio(img):.3f}")
    if st != "encounter":
        print("[catch] not in an encounter; aborting")
        return 1

    data = B.read_mon_data()
    print(f"[catch] mon={data}")

    ball = assert_ball_allowed(B.DEFAULT_BALL)   # R1 guard

    for attempt in range(1, 7):
        before = B.grab()
        small = before.resize((before.width // 2, before.height // 2))
        action = B.throw_ball() if not args.dry_run else {
            "type": "throw", "ball": ball, "ms": 120}
        action["ball"] = ball
        sess.record(before, small, action, 1.0, f"encounter:throw{attempt}")
        print(f"[catch] throw {attempt} ball={ball}")

        deadline = time.time() + 15
        while time.time() < deadline:
            time.sleep(0.8)
            img2 = B.grab()
            st2 = B.screen_state(img2)
            if st2 == "result":
                sess.record(img2, img2.resize((img2.width // 2, img2.height // 2)),
                            {"type": "tap", "x": 540, "y": 700}, 1.0, "result:caught")
                print(f"[catch] CAUGHT {data}")
                if not args.dry_run:
                    B.back()
                    time.sleep(1.5)
                print(f"[catch] events -> {sess.events}")
                return 0
            if st2 == "encounter":
                print(f"[catch] broke free (red={B.red_bottom(img2)})")
                break
            if B.red_bottom(img2) < 2000 and B.white_ratio(img2) > 0.2:
                sess.record(img2, img2.resize((img2.width // 2, img2.height // 2)),
                            {"type": "none"}, 1.0, "encounter:fled")
                print("[catch] FLED")
                return 1
        else:
            print("[catch] timeout waiting for result")
            return 1
    print("[catch] out of attempts")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
