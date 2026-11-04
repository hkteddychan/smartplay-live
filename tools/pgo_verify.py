"""Cross-check recorded intents against ground truth from adb.

Two independent sources of truth:

1. `getevent -lt /dev/input/event2`  -> what the kernel actually received
   (real DOWN/MOVE/UP, real coordinates, real gesture duration).
2. the session's frames             -> what the screen actually did
   (mean absolute pixel delta between consecutive decisions).

Usage:
    python tools/pgo_verify.py --session tools/pgo_sessions/<ts> \
                               --getevent tools/verify/getevent.log
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from PIL import Image

LINE = re.compile(r"^\[\s*([0-9.]+)\]\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)\s+(-?\d+)")


def parse_getevent(path: Path):
    """Return a list of gestures: dict(t0, t1, dur_ms, x0, y0, x1, y1, moves, path_px)."""
    gestures = []
    cur = None
    slot = 0
    x = y = None
    last_syn = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        t = float(m.group(1))
        typ, code, val = m.group(2), m.group(3), int(m.group(5))
        if typ == "EV_ABS":
            if code == "ABS_MT_SLOT":
                slot = val
            elif code == "ABS_MT_TRACKING_ID":
                if val == -1 or val == 4294967295:
                    if cur is not None:
                        cur["t1"] = t
                        cur["dur_ms"] = round((t - cur["t0"]) * 1000, 1)
                        gestures.append(cur)
                        cur = None
                        x = y = None
                else:
                    cur = {"t0": t, "x0": None, "y0": None, "x1": None, "y1": None,
                           "moves": 0, "path_px": 0.0}
            elif code == "ABS_MT_POSITION_X":
                x = val
                if cur is not None:
                    if cur["x0"] is None:
                        cur["x0"] = x
                    if cur["x1"] is not None:
                        cur["path_px"] += abs(x - cur["x1"])
                    cur["x1"] = x
            elif code == "ABS_MT_POSITION_Y":
                y = val
                if cur is not None:
                    if cur["y0"] is None:
                        cur["y0"] = y
                    cur["y1"] = y
        elif typ == "EV_SYN" and code == "SYN_REPORT":
            if cur is not None and x is not None and y is not None:
                cur["moves"] += 1
                last_syn = t
    return gestures


def load_actions(session: Path):
    ev = session / "events.jsonl"
    out = []
    for line in ev.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        a = e.get("action", {})
        if a.get("type") in ("tap", "swipe"):
            out.append((e["i"], e.get("screen"), a))
    return out


def frame_deltas(session: Path, events):
    """Mean absolute pixel delta between consecutive recorded frames."""
    prev = None
    rows = []
    for e in events:
        p = session / e["frame_small"]
        if not p.exists():
            continue
        im = np.asarray(Image.open(p).convert("L"), dtype=np.int16)
        if prev is not None and prev.shape == im.shape:
            rows.append((e["i"], e.get("screen"), float(np.abs(im - prev).mean())))
        prev = im
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--session", type=Path, required=True)
    ap.add_argument("--getevent", type=Path, default=Path("tools/verify/getevent.log"))
    ap.add_argument("--tolerance-px", type=int, default=25)
    ap.add_argument("--tolerance-ms", type=float, default=150)
    args = ap.parse_args()

    acts = load_actions(args.session)
    gestures = parse_getevent(args.getevent) if args.getevent.exists() else []

    print(f"recorded actions : {len(acts)}")
    print(f"kernel gestures  : {len(gestures)}\n")

    n = min(len(acts), len(gestures))
    ok = bad = 0
    print(f"{'#':>4} {'screen':10s} {'intent':28s} {'kernel':30s} {'dur ms':>9}  verdict")
    print("-" * 100)
    for k in range(n):
        idx, screen, a = acts[k]
        g = gestures[k]
        if a["type"] == "tap":
            ex, ey = a["x"], a["y"]
            dx, dy = (g["x0"] or 0) - ex, (g["y0"] or 0) - ey
            intent = f"tap ({ex},{ey})"
        else:
            ex, ey = a["x2"], a["y2"]
            dx, dy = (g["x1"] or 0) - ex, (g["y1"] or 0) - ey
            intent = f"swipe ({a['x1']},{a['y1']})->({ex},{ey}) {a.get('ms')}ms"
        actual = f"({g['x0']},{g['y0']})->({g['x1']},{g['y1']}) mv={g['moves']}"
        dist = (dx * dx + dy * dy) ** 0.5
        exp_ms = a.get("ms") if a["type"] == "swipe" else 0
        dms = abs((g.get("dur_ms") or 0) - (exp_ms or 0))
        good = dist <= args.tolerance_px and dms <= args.tolerance_ms
        ok += good
        bad += not good
        print(f"{idx:>4} {str(screen):10s} {intent:28s} {actual:30s} "
              f"{g.get('dur_ms'):>9}  {'OK' if good else f'MISMATCH d={dist:.0f}px dt={dms:.0f}ms'}")

    print(f"\nmatch: {ok}/{n}   mismatch: {bad}")

    if gestures:
        durs = [g["dur_ms"] for g in gestures if g.get("dur_ms") is not None]
        print(f"kernel gesture duration: min={min(durs):.0f}ms max={max(durs):.0f}ms "
              f"mean={sum(durs) / len(durs):.0f}ms")

    # frame deltas
    events = [json.loads(l) for l in (args.session / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = frame_deltas(args.session, events)
    if rows:
        print("\nframe delta (mean abs diff of 1/2-scale frames, 0-255):")
        for i, screen, d in rows[:40]:
            bar = "#" * min(40, int(d / 2))
            print(f"  {i:>4} {str(screen):10s} {d:6.2f} {bar}")
        vals = [d for _, _, d in rows]
        print(f"  n={len(vals)} mean={np.mean(vals):.1f} max={np.max(vals):.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
