"""Ensure 快速狙擊 I / II and 冷卻計時器 are OFF, then snapshot settings.

    python tools/_safe_settings.py

Sniping teleports the avatar and is a ban vector (user directive 2026-11-02),
so this both verifies and forces them off, then writes the settings snapshot
used by stop_status().
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_direct as D
import pgo_layer as L

MUST_BE_OFF = ("快速狙擊 I", "快速狙擊 II", "冷卻計時器")


def main() -> int:
    D.back_to_map()
    if not D.open_menu():
        print("cannot open menu")
        return 1
    m = L.menu_items()
    L.click_node("設置")
    time.sleep(3.0)
    if L.state() != "settings":
        print("settings did not open:", L.state())
        return 1

    sw = L.switches()
    print("current:", {k: sw.get(k) for k in MUST_BE_OFF})
    for k in MUST_BE_OFF:
        if sw.get(k):
            print(f"forcing OFF: {k} -> {L.toggle(k)}")
            time.sleep(1.5)
    sw = L.switches()
    ok = all(not sw.get(k) for k in MUST_BE_OFF)
    print("after  :", {k: sw.get(k) for k in MUST_BE_OFF}, "SAFE" if ok else "UNSAFE")

    snap = {
        "t": round(time.time(), 3),
        "toggles": sw,
        "values": list(L.values().keys()),
        "sniping_disabled": ok,
    }
    L.SETTINGS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    L.SETTINGS_CACHE.write_text(json.dumps(snap, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    print(f"snapshot -> {L.SETTINGS_CACHE}")

    L.click_node("確定")
    time.sleep(2.0)
    D.back_to_map()
    print("state:", L.state())
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
