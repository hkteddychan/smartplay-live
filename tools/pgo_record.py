"""PGO action recorder -> ML dataset.

Every loop iteration captures a frame, asks a policy what to do, appends the
(frame, action) pair to events.jsonl and executes the action over adb.

Layout of a session:
    tools/pgo_sessions/<ts>/
        frames/000000.png     full-res frame per decision
        frames_small/000000.png   1/2-scale frame (cheap training input)
        events.jsonl          one JSON record per action
        meta.json             device / screen / policy info

Usage:
    python tools/pgo_record.py --template throw:tpl.png --action tap --count 50
    python tools/pgo_record.py --template map_ball:tpl.png --action tap --region 400 1900 300 250
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image

from pgo_throw import best_match  # NCC template matcher

SERIAL_DEFAULT = "1bbd5689"


# --------------------------------------------------------------------- adb io

def adb(serial, *args, binary=False):
    cmd = ["adb"]
    if serial:
        cmd += ["-s", serial]
    cmd += list(args)
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def grab(serial) -> Image.Image:
    data = adb(serial, "exec-out", "screencap", "-p", binary=True)
    return Image.open(io.BytesIO(data)).convert("RGB")


def act(serial, action: dict) -> None:
    t = action["type"]
    if t == "tap":
        adb(serial, "shell", "input", "tap", str(action["x"]), str(action["y"]))
    elif t == "swipe":
        adb(serial, "shell", "input", "swipe", str(action["x1"]), str(action["y1"]),
            str(action["x2"]), str(action["y2"]), str(action.get("ms", 200)))
    elif t == "none":
        pass
    else:
        raise ValueError(f"unknown action type {t}")


# -------------------------------------------------------------------- session

class Session:
    def __init__(self, root: Path, meta: dict):
        self.root = root
        (root / "frames").mkdir(parents=True, exist_ok=True)
        (root / "frames_small").mkdir(parents=True, exist_ok=True)
        self.events = root / "events.jsonl"
        (root / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        self.n = 0

    def record(self, frame: Image.Image, small: Image.Image, action: dict, score: float,
               label: str) -> dict:
        idx = self.n
        self.n += 1
        fname = f"{idx:06d}.png"
        frame.save(self.root / "frames" / fname)
        small.save(self.root / "frames_small" / fname)
        rec = {
            "i": idx,
            "t": round(time.time(), 3),
            "frame": f"frames/{fname}",
            "frame_small": f"frames_small/{fname}",
            "screen": label,
            "action": action,
            "score": round(float(score), 4),
        }
        with self.events.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


# --------------------------------------------------------------------- policy

class TemplatePolicy:
    """Match one or more templates; act on the best scoring hit."""

    def __init__(self, templates, threshold=0.8, scale=0.5, region=None):
        self.templates = templates   # list of dicts: {name, path, action}
        self.threshold = threshold
        self.scale = scale
        self.region = region

    def step(self, img: Image.Image):
        gray = np.asarray(img.convert("L"), dtype=np.float64)
        small = np.asarray(img.convert("L").resize(
            (int(img.width * self.scale), int(img.height * self.scale))), dtype=np.float64)
        best = (-1.0, None, None, None, None)
        for spec in self.templates:
            tpl = Image.open(spec["path"]).convert("L")
            ts = tpl.resize((max(8, int(tpl.width * self.scale)),
                             max(8, int(tpl.height * self.scale))), Image.BILINEAR)
            tpl_small = np.asarray(ts, dtype=np.float64)
            if self.region:
                rx, ry, rw, rh = self.region
                sx0, sy0 = int(rx * self.scale), int(ry * self.scale)
                sub = small[sy0:sy0 + int(rh * self.scale), sx0:sx0 + int(rw * self.scale)]
                score, x, y, w, h = best_match(sub, tpl_small, (1.0,))
                x += sx0
                y += sy0
            else:
                score, x, y, w, h = best_match(small, tpl_small, (1.0,))
            if score > best[0]:
                best = (score, spec, x, y, w, h)
        score, spec, x, y, w, h = best
        if spec is None or score < self.threshold:
            return None, score, "none"
        cx = int((x + w / 2) / self.scale)
        cy = int((y + h / 2) / self.scale)
        action = dict(spec["action"])
        action.update({"type": action.get("type", "tap"), "x": cx, "y": cy})
        return action, score, spec["name"]


# ----------------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default=SERIAL_DEFAULT)
    ap.add_argument("--template", action="append", default=[],
                    help="name:path[:action]  (action: tap|swipe)")
    ap.add_argument("--region", nargs=4, type=int, default=None, metavar=("X", "Y", "W", "H"))
    ap.add_argument("--threshold", type=float, default=0.80)
    ap.add_argument("--scale", type=float, default=0.5)
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--interval", type=float, default=1.2)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--no-exec", action="store_true", help="record only, do not touch the phone")
    args = ap.parse_args()

    specs = []
    for raw in args.template:
        parts = raw.split(":")
        name, path = parts[0], parts[1]
        atype = parts[2] if len(parts) > 2 else "tap"
        specs.append({"name": name, "path": path, "action": {"type": atype}})
    if not specs:
        ap.error("need at least one --template name:path[:action]")

    root = args.out or Path("tools/pgo_sessions") / time.strftime("%Y%m%d_%H%M%S")
    root.mkdir(parents=True, exist_ok=True)
    sess = Session(root, {"serial": args.serial, "templates": specs,
                           "threshold": args.threshold, "region": args.region,
                           "interval": args.interval})

    policy = TemplatePolicy(specs, args.threshold, args.scale, args.region)
    print(f"[record] session {root}")

    for i in range(args.count):
        img = grab(args.serial)
        small = img.resize((img.width // 2, img.height // 2))
        action, score, label = policy.step(img)
        if action is None:
            action = {"type": "none"}
        rec = sess.record(img, small, action, score, label)
        print(f"[{i}] {label} score={score:.3f} action={action}")
        if not args.no_exec and action["type"] != "none":
            act(args.serial, action)
            time.sleep(0.45)
        if i + 1 < args.count:
            time.sleep(args.interval)

    print(f"[record] done -> {root / 'events.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
