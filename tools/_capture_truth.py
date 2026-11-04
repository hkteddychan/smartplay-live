"""Capture adb-side ground truth (kernel touch events + logcat) without shell quoting issues.

Usage:
    python tools/_capture_truth.py --seconds 240
"""
import argparse
import subprocess
import sys
import threading
from pathlib import Path

SERIAL = "1bbd5689"
OUT = Path("tools/verify")


def run(cmd, out_path: Path):
    with out_path.open("wb") as fh:
        p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        p.wait()
    print(f"[capture] {out_path} {out_path.stat().st_size} bytes", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=int, default=240)
    ap.add_argument("--serial", default=SERIAL)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    pid = subprocess.run(["adb", "-s", args.serial, "shell", "pidof", "com.nianticlabs.pokemongo"],
                         capture_output=True, text=True).stdout.strip()
    print(f"[capture] game pid = {pid!r}", flush=True)

    ev = OUT / "getevent.log"
    lc = OUT / "logcat.log"

    t1 = threading.Thread(target=run, args=(
        ["adb", "-s", args.serial, "shell", "timeout", str(args.seconds),
         "getevent", "-lt", "/dev/input/event2"], ev))
    t1.start()

    if pid:
        t2 = threading.Thread(target=run, args=(
            ["adb", "-s", args.serial, "logcat", "-v", "threadtime", f"--pid={pid}"], lc))
        t2.start()
        # logcat has no natural timeout; let getevent's duration bound the run
        t1.join()
        subprocess.run(["adb", "-s", args.serial, "shell", "pkill", "-f", "logcat"], capture_output=True)
        t2.join(timeout=5)
    else:
        t1.join()
    print("[capture] done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
