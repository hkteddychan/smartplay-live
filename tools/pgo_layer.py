"""Play PGSharp from the *data layer* only — no screencap.

Why this exists
---------------
Screenshots cost ~0.9 s each on this device and the pixel classifier only knows
three states (encounter / result / map).  The accessibility node tree, served by
our instrumentation APK (com.opencode.pgodrive), exposes the same information as
*data*: the game's own labels for level, IV, IV-split, weather boost, the berry
buttons, the PGSharp menu, every settings toggle and every system dialog.

This module turns that tree into named game state, so a policy can decide
without ever looking at a picture.

    python tools/pgo_layer.py state            # one-line state
    python tools/pgo_layer.py mon              # encounter data (L/IV/split)
    python tools/pgo_layer.py dump             # full deduped tree
    python tools/pgo_layer.py dump --grep 設置  # filter
    python tools/pgo_layer.py bench            # layer read vs screencap timing
    python tools/pgo_layer.py verify           # layer vs pixels, appends a report

Everything returns plain Python values so it can be used as a library:

    from pgo_layer import state, mon
    if state() == "encounter":
        print(mon())
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

SERIAL = "1bbd5689"
REPORT = Path("tools/verify/layer_vs_pixels.jsonl")
JOY_CACHE = Path("tools/verify/joystick.json")

RX_SPLIT = re.compile(r"^\d+/\d+/\d+$")
RX_NUM = re.compile(r"^\d+$")

# Texts that only exist on one interface.  Each predicate gets the whole text
# list, so multi-label screens (menu = 自動行走 + Feeds) work.  First match wins.
SIGNATURES = [
    ("anr_dialog",    lambda ts: any("沒有回應" in t or "isn't responding" in t for t in ts)),
    ("safety_dialog", lambda ts: any("注意周遭環境" in t for t in ts)),
    ("settings",      lambda ts: any("虛擬定位" in t or "快速捕捉" in t for t in ts)),
    ("pg_side_menu",  lambda ts: "自動行走" in ts and "Feeds" in ts),
    ("raid",          lambda ts: any(t in ("對戰", "私人小組") or "使用250MP" in t for t in ts)),
    ("stop_disc",     lambda ts: any("旋轉" in t or "轉補給站" in t for t in ts)),
    # An encounter is the ONLY screen that shows the berry row.  PGSharp's
    # L/IV overlay also stays visible on the Pokémon detail page, so L+IV alone
    # would misclassify that page as an encounter (observed 2026-11-02).
    ("encounter",     lambda ts: any(t in ("蔓莓果", "蕉香果", "凰梨果") for t in ts)),
    ("mon_detail",    lambda ts: "L" in ts and "IV" in ts),
]


# --------------------------------------------------------------------- driver
def sh(cmd: str) -> str:
    r = subprocess.run(["adb", "-s", SERIAL, "shell", cmd],
                       capture_output=True, text=True)
    return r.stdout


BASE = "/sdcard/Android/data/com.opencode.pgodrive/files"
CMD = BASE + "/cmd.txt"
OUT = BASE + "/out.txt"


def drive(cmd: str, timeout: float = 8.0, retry: bool = True) -> str:
    """One request/response round trip with the instrumentation driver.

    Everything happens inside a *single* `adb shell`, which polls the reply
    file on the device.  Three separate adb processes (rm / write / cat) cost
    ~300 ms; this costs ~100 ms and puts far less load on system_server.
    """
    ticks = max(20, int(timeout / 0.01))
    script = (
        f"rm -f {OUT}; printf '%s' '{cmd}' > {CMD}; "
        f"i=0; while [ $i -lt {ticks} ]; do "
        f"if [ -s {OUT} ]; then cat {OUT}; break; fi; "
        f"sleep 0.01; i=$((i+1)); done"
    )
    r = subprocess.run(["adb", "-s", SERIAL, "shell", script],
                       capture_output=True, text=True)
    out = r.stdout.strip()
    if not out and retry and cmd != "ping" and ensure_driver():
        return drive(cmd, timeout, retry=False)
    return out


_PINGED = False


def alive() -> bool:
    global _PINGED
    r = drive("ping", retry=False)
    ok = r.startswith("OK")
    _PINGED = ok
    return ok


_INSTR = ("am instrument -w -e nop 0 "
          "com.opencode.pgodrive/com.opencode.pgodrive.Driver")
PKG = "com.opencode.pgodrive"


def _start_instrumentation() -> None:
    subprocess.Popen(["adb", "-s", SERIAL, "shell", _INSTR],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def _dump_ok() -> bool:
    """A live UiAutomation always sees at least the system-bar nodes."""
    raw = drive("dump", retry=False)
    if not raw.startswith("OK nodes="):
        return False
    try:
        return int(raw.split("nodes=")[1].split()[0]) > 0
    except (IndexError, ValueError):
        return False


def restart_driver(wait: float = 15.0) -> bool:
    """Force-stop + relaunch the instrumentation and wait until it is usable.

    A plain relaunch is not enough: when the UiAutomation connection dies the
    old process keeps answering `ping` while `dump` returns zero nodes and
    `takeScreenshot` returns null.  Killing the process is the only fix.
    """
    subprocess.run(["adb", "-s", SERIAL, "shell", "am", "force-stop", PKG],
                   capture_output=True)
    time.sleep(1.0)
    _start_instrumentation()
    deadline = time.time() + wait
    while time.time() < deadline:
        time.sleep(0.5)
        if alive() and _dump_ok():
            return True
    return False


def ensure_driver(wait: float = 15.0) -> bool:
    """Make sure the layer is usable, restarting it if it has died."""
    if alive() and _dump_ok():
        return True
    return restart_driver(wait)


# ---------------------------------------------------------------- node tree
def parse_dump(raw: str) -> list[dict]:
    """Parse the driver's TSV dump into node dicts (deduped, no device access).

    Split out from `nodes()` so the parser can be regression-tested offline
    against saved dumps (see tools/_layer_selftest.py).
    """
    if not (raw.startswith("OK") or raw.startswith("nodes=")):
        return []
    out, seen = [], set()
    for line in raw.splitlines()[1:]:
        if line in seen:
            continue
        seen.add(line)
        p = line.split("|")
        if len(p) < 5:
            continue
        try:
            l, t, r, b = (int(v) for v in p[3].split(","))
        except ValueError:
            continue
        out.append({
            "cls": p[0].rsplit(".", 1)[-1],
            "text": p[1],
            "desc": p[2],
            "l": l, "t": t, "r": r, "b": b,
            "cx": (l + r) // 2, "cy": (t + b) // 2,
            "clickable": "C" in p[4],
            "flags": p[4],
        })
    return out


def nodes() -> list[dict]:
    """Deduped node list.  The driver walks every window, so entries repeat."""
    ns = parse_dump(drive("dump"))
    if not ns and ensure_driver():
        ns = parse_dump(drive("dump", retry=False))
    return ns


def texts(ns: list[dict] | None = None) -> list[str]:
    ns = nodes() if ns is None else ns
    out = []
    for n in ns:
        for s in (n["text"], n["desc"]):
            if s:
                out.append(s)
    return out


def find(label: str, ns: list[dict] | None = None, exact=False) -> dict | None:
    ns = nodes() if ns is None else ns
    for n in ns:
        for s in (n["text"], n["desc"]):
            if not s:
                continue
            if (s == label) if exact else (label in s):
                return n
    return None


# ---------------------------------------------------------------- game state
def state(ns: list[dict] | None = None) -> str:
    """Named interface, decided from the node tree alone."""
    ns = nodes() if ns is None else ns
    return state_from_texts(texts(ns)) if ns else "no_layer"


def state_from_texts(ts: list[str]) -> str:
    """Classify an interface from a bare list of texts (no device access).

    Split out so `tapwait` can classify the texts the phone returned in the same
    round trip, instead of asking for a second dump.
    """
    if not ts:
        return "no_layer"
    for name, pred in SIGNATURES:
        if pred(ts):
            return name
    return "map"


def mon(ns: list[dict] | None = None) -> dict:
    """Encounter data straight from the tree: level, IV, split, weather boost.

    The client lays the overlay out as a row of text nodes
    `L` `21` `IV` `53` `10/6/8` `✿/౯`, so we read them positionally rather
    than guessing from pixels.
    """
    ns = nodes() if ns is None else ns
    out = {"level": None, "iv": None, "split": None, "boost": None}
    row = [n for n in ns if n["cls"] == "TextView" and n["text"]
           and 380 < n["cy"] < 520 and n["l"] > 300]
    row.sort(key=lambda n: n["l"])
    vals = [n["text"] for n in row]
    for i, v in enumerate(vals):
        if v == "L" and i + 1 < len(vals):
            out["level"] = vals[i + 1]
        elif v == "IV" and i + 1 < len(vals):
            out["iv"] = vals[i + 1]
        elif RX_SPLIT.match(v):
            out["split"] = v
    for n in row:
        if "✿" in n["text"]:
            out["boost"] = n["text"]
    # the berry buttons tell us the encounter is live and which feeds are legal
    out["berries"] = [t for t in vals + texts(ns)
                      if t in ("蔓莓果", "蕉香果", "凰梨果")]
    # internal consistency: this client *truncates* 100*(atk+def+sta)/45
    #   (6+4+15)/45 = 55.56 -> shows 55, so floor, not round.
    if out["split"] and out["iv"]:
        try:
            s = sum(int(v) for v in out["split"].split("/"))
            expect = int(100 * s / 45)
            out["iv_expected"] = expect
            out["consistent"] = expect == int(out["iv"])
        except ValueError:
            out["consistent"] = None
    return out


def menu_items(ns: list[dict] | None = None) -> dict:
    """PGSharp side-menu entries, name -> tap point (layer-driven navigation)."""
    ns = nodes() if ns is None else ns
    want = ("地圖", "30.0 km/h", "自動行走", "Feeds", "收藏夾", "傳送", "設置")
    out = {}
    for n in ns:
        if n["cls"] == "TextView" and n["text"] in want and n["cx"] > 700:
            out[n["text"]] = (n["cx"], n["cy"])
    return out


def feed_entries(ns: list[dict] | None = None) -> list[dict]:
    """PGSharp's 附近的寶可夢 column: the clickable spawn shortcuts on the left.

    These are real layer nodes, so a policy can pick a target without looking at
    the map at all.
    """
    ns = nodes() if ns is None else ns
    out = []
    for n in ns:
        if not n["clickable"] or n["r"] > 130:
            continue
        if n["cls"] not in ("RelativeLayout", "ImageView", "ImageButton"):
            continue
        if not (400 <= n["t"] <= 1300):
            continue
        if n["b"] - n["t"] < 40:
            continue
        out.append({"cx": n["cx"], "cy": n["cy"],
                    "l": n["l"], "t": n["t"], "r": n["r"], "b": n["b"],
                    "cls": n["cls"], "desc": n["desc"]})
    out.sort(key=lambda d: d["t"])
    return out


def switches(ns: list[dict] | None = None) -> dict:
    """Label -> True/False for every on/off row, read from the Switch widget.

    The driver marks nodes `K` (checkable) and `X` (checked), so the layer
    exposes the real toggle state without any pixels.
    """
    ns = nodes() if ns is None else ns
    labels = [n for n in ns if n["cls"] == "TextView" and n["text"] and n["l"] < 70]
    out = {}
    for sw_n in (n for n in ns if n["cls"] == "Switch"):
        cy = (sw_n["t"] + sw_n["b"]) // 2
        near = [lb for lb in labels if abs((lb["t"] + lb["b"]) // 2 - cy) <= 40]
        if not near:
            continue
        lb = min(near, key=lambda d: abs((d["t"] + d["b"]) // 2 - cy))
        out[lb["text"]] = "X" in sw_n["flags"]
    return out


def values(ns: list[dict] | None = None) -> dict:
    """Numeric/text values the client exposes in EditText widgets (e.g. speed)."""
    ns = nodes() if ns is None else ns
    return {n["text"]: (n["l"], n["t"], n["r"], n["b"])
            for n in ns if n["cls"] == "EditText" and n["text"]}


def toggles(ns: list[dict] | None = None) -> dict:
    """Every settings row we can read: Switch states plus On/Off text rows."""
    ns = nodes() if ns is None else ns
    out = {k: ("On" if v else "Off") for k, v in switches(ns).items()}
    rows = sorted([n for n in ns if n["cls"] == "TextView" and n["text"]],
                  key=lambda n: n["t"])
    for i, n in enumerate(rows):
        if n["l"] < 40 or n["l"] > 60:
            continue
        for m in rows[i + 1:i + 3]:
            if abs(m["t"] - n["t"]) < 80 and m["text"] in ("On", "Off"):
                out.setdefault(n["text"], m["text"])
                break
    return out


def wait_state(want: str, timeout: float = 15.0, stable: int = 3,
               poll: float = 0.35) -> bool:
    """Wait until `want` is read `stable` times in a row (debounced)."""
    t0, hits = time.time(), 0
    while time.time() - t0 < timeout:
        if state() == want:
            hits += 1
            if hits >= stable:
                return True
        else:
            hits = 0
        time.sleep(poll)
    return False


def encounter_ended(timeout: float = 20.0, stable: int = 6,
                    poll: float = 0.35) -> bool:
    """True once the encounter has been gone for `stable` consecutive reads.

    The berry row disappears for ~1 s during the throw animation, so a single
    'not encounter' read is NOT evidence that the catch resolved.  Requiring a
    run of consecutive misses removes that false positive.
    """
    t0, miss = time.time(), 0
    while time.time() - t0 < timeout:
        if state() == "encounter":
            miss = 0
        else:
            miss += 1
            if miss >= stable:
                return True
        time.sleep(poll)
    return False


# -------------------------------------------------------------------- actions
# After a catch the client shows a result card ("TOTAL 1,170 XP" / 抓獲結果).
# It renders on the Unity surface, so it has no text of its own, but the game
# stays blocked behind it until its OK is pressed.  The user's rule
# (2026-11-02) is: press OK immediately and get back to the map, so the next
# spawn can be handled without waiting for the card to time out.
CATCH_CARD_OK = (539, 1580)
CATCH_CARD_LABELS = ("OK", "確定", "好")


def dismiss_catch_card(tries: int = 3) -> bool:
    """Press the catch result card's OK so the map comes back immediately.

    Prefers the accessibility action (no MotionEvent, so no ANR risk); falls
    back to a coordinate tap at the card's button.  Returns True once the
    screen is the map again.
    """
    import pgo_bot as B

    for _ in range(tries):
        if state() == "map" and not probe().get("overlay"):
            return True
        for label in CATCH_CARD_LABELS:
            if click_node(label).startswith("OK"):
                time.sleep(1.0)
                break
        else:
            B.tap(*CATCH_CARD_OK)
            time.sleep(1.0)
        if state() == "map" and not probe().get("overlay"):
            return True
    return state() == "map"


ENCOUNTER_LOG = Path("tools/verify/encounters.jsonl")


def log_encounter(data: dict, extra: dict | None = None) -> None:
    """Append one layer-read encounter to the verification dataset."""
    ENCOUNTER_LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = {"t": round(time.time(), 3), **data}
    if extra:
        rec.update(extra)
    with ENCOUNTER_LOG.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def catch_if_encounter(max_throws: int = 8, ball: str | None = None) -> dict | None:
    """Policy: an open encounter is always thrown at, immediately.

    Every entry point calls this before doing anything else, so a stray tap that
    opens an encounter is never left hanging (and never wastes the spawn).
    Returns None when there is no encounter, otherwise the result of `catch()`.

    No screenshot and no OCR is involved: the encounter is recognised from the
    berry row in the accessibility tree, the Pokémon's level/IV from the
    PGSharp overlay labels, and the throw is a fixed 120 ms flick.
    """
    if state() != "encounter":
        return None
    data = mon()
    out = catch(max_throws=max_throws, ball=ball)
    out["mon"] = out.get("mon") or data
    return out


def catch(max_throws: int = 8, ball: str | None = None) -> dict:
    """Catch the current encounter using the layer for every decision.

    Returns {"caught": bool, "throws": int, "mon": {...}}.
    """
    from pgo_rules import DEFAULT_BALL, assert_ball_allowed
    import pgo_bot as B

    ball = assert_ball_allowed(ball or DEFAULT_BALL)
    if state() != "encounter":
        return {"caught": False, "throws": 0, "mon": {}, "error": "not in encounter"}
    data = mon()
    log_encounter(data)
    throws = 0
    for _ in range(max_throws):
        if state() != "encounter":
            break
        B.swipe(540, 1900, 540, 800, 120)
        throws += 1
        if encounter_ended(timeout=18):
            # Policy: press OK straight away so the map is back for the next spawn.
            dismissed = dismiss_catch_card()
            return {"caught": True, "throws": throws, "mon": data,
                    "ball": ball, "state": state(), "map_back": dismissed}
    return {"caught": False, "throws": throws, "mon": data, "ball": ball,
            "state": state()}


# ----------------------------------------------------------- settings snapshot
STAR = (981, 153)                     # PGSharp floating menu toggle
SETTINGS_CACHE = Path("tools/verify/settings.json")


def snapshot() -> dict:
    """Open 設置, read every switch/value from the layer, close, cache it.

    Reading the toggles only works while the settings panel is open, so we do
    it once and reuse the result.  Costs ~2 taps.
    """
    import pgo_bot as B

    st = state()
    if st != "pg_side_menu":
        B.tap(*STAR)
        time.sleep(1.2)
    m = menu_items()
    if "設置" not in m:
        raise RuntimeError(f"side menu not visible (state={state()})")
    B.tap(*m["設置"])
    time.sleep(3.0)
    if state() != "settings":
        raise RuntimeError("settings panel did not open")
    data = {"toggles": toggles(), "values": list(values().keys()),
            "t": round(time.time(), 3)}
    click("確定")
    time.sleep(1.5)
    SETTINGS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    return data


def _on(v) -> bool:
    """Toggles are stored as bools by switches(); accept 'On'/'Off' too."""
    return v is True or v == "On"


def stop_status() -> dict:
    """Best-effort PokéStop status from the data layer.

    The stops themselves are Unity sprites with no nodes, so per-stop state
    (spun / available) is NOT obtainable here.  What the layer *does* expose is
    the automation that decides it for us.
    """
    if not SETTINGS_CACHE.exists():
        return {"known": False,
                "note": "run `pgo_layer.py snapshot` once to cache settings"}
    cache = json.loads(SETTINGS_CACHE.read_text(encoding="utf-8"))
    t = cache.get("toggles", {})
    speed = next((v for v in cache.get("values", []) if v.replace(".", "").isdigit()), None)
    return {
        "known": True,
        "auto_spin": _on(t.get("快速旋轉")),
        "quick_catch": _on(t.get("快速捕捉")),
        "speed_kmh": speed,
        "sniping_disabled": cache.get("sniping_disabled"),
        "raid_assistant": _on(t.get("Raid & Gym Battle Assistant")),
        "max_battle_assistant": _on(t.get("極巨化戰鬥輔助")),
        "per_stop_state": None,
        "note": ("per-stop spun/available is Unity-only; the layer exposes no "
                 "node for it. With 快速旋轉 On the client spins on proximity, "
                 "so the bot never has to decide."),
    }


# --------------------------------------------------------------- verification
RX_COORD = re.compile(r"^(-?\d{1,3}\.\d{3,})\s*,\s*(-?\d{1,3}\.\d{3,})$")


def position() -> dict:
    """Player lat/lng, read from the 傳送 panel — the layer's only location data.

    No screenshot is involved: the panel renders the current coordinates as a
    plain TextView, which we parse.  Opens and cancels the panel (~2 s).
    """
    import pgo_bot as B

    if state() != "pg_side_menu":
        B.tap(*STAR)
        time.sleep(1.2)
    m = menu_items()
    if "傳送" not in m:
        return {"known": False, "error": f"no 傳送 entry (state={state()})"}
    B.tap(*m["傳送"])
    time.sleep(2.5)
    ns = nodes()
    lat = lon = local = None
    for n in ns:
        t = (n["text"] or "").strip()
        mm = RX_COORD.match(t.replace(" ", ""))
        if mm:
            lat, lon = float(mm.group(1)), float(mm.group(2))
        elif re.match(r"\d{2}-\d{2}\s+\d{2}:\d{2}", t):
            local = t
    click("取消")
    time.sleep(1.0)
    return {"known": lat is not None, "lat": lat, "lon": lon, "local": local}


def joystick() -> tuple[int, int] | None:
    """PGSharp's virtual joystick knob.

    Normally located from the layer: the knob is a plain `android.view.View` at
    the left edge and the largest such node in the lower-left quadrant is the
    drag area.  On some launches the overlay is drawn without an accessibility
    node at all (only two windows are reported), so we fall back to the last
    verified position, cached in tools/verify/joystick.json.
    """
    best = None
    for n in nodes():
        w, h = n["r"] - n["l"], n["b"] - n["t"]
        if n["cls"] != "View":
            continue
        if n["l"] > 12 or not (1150 <= n["t"] <= 1780) or w < 200 or h < 200:
            continue
        if best is None or n["b"] > best["b"]:
            best = n
    if best:
        pos = (best["cx"], best["cy"])
        try:
            JOY_CACHE.parent.mkdir(parents=True, exist_ok=True)
            JOY_CACHE.write_text(json.dumps({"x": pos[0], "y": pos[1]}),
                                 encoding="utf-8")
        except OSError:
            pass
        return pos
    if JOY_CACHE.exists():
        try:
            d = json.loads(JOY_CACHE.read_text(encoding="utf-8"))
            return int(d["x"]), int(d["y"])
        except (ValueError, KeyError):
            return None
    return None


STOP_ORANGE = 0.30     # >30% orange inside the object -> PokéStop available
STOP_VIOLET = 0.22     # >22% violet   -> PokéStop already spun
RING_MIN = 0.45        # >45% of a pale ground ellipse -> world object on a ring
WARM_OVERLAY = -12.0   # mean(R-B) above this = a full-screen Unity overlay, not the map


def probe() -> dict:
    """Cheap screen-type probe, computed on the phone.

    `warm` is mean(R-B) over the central area: the map is strongly blue-grey
    (about -25), while any full-screen Unity overlay — PokéStop photo disc, gym
    sheet, catch screen — is warm and near 0.  The accessibility tree cannot
    tell those apart, because they are drawn on the Unity surface.
    """
    raw = drive("probe")
    if not raw.startswith("OK"):
        return {"ok": False, "raw": raw, "overlay": None}
    meta = dict(kv.split("=") for kv in raw.split()[2:] if "=" in kv)
    warm = int(meta.get("warm", 0)) / 10.0
    return {"ok": True, "warm": warm,
            "sat": int(meta.get("sat", 0)) / 10.0,
            "satsd": int(meta.get("satsd", 0)) / 10.0,
            "lum": int(meta.get("lum", 0)) / 10.0,
            "overlay": warm > WARM_OVERLAY}


def on_map() -> bool:
    """True only when the accessibility tree AND the pixels agree it is the map."""
    if state() != "map":
        return False
    p = probe()
    return p.get("ok") and p["overlay"] is False


def tapwait(x: int, y: int, settle: int = 800, nowarm: bool = False) -> dict:
    """Tap at (x, y) and get the resulting interface back in ONE round trip.

    The phone polls its own node tree and screen probe every ~100 ms and stops
    as soon as anything changes, so a hit costs ~250 ms instead of ~2.8 s of
    `tap` + `sleep` + `dump` + `probe`.

    `nowarm=True` keeps the wait on the node tree only.  The pixel probe is
    useless on event maps, where the bare map is warm too, and taking a
    screenshot every 70 ms starves the GPU (dequeueBuffer -110, 30 s frames).

    Returns {"ok", "ms", "changed", "warm", "state", "texts", "overlay"}.
    """
    cmd = f"tapwait {int(x)} {int(y)} {int(settle)}" + (" nowarm" if nowarm else "")
    raw = drive(cmd)
    if not raw.startswith("OK") and ensure_driver():
        raw = drive(cmd, retry=False)
    if not raw.startswith("OK"):
        return {"ok": False, "raw": raw, "state": "no_layer", "texts": [],
                "changed": False, "warm": 0.0, "overlay": False, "ms": 0}

    head, _, tail = raw.partition(" texts=")
    meta = dict(kv.split("=", 1) for kv in head.split()[2:] if "=" in kv)
    ts = [t for t in tail.split("\x01") if t] if tail else []
    warm = int(meta.get("warm", 0)) / 10.0
    if nowarm or warm < -9000:           # probe disabled / no screenshot
        warm = 0.0
        overlay = False
    else:
        overlay = warm > WARM_OVERLAY
    return {"ok": True, "ms": int(meta.get("ms", 0)),
            "changed": meta.get("changed") == "1",
            "warm": warm, "overlay": overlay,
            "texts": ts, "state": state_from_texts(ts)}


def catch_seq(max_throws: int = 3) -> dict:
    """Throw/wait/OK as ONE driver round trip (~3 s instead of ~6.4 s).

    The phone polls its own tree for the berry row disappearing and its own
    pixels for the result card, so the ~220 ms adb round trip is paid once
    instead of on every poll.

    Returns {"ok", "throws", "caught", "map_back", "ms"}.
    """
    cmd = f"catchseq {int(max_throws)}"
    raw = drive(cmd, timeout=40.0)
    if not raw.startswith("OK") and ensure_driver():
        raw = drive(cmd, timeout=40.0, retry=False)
    if not raw.startswith("OK"):
        return {"ok": False, "raw": raw, "throws": 0, "caught": False,
                "map_back": False, "ms": 0}
    meta = dict(kv.split("=", 1) for kv in raw.split()[2:] if "=" in kv)
    return {"ok": True,
            "throws": int(meta.get("throws", 0)),
            "caught": meta.get("ended") == "1",
            "map_back": meta.get("map") == "1",
            "warm": int(meta.get("warm", 0)) / 10.0,
            "ms": int(meta.get("ms", 0))}


def scan() -> dict:
    """On-device object scan (screenshot stays on the phone).

    Returns {"ok", "ms", "w", "h", "objects":[{x,y,var,orange,violet,kind}]}.
    Classification thresholds live here so they can be tuned without rebuilding
    the APK.
    """
    raw = drive("scan")
    if raw.startswith("ERR noshot") and restart_driver():
        raw = drive("scan", retry=False)
    if not raw.startswith("OK"):
        return {"ok": False, "raw": raw, "objects": []}
    head = raw.splitlines()[0]
    meta = dict(kv.split("=") for kv in head.split()[2:] if "=" in kv)
    objs = []
    for line in raw.splitlines()[1:]:
        p = line.split()
        if len(p) < 8 or p[0] != "obj":
            continue
        x, y, var, o100, v100, hw10, ring = (int(v) for v in p[1:8])
        orange, violet = o100 / 100.0, v100 / 100.0
        # A PokéStop is an orange/violet tower standing inside a pale ground
        # ring.  Requiring BOTH kills the two failure modes seen on real
        # frames: purple/blue Pokémon matching the stop colour, and white
        # Pokémon matching the ring.
        if ring >= RING_MIN and orange >= STOP_ORANGE:
            kind = "stop_free"
        elif ring >= RING_MIN and violet >= STOP_VIOLET:
            kind = "stop_spun"
        else:
            kind = "spawn"
        objs.append({"x": x, "y": y, "var": var, "orange": orange,
                     "violet": violet, "hw": hw10 / 10.0,
                     "ring": ring / 100.0, "kind": kind})
    return {"ok": True, "ms": int(meta.get("ms", 0)),
            "w": int(meta.get("w", 0)), "h": int(meta.get("h", 0)),
            "objects": objs}


def clickables(leftmax: int = 130) -> list[dict]:
    """Enumerate clickable nodes in the left strip, ordered top-to-bottom.

    The PGSharp nearby list has no text at all, so this is the only way to
    address its entries: by data-layer enumeration order.
    """
    raw = drive(f"clickables {leftmax}")
    if not raw.startswith("OK"):
        return []
    out = []
    for line in raw.splitlines()[1:]:
        if " " not in line:
            continue
        idx, rest = line.split(" ", 1)
        if not idx.isdigit():
            continue
        p = rest.split("|")
        if len(p) < 5:
            continue
        try:
            l, t, r, b = (int(v) for v in p[3].split(","))
        except ValueError:
            continue
        out.append({"i": int(idx), "cls": p[0].rsplit(".", 1)[-1],
                    "text": p[1], "desc": p[2],
                    "l": l, "t": t, "r": r, "b": b,
                    "cx": (l + r) // 2, "cy": (t + b) // 2})
    return out


def index_click(i: int, leftmax: int = 130) -> str:
    """Click the i-th clickable node in the left strip (1-based), by ACTION_CLICK."""
    return drive(f"index_click {i} {leftmax}")


def click(label: str, exact=False) -> bool:
    """Layer-level click: find the node by its own text, tap its centre."""
    n = find(label, exact=exact)
    if n is None:
        return False
    import pgo_bot as B
    B.tap(n["cx"], n["cy"])
    return True


def node_info(label: str) -> str:
    """Driver-side description of one node (clickable/checkable/checked/bounds)."""
    return drive(f"info {label}")


def toggle(label: str) -> str:
    """Semantic toggle: ACTION_CLICK on the Switch that owns <label>.

    Works for rows scrolled off-screen, where coordinate taps are impossible.
    """
    return drive(f"toggle {label}")


def click_node(label: str) -> str:
    """Semantic click on the clickable ancestor of <label> (no coordinates)."""
    return drive(f"clicknode {label}")


def leave_raid(ns: list[dict] | None = None) -> bool:
    """R5 guard: never join a 團體戰.  Close the sheet with its X and nothing else.

    The raid sheet's close button is the X at the bottom centre of the card
    (measured: 539,2011 on this 1080x2160 device).  We deliberately never touch
    對戰 / 私人小組 / 使用250MP.
    """
    ns = nodes() if ns is None else ns
    if state(ns) != "raid":
        return False
    import pgo_bot as B
    B.tap(539, 2011)
    time.sleep(1.5)
    return True


def guard() -> str:
    """Refuse to play if the current interface is a raid; otherwise report it."""
    from pgo_rules import RuleViolation, assert_no_raid
    ns = nodes()
    st = state(ns)
    assert_no_raid(st)
    return st


def pixel_state() -> str:
    import pgo_bot as B
    img = B.grab()
    return B.screen_state(img)


def bench(n: int = 5) -> dict:
    """How much faster is the layer than a screenshot?"""
    import pgo_bot as B
    tl, tp = [], []
    for _ in range(n):
        t0 = time.time(); nodes(); tl.append(time.time() - t0)
        t0 = time.time(); B.grab(); tp.append(time.time() - t0)
    return {"layer_ms": round(1000 * sum(tl) / n, 1),
            "screencap_ms": round(1000 * sum(tp) / n, 1),
            "speedup": round((sum(tp) / n) / (sum(tl) / n), 1)}


def verify(rounds: int = 12, gap: float = 1.0) -> int:
    """Sample both sources; every sample is appended to a report file."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    agree = 0
    print(f"{'#':>3} {'layer':<14} {'pixels':<10} {'mon':<34} match")
    for i in range(rounds):
        ns = nodes()
        ls = state(ns)
        ps = pixel_state()
        data = mon(ns) if ls == "encounter" else {}
        # the pixel classifier only distinguishes encounter/result/map, so only
        # compare on those three; overlays are layer-only knowledge.
        comparable = ps in ("encounter", "result", "map")
        if comparable:
            ok = (ls == ps) or (ls == "encounter" and ps == "encounter")
        else:
            ok = None
        agree += 1 if ok else 0
        rec = {"i": i, "t": round(time.time(), 3), "layer": ls, "pixels": ps,
               "match": ok, "mon": data}
        with REPORT.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        print(f"{i:>3} {ls:<14} {ps:<10} {str(data):<34} {ok}")
        time.sleep(gap)
    print(f"\nagreement {agree}/{rounds} -> {REPORT}")
    return 0 if agree == rounds else 1


