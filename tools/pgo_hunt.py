"""Scan the map on-device, then verify each tap against the data layer.

    python tools/pgo_hunt.py --rounds 1 --max-taps 8
    python tools/pgo_hunt.py --dry                 # scan only, no taps

Why the two-stage design
------------------------
The on-device scan (Driver `scan`) is a *candidate generator*: it costs ~100 ms
and returns at most 12 variance peaks with colour + ground-ring evidence.  Pixel
classification alone can confuse a purple Pokémon with a spun PokéStop, so no
decision is made from the picture.  Every candidate is tapped and the resulting
interface is read from the accessibility layer, which is authoritative:

    encounter   -> catch it (rules R1-R5 enforced by pgo_layer.catch)
    stop_disc   -> mark the stop spun, BACK out
    raid        -> R5: BACK out immediately, never press 對戰
    settings / pg_side_menu / anything else -> return to map
    map         -> nothing there (out of range, or already gone)

Usage is deliberately conservative: at most `--max-taps` taps per round, and a
tap point is never retried within the same round.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pgo_bot as B
import pgo_direct as D
import pgo_layer as L
import pgo_rules as R

OBS = Path("tools/verify/observations.jsonl")
LEDGER = Path("tools/verify/pokestop_ledger.jsonl")
AVATAR = (540, 1380)
SETTLE = 2.0

# The avatar's screen position is stable for a given camera, and the game only
# lets you interact with things inside ~40 m.  At this zoom that is ~165 px
# (measured: 33.3 m of walking shifted the world 136 px -> 4.1 px/m), so the
# sweep below covers a 3x that radius to allow for camera drift.
HOT_R = 210
SWEEP_STEP = 85


def _sweep_points(cx: int = AVATAR[0], cy: int = AVATAR[1],
                  r: int = HOT_R, step: int = SWEEP_STEP) -> list[tuple[int, int]]:
    """Tap points inside the interaction circle, nearest first.

    Vision can only *propose* targets: a variance peak may sit on a road
    marking or an event pumpkin.  This sweep is the fallback that guarantees
    coverage of the reachable area, and every point is verified against the
    accessibility layer, so a miss costs one tap and nothing else.
    """
    pts = []
    for dy in range(-r, r + 1, step):
        for dx in range(-r, r + 1, step):
            if dx * dx + dy * dy > r * r:
                continue
            pts.append((cx + dx, cy + dy))
    pts.sort(key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
    return pts


def _dist(o: dict) -> float:
    return ((o["x"] - AVATAR[0]) ** 2 + (o["y"] - AVATAR[1]) ** 2) ** 0.5


def _order(objs: list[dict]) -> list[dict]:
    """Wild spawns first (nearest first), then stops, then everything else."""
    def key(o):
        rank = 0 if o["kind"] == "spawn" else (1 if o["kind"].startswith("stop") else 2)
        return (rank, _dist(o))
    return sorted(objs, key=key)


def _append(path: Path, rec: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def hunt_round(max_taps: int, dry: bool, pos: dict) -> dict:
    st = L.state()
    if st != "map":
        D.back_to_map()
    res = L.scan()
    if not res.get("ok"):
        return {"error": res.get("raw", ""), "tapped": 0, "caught": 0}

    objs = _order(res["objects"])
    spawns = sum(1 for o in objs if o["kind"] == "spawn")
    stops = sum(1 for o in objs if o["kind"].startswith("stop"))
    print(f"scan {res['ms']} ms: {len(objs)} objects "
          f"({spawns} spawn / {stops} stop)")
    for o in objs:
        print(f"   {o['kind']:<10} {o['x']:>4} {o['y']:>4} "
              f"ring={o['ring']:.2f} o={o['orange']:.2f} v={o['violet']:.2f}")

    if dry:
        return {"tapped": 0, "caught": 0, "objects": objs}

    tapped = caught = spun = 0
    seen: list[tuple[int, int]] = []
    for o in objs:
        if tapped >= max_taps:
            break
        if any((o["x"] - x) ** 2 + (o["y"] - y) ** 2 < 70 ** 2 for x, y in seen):
            continue
        seen.append((o["x"], o["y"]))
        tapped += 1

        B.tap(o["x"], o["y"])
        time.sleep(SETTLE)
        st = L.state()

        if st == "anr_dialog":
            # The game's main thread missed our MotionEvent.  "等一下" keeps the
            # session; "關閉應用程式" would kill it.
            print(f"   tap {o['x']},{o['y']} -> ANR, waiting")
            L.click_node("等一下")
            time.sleep(4.0)
            st = L.state()

        # R5 guard: a gym / raid sheet must be dismissed, never acted on.
        if st in R.RAID_STATES:
            print(f"   tap {o['x']},{o['y']} -> RAID screen, BACK (R5)")
            D.back_to_map()
            continue

        if st == "encounter":
            data = L.mon()
            print(f"   tap {o['x']},{o['y']} -> encounter {data}")
            out = L.catch()
            caught += 1 if out.get("caught") else 0
            _append(OBS, {
                "t": round(time.time(), 3), "kind": "encounter",
                "lat": pos.get("lat"), "lon": pos.get("lon"),
                "local": pos.get("local"),
                "sx": o["x"], "sy": o["y"],
                "level": data.get("level"), "iv": data.get("iv"),
                "split": data.get("split"), "weather": data.get("boost"),
                "caught": bool(out.get("caught")), "throws": out.get("throws", 0),
                "ball": out.get("ball", ""),
                "ring": o["ring"], "orange": o["orange"], "violet": o["violet"],
            })
            print(f"      caught={out.get('caught')} throws={out.get('throws')} "
                  f"ball={out.get('ball')}")
            D.back_to_map()
            continue

        if st == "stop_disc":
            spun += 1
            print(f"   tap {o['x']},{o['y']} -> PokéStop, BACK")
            _append(LEDGER, {
                "t": round(time.time(), 3), "kind": "stop_observation",
                "lat": pos.get("lat"), "lon": pos.get("lon"),
                "local": pos.get("local"),
                "sx": o["x"], "sy": o["y"], "state": "spun",
                "orange": o["orange"], "violet": o["violet"], "ring": o["ring"],
                "verified": "stop_disc",
            })
            D.back_to_map()
            continue

        print(f"   tap {o['x']},{o['y']} -> {st}")
        if st != "map":
            D.back_to_map()

    return {"tapped": tapped, "caught": caught, "spun": spun,
            "objects": len(objs)}


def sweep_round(max_taps: int, pos: dict, settle: int = 800) -> dict:
    """Tap a grid over the interaction circle until something real opens.

    Each point costs ONE driver round trip: `tapwait` injects the tap, then the
    phone itself polls its node tree and screen probe and returns the resulting
    interface.  That is ~0.95 s per miss (was ~2.8 s) and ~0.3 s per hit.

    The picture is never trusted for a decision: a tap that opens nothing costs
    one tap, an encounter is caught immediately, and a raid sheet is backed out
    of (R5).
    """
    tapped = caught = spun = 0
    for x, y in _sweep_points():
        if tapped >= max_taps:
            break
        tapped += 1
        r = L.tapwait(x, y, settle)
        st = r["state"]

        if st == "anr_dialog":
            print(f"   tap {x},{y} -> ANR, waiting")
            L.click_node("等一下")
            time.sleep(3.0)
            continue

        if st in R.RAID_STATES:
            print(f"   tap {x},{y} -> RAID screen, BACK (R5)")
            D.back_to_map()
            continue

        if st == "encounter":
            data = L.mon()
            print(f"   tap {x},{y} -> ENCOUNTER {data}  ({r['ms']} ms)")
            out = L.catch()
            caught += 1 if out.get("caught") else 0
            _append(OBS, {
                "t": round(time.time(), 3), "kind": "encounter",
                "lat": pos.get("lat"), "lon": pos.get("lon"),
                "local": pos.get("local"),
                "sx": x, "sy": y,
                "level": data.get("level"), "iv": data.get("iv"),
                "split": data.get("split"), "weather": data.get("boost"),
                "caught": bool(out.get("caught")), "throws": out.get("throws", 0),
                "ball": out.get("ball", ""),
                "map_back": out.get("map_back"),
            })
            print(f"      caught={out.get('caught')} throws={out.get('throws')} "
                  f"ball={out.get('ball')} map_back={out.get('map_back')}")
            if not out.get("map_back"):
                D.back_to_map()
            continue

        if st == "stop_disc":
            spun += 1
            print(f"   tap {x},{y} -> PokéStop, BACK  ({r['ms']} ms)")
            _append(LEDGER, {
                "t": round(time.time(), 3), "kind": "stop_observation",
                "lat": pos.get("lat"), "lon": pos.get("lon"),
                "local": pos.get("local"),
                "sx": x, "sy": y, "state": "spun", "verified": "stop_disc",
            })
            D.back_to_map()
            continue

        if st == "map":
            # A tap that opened nothing looks exactly like the map in the tree.
            # The probe tells them apart: a warm centre means a full-screen
            # Unity overlay came up (PokéStop photo disc, gym sheet).
            if r["overlay"]:
                print(f"   tap {x},{y} -> overlay (warm={r['warm']:.1f}), BACK")
                _append(LEDGER, {
                    "t": round(time.time(), 3), "kind": "overlay_observation",
                    "lat": pos.get("lat"), "lon": pos.get("lon"),
                    "local": pos.get("local"),
                    "sx": x, "sy": y, "state": "unknown",
                    "verified": "overlay_probe", "warm": r["warm"],
                })
                spun += 1
                D.back_to_map()
            continue

        print(f"   tap {x},{y} -> {st}")
        D.back_to_map()

    return {"tapped": tapped, "caught": caught, "spun": spun, "mode": "sweep"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--max-taps", type=int, default=8)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--sweep", action="store_true",
                    help="grid-sweep the interaction circle instead of trusting vision")
    ap.add_argument("--settle", type=int, default=800,
                    help="ms the phone waits for a change after each tap")
    args = ap.parse_args()

    if not L.ensure_driver():
        print("driver unavailable")
        return 1

    # Policy: an encounter that is already open is thrown at immediately.
    total = {"tapped": 0, "caught": 0, "spun": 0}
    if L.state() == "encounter":
        print("already in an encounter -> catching")
        out = L.catch()
        print(f"   caught={out.get('caught')} throws={out.get('throws')} "
              f"ball={out.get('ball')} mon={out.get('mon')}")
        if out.get("caught"):
            total["caught"] += 1
            _append(OBS, {
                "t": round(time.time(), 3), "kind": "encounter",
                "lat": None, "lon": None, "local": None,
                "sx": None, "sy": None,
                "level": out["mon"].get("level"), "iv": out["mon"].get("iv"),
                "split": out["mon"].get("split"),
                "weather": out["mon"].get("boost"),
                "caught": True, "throws": out.get("throws", 0),
                "ball": out.get("ball", ""), "verified": "opening_policy",
            })
            D.back_to_map()

    for r in range(args.rounds):
        D.back_to_map()
        pos = L.position()          # authoritative lat/lon for the records
        D.back_to_map()
        if args.sweep:
            out = sweep_round(args.max_taps, pos, args.settle)
        else:
            out = hunt_round(args.max_taps, args.dry, pos)
        print(f"[{r}] {out}")
        if "error" in out:
            continue
        for k in total:
            total[k] += out.get(k, 0)

    print(f"total {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
