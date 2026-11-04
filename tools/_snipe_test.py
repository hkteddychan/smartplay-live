"""Does the nearby list open an encounter once 快速狙擊 is enabled?

    python tools/_snipe_test.py

Steps (all layer-driven, no coordinates except the floating star):
  1. map -> menu -> settings
  2. read 快速狙擊 I / 冷卻計時器 state, enable both, verify
  3. close settings, back to map
  4. index_click the N-th nearby entry, poll the layer for 12 s
  5. report every state transition; if an encounter opens, read mon() and back out
     (we deliberately do NOT throw: a snipe teleport may still be cooling down)
  6. restore both toggles to their original values
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_direct as D
import pgo_layer as L

SETTLE = 2.5
WANT = ("快速狙擊 I", "冷卻計時器")


def ensure_toggle(label: str, on: bool) -> bool:
    cur = L.switches().get(label)
    if cur is None:
        print(f"  ! {label} not readable")
        return False
    if cur == on:
        print(f"  = {label} already {'On' if on else 'Off'}")
        return True
    print(f"  toggling {label}: {cur} -> {on}  {L.toggle(label)}")
    time.sleep(1.5)
    now = L.switches().get(label)
    print(f"  -> {label} = {now}")
    return now == on


def main() -> int:
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    print("== snipe test ==")
    D.back_to_map()
    if not D.open_menu():
        print("cannot open menu")
        return 1
    m = L.menu_items()
    print("menu:", list(m))
    L.click_node("設置")
    time.sleep(3.0)
    if L.state() != "settings":
        print("settings did not open, state=", L.state())
        return 1

    before = {w: L.switches().get(w) for w in WANT}
    print("before:", before)
    for w in WANT:
        ensure_toggle(w, True)

    L.click_node("確定")
    time.sleep(2.5)
    D.back_to_map()
    print("state after settings:", L.state())

    cbs = L.clickables(130)
    print(f"nearby entries: {len(cbs)} -> clicking #{idx}")
    print("  ", L.index_click(idx))

    t0 = time.time()
    last = None
    seen = []
    while time.time() - t0 < 12:
        st = L.state()
        if st != last:
            seen.append((round(time.time() - t0, 1), st))
            print(f"  t={time.time() - t0:5.1f}s  state={st}")
            last = st
        time.sleep(0.4)

    if L.state() == "encounter":
        print("  mon:", L.mon())
        print("  backing out WITHOUT throwing (cooldown safety)")
        B.back()
        time.sleep(2.5)

    print("transitions:", seen)

    # restore
    D.back_to_map()
    D.open_menu()
    L.click_node("設置")
    time.sleep(3.0)
    if L.state() == "settings":
        for w in WANT:
            ensure_toggle(w, bool(before.get(w)))
        L.click_node("確定")
        time.sleep(2.0)
    D.back_to_map()
    print("final state:", L.state())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