# ----------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("state"); s.set_defaults(f=lambda a: (print(state()), 0)[1])
    s = sub.add_parser("mon"); s.set_defaults(f=lambda a: (print(json.dumps(mon(), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("menu"); s.set_defaults(f=lambda a: (print(json.dumps(menu_items(), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("toggles"); s.set_defaults(f=lambda a: (print(json.dumps(toggles(), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("values"); s.set_defaults(f=lambda a: (print(json.dumps(values(), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("feed"); s.set_defaults(f=lambda a: (print(json.dumps(feed_entries(), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("click")
    s.add_argument("label")
    s.set_defaults(f=lambda a: (print(click(a.label)), 0)[1])
    s = sub.add_parser("info")
    s.add_argument("label")
    s.set_defaults(f=lambda a: (print(node_info(a.label)), 0)[1])
    s = sub.add_parser("toggle")
    s.add_argument("label")
    s.set_defaults(f=lambda a: (print(toggle(a.label)), 0)[1])
    s = sub.add_parser("clicknode")
    s.add_argument("label")
    s.set_defaults(f=lambda a: (print(click_node(a.label)), 0)[1])
    s = sub.add_parser("clickables")
    s.add_argument("--leftmax", type=int, default=130)
    s.set_defaults(f=lambda a: (print(json.dumps(clickables(a.leftmax), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("index_click")
    s.add_argument("i", type=int)
    s.add_argument("--leftmax", type=int, default=130)
    s.set_defaults(f=lambda a: (print(index_click(a.i, a.leftmax)), 0)[1])
    s = sub.add_parser("guard"); s.set_defaults(f=lambda a: (print(guard()), 0)[1])
    s = sub.add_parser("snapshot"); s.set_defaults(f=lambda a: (print(json.dumps(snapshot(), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("stops"); s.set_defaults(f=lambda a: (print(json.dumps(stop_status(), ensure_ascii=False, indent=2)), 0)[1])
    s = sub.add_parser("position"); s.set_defaults(f=lambda a: (print(json.dumps(position(), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("joystick"); s.set_defaults(f=lambda a: (print(joystick()), 0)[1])
    s = sub.add_parser("scan"); s.set_defaults(f=lambda a: (print(json.dumps(scan(), ensure_ascii=False)), 0)[1])
    s = sub.add_parser("leave-raid"); s.set_defaults(f=lambda a: (print(leave_raid()), 0)[1])
    s = sub.add_parser("dump")
    s.add_argument("--grep", default=None)
    s.set_defaults(f=lambda a: (dump(a.grep), 0)[1])
    s = sub.add_parser("bench"); s.add_argument("-n", type=int, default=5)
    s.set_defaults(f=lambda a: (print(json.dumps(bench(a.n))), 0)[1])
    s = sub.add_parser("verify")
    s.add_argument("--rounds", type=int, default=12)
    s.add_argument("--gap", type=float, default=1.0)
    s.set_defaults(f=lambda a: (verify(a.rounds, a.gap), 0)[1])
    args = ap.parse_args()
    return args.f(args)


def dump(grep=None):
    ns = nodes()
    print(f"nodes={len(ns)}")
    for n in ns:
        line = f"{n['cls']}|{n['text']}|{n['desc']}|{n['l']},{n['t']},{n['r']},{n['b']}|{n['flags']}"
        if grep is None or grep in line:
            print(line)


if __name__ == "__main__":
    raise SystemExit(main())
