"""Drive PGSharp from layer *labels*, not coordinates.

    python tools/pgo_direct.py demo
    python tools/pgo_direct.py clicknode 設置
    python tools/pgo_direct.py toggle 快速旋轉
    python tools/pgo_direct.py info 虛擬定位

Everything here is resolved from the accessibility tree:
  info <label>       -> clickable / checkable / checked / bounds as data
  clicknode <label>  -> ACTION_CLICK on the clickable ancestor of <label>
  toggle <label>     -> ACTION_CLICK on the Switch that owns <label>
                        (works for rows scrolled off-screen, where a
                         coordinate tap is physically impossible)

`demo` walks menu -> settings -> toggle -> revert -> close and asserts every
transition from the layer, printing PASS/FAIL per step.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_layer as L

SETTLE = 2.5


def _ok(cond, msg):
    print(f"{'PASS' if cond else 'FAIL'}  {msg}")
    return bool(cond)


def back_to_map(steps: int = 10) -> bool:
    """Reach the map from anywhere.

    The map viewer keeps the side-menu labels in the tree, so it reports as
    `pg_side_menu`; its close X is at (987,130).
    """
    viewer_x = (987, 130)
    for i in range(steps):
        st = L.state()
        if st == "map":
            # The tree cannot see Unity overlays (PokéStop disc, gym sheet), so
            # confirm with the pixel probe before declaring victory.
            if L.probe().get("overlay"):
                B.back()
                time.sleep(SETTLE)
                continue
            return True
        if st == "anr_dialog":
            # Never "關閉應用程式": that kills the game and the session.
            L.click_node("等一下")
        elif st == "pg_side_menu":
            if i % 2 == 0:
                B.tap(*L.STAR)          # close the floating menu
            else:
                B.tap(*viewer_x)        # close the map viewer
        elif st == "settings":
            L.click_node("確定")
        else:
            B.back()
        time.sleep(SETTLE)
    return L.state() == "map"


def open_menu() -> bool:
    """The floating star has no label, so it is the one coordinate we keep."""
    if L.state() == "pg_side_menu":
        return True
    B.tap(*L.STAR)
    time.sleep(SETTLE)
    return L.state() == "pg_side_menu"


def demo() -> int:
    print("== layer-directed navigation demo ==")
    allok = True

    allok &= _ok(back_to_map(), "return to map")
    allok &= _ok(open_menu(), "open PGSharp menu")

    items = L.menu_items()
    allok &= _ok("設置" in items, f"menu read from layer: {list(items)}")

    allok &= _ok(L.click_node("設置") .startswith("OK"), "clicknode 設置 (by label)")
    time.sleep(3.0)
    allok &= _ok(L.state() == "settings", "state == settings")

    info = L.node_info("虛擬定位")
    allok &= _ok(info.startswith("OK"), f"info 虛擬定位 -> {info[:70]}")

    before = L.switches().get("快速旋轉")
    r1 = L.toggle("快速旋轉")
    time.sleep(1.5)
    mid = L.switches().get("快速旋轉")
    r2 = L.toggle("快速旋轉")
    time.sleep(1.5)
    after = L.switches().get("快速旋轉")
    allok &= _ok(before is not None and mid == (not before) and after == before,
                 f"toggle 快速旋轉 round-trip {before} -> {mid} -> {after}")

    allok &= _ok(L.click_node("確定").startswith("OK"), "clicknode 確定")
    time.sleep(2.5)
    allok &= _ok(L.state() in ("pg_side_menu", "map"), f"closed settings (state={L.state()})")

    print("\nDEMO PASS" if allok else "\nDEMO FAILURES")
    return 0 if allok else 1


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "demo":
        return demo()
    if cmd in ("info", "toggle", "clicknode", "click"):
        label = " ".join(sys.argv[2:])
        fn = {"info": L.node_info, "toggle": L.toggle,
              "clicknode": L.click_node, "click": L.click}[cmd]
        print(fn(label))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
