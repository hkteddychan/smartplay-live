"""Review a recorded PGO session: state stats, action mix, and a contact sheet.

Usage:
    python tools/pgo_review.py tools/pgo_sessions/<ts>
    python tools/pgo_review.py tools/pgo_sessions/<ts> --sheet
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from PIL import Image, ImageDraw


def load(session: Path):
    ev = session / "events.jsonl"
    events = [json.loads(l) for l in ev.read_text(encoding="utf-8").splitlines() if l.strip()]
    meta = json.loads((session / "meta.json").read_text(encoding="utf-8"))
    return events, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session", type=Path)
    ap.add_argument("--sheet", action="store_true", help="build frames_sheet.png")
    ap.add_argument("--cols", type=int, default=8)
    args = ap.parse_args()

    events, meta = load(args.session)
    if not events:
        print("no events")
        return 1

    dur = events[-1]["t"] - events[0]["t"]
    states = Counter(e.get("screen", "?") for e in events)
    acts = Counter(e["action"].get("type", "?") for e in events)

    # a catch = a "result" state followed by a back action
    catches = sum(1 for e in events
                  if e.get("screen") == "result" and e["action"].get("type") == "back")
    throws = sum(1 for e in events
                 if e["action"].get("type") == "swipe")
    taps = sum(1 for e in events if e["action"].get("type") == "tap")

    print(f"session : {args.session}")
    print(f"events  : {len(events)}   duration: {dur / 60:.1f} min")
    print(f"catches : {catches}   throws: {throws}   taps: {taps}")
    if dur > 0:
        print(f"rate    : {catches / (dur / 3600):.1f} catches/hour")
    print("\nstates  :", dict(states))
    print("actions :", dict(acts))
    print("\nmeta    :", json.dumps({k: v for k, v in meta.items()
                                     if k not in ("grid_x", "grid_y")}, ensure_ascii=False))

    if args.sheet:
        cols = args.cols
        rows = (len(events) + cols - 1) // cols
        tw, th = 180, 360
        sheet = Image.new("RGB", (cols * tw, rows * (th + 16)), (20, 20, 20))
        d = ImageDraw.Draw(sheet)
        for i, e in enumerate(events):
            p = args.session / e["frame_small"]
            if not p.exists():
                continue
            im = Image.open(p).convert("RGB").resize((tw, th))
            x, y = (i % cols) * tw, (i // cols) * (th + 16)
            sheet.paste(im, (x, y))
            a = e["action"]
            lbl = a.get("type", "?")[0].upper() + (f" {a.get('x')},{a.get('y')}" if a.get("x") else "")
            d.text((x + 3, y + th + 2), f"{e['i']} {e.get('screen', '')[:4]} {lbl}", fill=(220, 220, 220))
        out = args.session / "frames_sheet.png"
        sheet.save(out)
        print(f"\nsheet   : {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
