"""Ground-truth from the device, used to validate what the bot *thinks* it sees.

The game's own analytics SDK (QUAGO-SDK) logs a clean state timeline:

    SegmentBegin Name = MapExplore
    SegmentBegin Name = Pokestop
    KeyValues for Segment Encounter = [EncounterResult,CapturedPokemon]
    KeyValues for Segment Encounter = [EncounterMode,Standard]

That is independent of our vision classifier, so comparing the two is a real
cross-check instead of us marking our own homework.

Usage:
    # capture 5 minutes of ground truth while the bot runs
    python tools/pgo_truth.py capture --seconds 300

    # compare a recorded session against a capture
    python tools/pgo_truth.py compare --session tools/pgo_sessions/<ts> \
                                      --log tools/verify/logcat_truth.log
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

SERIAL = "1bbd5689"
PKG = "com.nianticlabs.pokemongo"

RX_SEG_BEGIN = re.compile(r"SegmentBegin Name = (\w+)")
RX_SEG_END = re.compile(r"Segment ended")
RX_KV = re.compile(r"KeyValues for Segment (\w+) = \[([^,\]]+),([^\]]*)\]")
RX_EPOCH = re.compile(r"^\s*([0-9]{9,}\.[0-9]+)\s")


def adb(*args):
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True, text=True)
    return r.stdout.strip()


def phone_clock_offset() -> float:
    """phone_epoch - pc_epoch, so truth timestamps can be compared to time.time()."""
    dev = float(adb("shell", "date +%s.%N") or 0)
    pc = time.time()
    return dev - pc


def pid_of(pkg=PKG) -> str:
    return adb("shell", "pidof", pkg)


def parse(lines, offset: float):
    """Turn logcat lines into [(pc_epoch, kind, value)]."""
    out = []
    for line in lines:
        m = RX_EPOCH.match(line)
        if not m:
            continue
        t = float(m.group(1)) - offset
        kv = RX_KV.search(line)
        if kv:
            out.append((t, "kv", f"{kv.group(1)}:{kv.group(2)}={kv.group(3)}"))
            continue
        b = RX_SEG_BEGIN.search(line)
        if b:
            out.append((t, "segment", b.group(1)))
            continue
        if RX_SEG_END.search(line):
            out.append((t, "segment_end", ""))
    return out


def cmd_capture(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "logcat_truth.log"
    pid = pid_of()
    print(f"[truth] pid={pid} -> {log}", flush=True)
    offset = phone_clock_offset()
    (out / "clock_offset.json").write_text(json.dumps({"offset": offset}), encoding="utf-8")

    cmd = ["adb", "-s", SERIAL, "logcat", "-v", "epoch"]
    if pid:
        cmd.append(f"--pid={pid}")
    # start from "now" rather than replaying the whole buffer
    subprocess.run(["adb", "-s", SERIAL, "logcat", "-c"], capture_output=True)
    with log.open("w", encoding="utf-8", errors="replace") as fh:
        p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        try:
            time.sleep(args.seconds)
        finally:
            p.terminate()
            try:
                p.wait(timeout=5)
            except Exception:
                p.kill()
    print(f"[truth] captured {log.stat().st_size} bytes", flush=True)
    return 0


def cmd_compare(args):
    session = args.session
    log = Path(args.log)
    off_file = log.parent / "clock_offset.json"
    offset = 0.0
    if off_file.exists():
        offset = json.loads(off_file.read_text(encoding="utf-8"))["offset"]

    truth = parse(log.read_text(encoding="utf-8", errors="replace").splitlines(), offset)
    events = [json.loads(l) for l in (session / "events.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

    print(f"session events : {len(events)}  ({events[0]['t']:.0f} .. {events[-1]['t']:.0f})")
    print(f"truth entries  : {len(truth)}\n")

    catches = [t for t in truth if t[1] == "kv" and t[2].endswith("CapturedPokemon")]
    stops = [t for t in truth if t[1] == "segment" and t[2] == "Pokestop"]
    maps = [t for t in truth if t[1] == "segment" and t[2] == "MapExplore"]

    print(f"ground truth: catches={len(catches)} pokestops={len(stops)} map-returns={len(maps)}")
    for t, kind, val in catches:
        print(f"  caught @ {t:.1f}  {val}")

    # vision-reported catches
    vis = [e for e in events if e.get("screen") == "result" and e["action"].get("type") == "back"]
    print(f"\nvision said 'catch card -> BACK': {len(vis)} times")

    # align: for each vision catch, is there a ground-truth catch within +-30s?
    print("\nalignment (vision catch -> nearest ground truth catch):")
    for e in vis:
        if not catches:
            print(f"  event {e['i']:4d} @ {e['t']:.1f}  -> NO GROUND TRUTH")
            continue
        best = min(catches, key=lambda c: abs(c[0] - e["t"]))
        d = best[0] - e["t"]
        flag = "OK" if abs(d) <= 30 else "MISMATCH"
        print(f"  event {e['i']:4d} @ {e['t']:.1f}  -> catch @ {best[0]:.1f}  dt={d:+.1f}s  {flag}")

    # state timeline overlay
    print("\ntimeline (truth vs vision):")
    merged = sorted([(t, "TRUTH", f"{k}:{v}") for t, k, v in truth] +
                    [(e["t"], "VISION", e.get("screen", "")) for e in events])
    t0 = merged[0][0] if merged else 0
    for t, src, msg in merged[:120]:
        print(f"  {t - t0:8.1f}s {src:6s} {msg}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("--seconds", type=int, default=300)
    c.add_argument("--out", default="tools/verify")
    c.set_defaults(func=cmd_capture)
    m = sub.add_parser("compare")
    m.add_argument("--session", type=Path, required=True)
    m.add_argument("--log", default="tools/verify/logcat_truth.log")
    m.set_defaults(func=cmd_compare)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
