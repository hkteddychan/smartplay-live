"""Throw once and poll the *layer* (no screenshots) to see the state transitions.

    python tools/_throw_poll.py            # throw with the verified 120 ms flick
    python tools/_throw_poll.py --no-throw # only poll

Prints one line per state change, so we can tell whether the catch flow is
observable from the data layer alone.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_layer as L
from pgo_rules import DEFAULT_BALL, assert_ball_allowed


def main() -> int:
    ball = assert_ball_allowed(DEFAULT_BALL)
    print(f"ball={ball}")
    if "--no-throw" not in sys.argv:
        print("throw: swipe 540,1990 -> 540,1000 in 120 ms")
        B.swipe(540, 1990, 540, 1000, 120)

    last = None
    t0 = time.time()
    while time.time() - t0 < 22:
        st = L.state()
        if st != last:
            print(f"  t={time.time() - t0:5.1f}s  layer={st}")
            last = st
        time.sleep(0.4)
    print(f"final layer state = {L.state()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
