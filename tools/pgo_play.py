"""Long-run hunter driven by PGSharp's nearby bar — no pixel hunting.

    python tools/pgo_play.py --minutes 300
    python tools/pgo_play.py --minutes 20 --step 20 --gap 2.0

Targeting: the nearby bar
-------------------------
PGSharp draws a vertical bar of the nearby wild spawns in the top-left corner
(x ≈ 0..110).  A **double tap** on one of its icons opens that spawn's encounter
directly (a single tap does nothing).  That bar belongs to PGSharp's overlay,
not to Unity, so:

* the tap target comes from the client's own spawn list instead of from sprite
  detection on the map, and
* the tap never queues a MotionEvent into the game's input channel.

Measured on this device (2026-11-03): icons sit at x = 65, pitch ≈ 105–135 px,
first icon at y ≈ 195; empty bar rows swallow taps harmlessly.

Catching
--------
One flick of the ball (540,1900) → (540,820) over 140 ms is a curve "Great
Throw" and lands on the spawn.  After the throw the berry row disappears, so a
green OK button in the lower part of the result card is the reliable "caught"
marker; tapping it can leave a Pokémon-detail page open, which BACK closes.

Hard rules are enforced at the point of action through `pgo_rules`:
R1 精靈球 only, R2 no berries at all, R5 never touch a raid / max battle.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

import pgo_bot as B
import pgo_direct as D
import pgo_layer as L
import pgo_rules as R
import pgo_walk as W

OBS = Path("tools/verify/observations.jsonl")
STATUS = Path("tools/verify/play_status.json")
SHOT_DIR = Path("tools/pgo_sessions/play")
SERIAL = L.SERIAL

BAR_X = 65
BAR_SLOTS = (195, 300, 405, 510, 615, 720)
THROW = (540, 1900, 540, 820, 140)
OK_BTN = (540, 1853)
GAP = 2.0                 # flavour delay between Unity gestures
DOUBLE_GAP = 0.09         # the double tap has to be fast
ANR_WAIT_BUTTON = (540, 1219)


# ------------------------------------------------------------------ helpers
def sh(*args: str) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", *args],
                       capture_output=True, text=True)
    return (r.stdout or "").strip()


def record(rec: dict) -> None:
    OBS.parent.mkdir(parents=True, exist_ok=True)
    with OBS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def write_status(rec: dict) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    STATUS.write_text(json.dumps(rec, ensure_ascii=False, indent=1),
                      encoding="utf-8")


def has_card(img) -> bool:
    """The result card's OK button is a large green pill at the bottom."""
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    reg = a[1700:1980, 240:840]
    r, g, b = reg[..., 0], reg[..., 1], reg[..., 2]
    return int(((g > 140) & (g > r + 40) & (g > b + 10)).sum()) > 8000


def spec_name(ns=None) -> str | None:
    """Best-effort species name: a CJK label inside the encounter overlay."""
    ts = L.texts(L.nodes() if ns is None else ns)
    skip = {"蔓莓果", "蕉香果", "凰梨果", "精靈球", "超級球", "高級球"}
    for t in ts:
        t = t.strip()
        if 2 <= len(t) <= 5 and any("\u4e00" <= ch <= "\u9fff" for ch in t) \
                and t not in skip and "L" not in t and "IV" not in t \
                and "XP" not in t:
            return t
    return None


def system_stuck() -> bool:
    return "Application Not Responding" in sh("dumpsys", "window", "windows")


def dismiss_anr(tries: int = 2) -> bool:
    for _ in range(tries):
        B.tap(*ANR_WAIT_BUTTON)
        time.sleep(8)
        if not system_stuck():
            time.sleep(4)
            return True
    return False


def double_tap(x: int, y: int) -> None:
    B.tap(x, y)
    time.sleep(DOUBLE_GAP)
    B.tap(x, y)


def settle_after_throw(max_s: float = 12.0) -> str:
    """'encounter' (broke out), 'caught' (card up) or 'unknown'."""
    t0 = time.time()
    while time.time() - t0 < max_s:
        time.sleep(1.0)
        if L.state() == "encounter":
            return "encounter"
        if time.time() - t0 >= 3.0 and has_card(B.grab()):
            return "caught"
    return "unknown"


