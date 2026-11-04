"""Try every non-root avenue to enable a locked PGSharp switch, and report.

    python tools/pgo_unlock.py 虛擬 Go Plus
    python tools/pgo_unlock.py --scan          # look for a licence/activation row

Context
-------
Four rows (快速捕捉 / 跳過過場動畫 / 擴大遭遇範圍 / 虛擬 Go Plus) ignore
ACTION_CLICK and injected taps while other rows (禮品助理, 冷卻計時器) toggle
normally on the same panel, at the same moment.  They are also drawn grey.
That points at a feature gate, not at our input path.

This script tests, in order, everything available to an unrooted `adb shell`:

  1. accessibility ACTION_CLICK on the switch          (already known: no-op)
  2. accessibility ACTION_CLICK twice (some skins need a pair)
  3. `settings put` system rows                        (wrong namespace)
  4. direct write to the app's shared_prefs            (expect EACCES)
  5. `run-as <pkg>`                                    (only debuggable apps)
  6. `su -c`                                           (no root on this device)

Each step prints what actually happened, so the blocker is demonstrated rather
than assumed.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_layer as L

PKGS = ["com.nianticlabs.pokemongo", "com.pgsharp.pgsharp"]


def sh(cmd: str) -> str:
    r = subprocess.run(["adb", "-s", L.SERIAL, "shell", cmd],
                       capture_output=True, text=True)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    return out if out else f"<empty> {err}".strip()


def switch_state(label: str):
    ns = L.nodes()
    labels = [n for n in ns if n["cls"] == "TextView" and n["text"] and n["l"] < 70]
    for s in (n for n in ns if n["cls"] == "Switch"):
        cy = (s["t"] + s["b"]) // 2
        near = [lb for lb in labels if abs((lb["t"] + lb["b"]) // 2 - cy) <= 40]
        if not near:
            continue
        lb = min(near, key=lambda d: abs((d["t"] + d["b"]) // 2 - cy))
        if lb["text"] == label:
            return "X" in s["flags"], (s["l"] + s["r"]) // 2, cy
    return None, 0, 0


def scan_licence() -> None:
    """Print any row that looks like activation / licence / expiry."""
    ns = L.nodes()
    keys = ("授權", "激活", "啟用", "登入", "帳號", "到期", "會員", "版本",
            "licen", "activ", "premium", "vip", "trial", "expire")
    print("nodes that look like licence / status rows:")
    for n in ns:
        blob = f"{n['text']} {n['desc']}".lower()
        if any(k.lower() in blob for k in keys):
            print(f"  {n['cls']:<14} text={n['text']!r:<24} "
                  f"desc={n['desc']!r:<18} box=({n['l']},{n['t']},{n['r']},{n['b']})")


def main() -> int:
    if "--scan" in sys.argv:
        scan_licence()
        return 0

    label = sys.argv[1] if len(sys.argv) > 1 else "虛擬 Go Plus"
    if L.state() != "settings":
        print(f"open 設置 first (state={L.state()})")
        return 1

    checked, cx, cy = switch_state(label)
    if checked is None:
        print(f"row not visible: {label}")
        return 1
    print(f"{label}: {'On' if checked else 'Off'} at ({cx},{cy})")

    print("\n[1] accessibility ACTION_CLICK")
    print("   ", L.toggle(label))
    time.sleep(1.0)
    print("    now:", "On" if switch_state(label)[0] else "Off")

    print("\n[2] ACTION_CLICK x2")
    L.toggle(label)
    time.sleep(0.4)
    L.toggle(label)
    time.sleep(1.0)
    print("    now:", "On" if switch_state(label)[0] else "Off")

    print("\n[3] settings put (system namespace — wrong place for app prefs)")
    print("   ", sh("settings put global pgsharp_virtual_goplus 1"))
    print("   ", sh("settings get global pgsharp_virtual_goplus"))

    for pkg in PKGS:
        print(f"\n[4] write shared_prefs of {pkg}")
        print("   ", sh(f"ls /data/data/{pkg}/shared_prefs 2>&1 | head -5"))
        print("   ", sh(f"cat /data/data/{pkg}/shared_prefs/*.xml 2>&1 | head -3"))
        print(f"[5] run-as {pkg}")
        print("   ", sh(f"run-as {pkg} id 2>&1"))

    print("\n[6] su")
    print("   ", sh("su -c id 2>&1"))

    print("\nresult:",
          "ENABLED" if switch_state(label)[0] else "STILL OFF (blocked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
