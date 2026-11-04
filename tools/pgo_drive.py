"""Talk to the layer-level driver APK (com.opencode.pgodrive).

    python tools/pgo_drive.py ping
    python tools/pgo_drive.py dump
    python tools/pgo_drive.py click_text 設置
    python tools/pgo_drive.py click 540 1000
    python tools/pgo_drive.py swipe 840 1150 320 1150 600
"""
from __future__ import annotations

import subprocess
import sys
import time

SERIAL = "1bbd5689"
BASE = "/sdcard/Android/data/com.opencode.pgodrive/files"
CMD = BASE + "/cmd.txt"
OUT = BASE + "/out.txt"
BUSY = BASE + "/busy"


def sh(cmd: str) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True)
    return r.stdout


def send(command: str, timeout: float = 20.0) -> str:
    sh(f"rm -f {OUT}")
    sh(f"printf '%s' '{command}' > {CMD}")
    t0 = time.time()
    while time.time() - t0 < timeout:
        out = sh(f"cat {OUT} 2>/dev/null")
        if out and out.strip():
            return out.rstrip("\r\n")
        time.sleep(0.05)
    return "TIMEOUT"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = " ".join(sys.argv[1:])
    out = send(cmd)
    print(out)
    return 0 if out.startswith("OK") else 1


if __name__ == "__main__":
    raise SystemExit(main())
