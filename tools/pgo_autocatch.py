"""Program-level auto-catch: the bot walks, and anything catchable gets caught.

    python tools/pgo_autocatch.py --minutes 5
    python tools/pgo_autocatch.py --minutes 2 --step 10 --max-catches 5

Why this instead of PGSharp's 虛擬 Go Plus
-----------------------------------------
「虛擬 Go Plus」, 「快速捕捉」, 「跳過過場動畫」 and 「擴大遭遇範圍」 are greyed out
in the settings panel and ignore ACTION_CLICK and injected taps: they are gated
by PGSharp's authorisation, not by a config value.  Enabling them would mean
patching the app's permission check, which would break authorisation — the one
thing we must not do.

So the same capability is built here, in our own code:

  * walk continuously with the virtual joystick   -> new spawns enter catch range
  * fine sweep around the avatar (data-layer verified) -> find what is catchable
  * throw immediately on encounter (120 ms flick)  -> 精靈球 only (R1)
  * throw/wait/OK in ONE driver round trip          -> catch in ~3 s

Every hard rule is still enforced at the point of action:
R1 精靈球 only, R2 no berries at all, R5 never touch a raid sheet.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_direct as D
import pgo_layer as L
import pgo_rules as R
import pgo_walk as W

OBS = Path("tools/verify/observations.jsonl")
AVATAR = (535, 1315)
SETTLE_MS = 700


def sweep(r: int = 140, step: int = 50) -> dict | None:
    """Return the first interface that is not the plain map, or None."""
    for x, y in W_sweep(AVATAR, r, step):
        res = L.tapwait(x, y, SETTLE_MS)
        st = res["state"]
        if st == "anr_dialog":
            L.click_node("等一下")
            time.sleep(2.0)
            continue
        if st != "map" or res["overlay"]:
            return {"x": x, "y": y, **res}
    return None


def W_sweep(centre: tuple[int, int], r: int, step: int) -> list[tuple[int, int]]:
    cx, cy = centre
    pts = []
    for dy in range(-r, r + 1, step):
        for dx in range(-r, r + 1, step):
            if dx * dx + dy * dy <= r * r:
                pts.append((cx + dx, cy + dy))
    pts.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    return pts


def record(rec: dict) -> None:
    OBS.parent.mkdir(parents=True, exist_ok=True)
    with OBS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def handle(hit: dict, pos: dict) -> dict:
    """Act on a non-map interface, enforcing the rules."""
    st = hit["state"]
    out = {"state": st, "caught": 0}

    if st in R.RAID_STATES:
        print("   RAID sheet -> BACK (R5, never 對戰)")
        D.back_to_map()
        return out

    if st == "encounter":
        data = L.mon()
        res = L.catch_seq()
        out["caught"] = 1 if res["caught"] else 0
        out["throws"] = res["throws"]
        out["ms"] = res["ms"]
        print(f"   ENCOUNTER L{data.get('level')}/IV{data.get('iv')}/"
              f"{data.get('split')} -> caught={res['caught']} "
              f"throws={res['throws']} {res['ms']} ms "
              f"map_back={res['map_back']}")
        record({"t": round(time.time(), 3), "kind": "encounter",
                "lat": pos.get("lat"), "lon": pos.get("lon"),
                "local": pos.get("local"),
                "sx": hit["x"], "sy": hit["y"],
                "level": data.get("level"), "iv": data.get("iv"),
                "split": data.get("split"), "weather": data.get("boost"),
                "caught": bool(res["caught"]), "throws": res["throws"],
                "ball": R.DEFAULT_BALL, "map_back": res["map_back"],
                "source": "autocatch"})
        if not res["map_back"]:
            D.back_to_map()
        return out

    if st == "stop_disc":
        print("   PokéStop -> BACK")
        D.back_to_map()
        return out

    if hit.get("overlay") and st == "map":
        D.back_to_map()
        return out

    print(f"   {st} -> back to map")
    D.back_to_map()
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--step", type=float, default=12.0, help="metres per walk step")
    ap.add_argument("--max-catches", type=int, default=99)
    args = ap.parse_args()

    if not L.ensure_driver():
        print("driver unavailable")
        return 1

    print(R.describe())
    print()

    D.back_to_map()
    pos = L.position()
    D.back_to_map()

    t_end = time.time() + args.minutes * 60
    caught = walks = sweeps = 0
    heading = 0
    dirs = [(0, -1), (1, 0), (0, 1), (-1, 0)]

    while time.time() < t_end and caught < args.max_catches:
        st = L.state()
        if st == "encounter":
            out = handle({"state": st, "x": 0, "y": 0, "overlay": False}, pos)
            caught += out["caught"]
            continue
        if st != "map":
            D.back_to_map()
            continue

        sweeps += 1
        hit = sweep()
        if hit:
            out = handle(hit, pos)
            caught += out["caught"]
            continue

        dx, dy = dirs[heading % 4]
        heading += 1
        W.walk(dx * args.step, dy * args.step, settle=1.2)
        walks += 1
        if walks % 5 == 0:                 # re-anchor the coordinates periodically
            p = L.position()
            D.back_to_map()
            if p.get("lat"):
                pos = p

    print()
    print(f"done: catches={caught} sweeps={sweeps} walks={walks} "
          f"minutes={args.minutes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
