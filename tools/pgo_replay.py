"""Replay a recorded PGO session straight over adb (fast path, no vision).

The recorder writes events.jsonl; this replays the actions in order, so a
recorded routine can be re-run at full speed without any template matching.
Useful for A/B testing a new policy, and for "fast repeat" loops in the
competition.

Usage:
    python tools/pgo_replay.py tools/pgo_sessions/<ts> --speed 1.0
    python tools/pgo_replay.py tools/pgo_sessions/<ts> --only screen=encounter
    python tools/pgo_replay.py tools/pgo_sessions/<ts> --dry-run
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path

SERIAL_DEFAULT = "1bbd5689"


def adb(serial, *args):
    r = subprocess.run(["adb", "-s", serial, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())


def exec_action(serial, action: dict) -> None:
    t = action.get("type", "none")
    if t == "tap":
        adb(serial, "shell", "input", "tap", str(action["x"]), str(action["y"]))
    elif t == "swipe":
        adb(serial, "shell", "input", "swipe", str(action["x1"]), str(action["y1"]),
            str(action["x2"]), str(action["y2"]), str(action.get("ms", 200)))
    elif t == "none":
        return
    else:
        raise ValueError(t)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session", type=Path)
    ap.add_argument("--serial", default=SERIAL_DEFAULT)
    ap.add_argument("--speed", type=float, default=1.0, help=">1 = faster than recorded")
    ap.add_argument("--delay", type=float, default=0.45, help="gap between actions (s)")
    ap.add_argument("--only", default=None, help="filter: key=value (e.g. screen=encounter)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    events = [json.loads(l) for l in (args.session / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        k, v = args.only.split("=", 1)
        events = [e for e in events if str(e.get(k)) == v]
    print(f"[replay] {len(events)} events from {args.session}")

    prev_t = None
    for e in events:
        gap = 0.0
        if prev_t is not None:
            gap = max(0.0, (e["t"] - prev_t) / max(args.speed, 0.01))
        prev_t = e["t"]
        a = e["action"]
        print(f"  [{e['i']:4d}] {e.get('screen','?'):10s} {a} gap={gap:.2f}s")
        if not args.dry_run:
            exec_action(args.serial, a)
            time.sleep(gap if gap else args.delay)
        else:
            time.sleep(0.0)
    print("[replay] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