def catch_slow(pos: dict, slot: int, auto: bool) -> int:
    data = L.mon()
    name = spec_name()
    throws = 0
    outcome = "encounter"
    for _ in range(3):
        if L.state() != "encounter":
            break
        B.swipe(*THROW)
        throws += 1
        time.sleep(GAP)
        outcome = settle_after_throw()
        if outcome == "caught":
            break
        time.sleep(0.8)

    caught = outcome == "caught"
    if caught:
        B.tap(*OK_BTN)
        time.sleep(1.6)
        if L.state() != "map":          # a detail page may be left open
            sh("input", "keyevent", "4")
            time.sleep(1.2)
        if L.state() != "map":
            D.back_to_map()
    else:
        D.back_to_map()

    record({"t": round(time.time(), 3), "kind": "encounter",
            "name": name, "level": data.get("level"), "iv": data.get("iv"),
            "split": data.get("split"), "weather": data.get("boost"),
            "caught": caught, "throws": throws, "outcome": outcome,
            "slot": slot, "auto": auto, "ball": R.DEFAULT_BALL,
            "lat": pos.get("lat"), "lon": pos.get("lon"),
            "local": pos.get("local")})
    print(f"   {'CAUGHT' if caught else 'missed'} {name or '?'}"
          f" L{data.get('level')}/IV{data.get('iv')} throws={throws}"
          f" slot={slot} -> {L.state()}")
    return 1 if caught else 0


# --------------------------------------------------------------------- loop
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=300.0)
    ap.add_argument("--step", type=float, default=20.0, help="metres per walk")
    ap.add_argument("--gap", type=float, default=GAP)
    ap.add_argument("--max-catches", type=int, default=10000)
    args = ap.parse_args()

    if not L.ensure_driver():
        print("driver unavailable")
        return 1

    print(R.describe())
    print(f"session: {args.minutes:.0f} min, step {args.step} m, "
          f"gap {args.gap:.1f} s\n")

    SHOT_DIR.mkdir(parents=True, exist_ok=True)

    if system_stuck():
        print("system already showing a Not-Responding window; dismissing")
        if not dismiss_anr():
            print("!! needs reboot, stopping")
            return 2

    if L.state() != "map":
        D.back_to_map()

    pos = {"lat": None, "lon": None, "local": None}
    t_end = time.time() + args.minutes * 60
    catches = walks = cycles = empty_sweeps = 0
    last_pos_check = time.time()
    health_check = time.time()
    heading = 0
    dirs = [(0, -1), (1, 0), (0, 1), (-1, 0)]

    while time.time() < t_end and catches < args.max_catches:
        cycles += 1

        # ---- system health, every two minutes
        if time.time() - health_check > 120:
            health_check = time.time()
            if system_stuck():
                print("!! system Not-Responding window -> back off")
                if not dismiss_anr():
                    print("!! will not clear; stopping (reboot needed)")
                    write_status({"updated": round(time.time(), 3),
                                  "done": True, "reason": "system_anr",
                                  "cycles": cycles, "catches": catches})
                    return 3
                if L.state() != "map":
                    D.back_to_map()
                continue

        st = L.state()

        if st == "anr_dialog":
            dismiss_anr()
            continue

        if st == "encounter":
            catches += catch_slow(pos, -1, True)
            continue

        if st != "map":
            if st in R.RAID_STATES:
                print("   RAID/極巨化 sheet -> BACK (R5)")
            D.back_to_map()
            continue

        # ---- sweep the nearby bar: the first icon that opens an encounter
        entered = -1
        for slot, y in enumerate(BAR_SLOTS):
            double_tap(BAR_X, y)
            time.sleep(1.3)
            s = L.state()
            if s == "encounter":
                entered = slot
                break
            if s == "anr_dialog":
                dismiss_anr()
                break
            if s in R.RAID_STATES:
                print("   RAID/極巨化 sheet -> BACK (R5)")
                D.back_to_map()
                break
            if s != "map":
                D.back_to_map()
                break

        if entered >= 0:
            catches += catch_slow(pos, entered, False)
            continue

        # ---- nothing in the bar: walk to refresh the spawn list
        empty_sweeps += 1
        dx, dy = dirs[heading % 4]
        W.walk(dx * args.step, dy * args.step, settle=1.0)
        time.sleep(GAP)
        walks += 1
        heading += 1

        # ---- re-anchor coordinates every ~10 min (also proves no sniping)
        if time.time() - last_pos_check > 600:
            last_pos_check = time.time()
            p = L.position()
            D.back_to_map()
            if p.get("lat"):
                pos = p
                record({"t": round(time.time(), 3), "kind": "position",
                        "lat": p.get("lat"), "lon": p.get("lon"),
                        "local": p.get("local"), "cycles": cycles,
                        "catches": catches, "walks": walks})

        write_status({"updated": round(time.time(), 3), "cycles": cycles,
                      "catches": catches, "walks": walks,
                      "empty_sweeps": empty_sweeps,
                      "minutes_left": round((t_end - time.time()) / 60, 1),
                      "state": st, "lat": pos.get("lat"),
                      "lon": pos.get("lon")})

    print(f"\ndone: catches={catches} walks={walks} cycles={cycles}")
    write_status({"updated": round(time.time(), 3), "done": True,
                  "cycles": cycles, "catches": catches, "walks": walks,
                  "state": "finished"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
