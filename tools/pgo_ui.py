"""UI-hierarchy driver for the Mix2S PGSharp build.

`uiautomator dump` exposes the game's on-screen labels with exact bounds, so
elements can be located by *name* instead of by pixel template matching.
That is both far more robust and much cheaper than a screenshot round-trip.

    python tools/pgo_ui.py dump                    # list labelled nodes
    python tools/pgo_ui.py find Feeds              # locate one label
    python tools/pgo_ui.py tap Feeds               # tap a label
    python tools/pgo_ui.py tap 981 153             # tap raw coordinates
    python tools/pgo_ui.py nodes                   # dump only clickable nodes
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

SERIAL = "1bbd5689"
REMOTE = "/sdcard/pgo_ui.xml"

# Labels we care about, with fallbacks in case the language changes.
KNOWN = {
    "map": ["地圖", "Map"],
    "speed": ["km/h", "速度"],
    "autowalk": ["自動行走", "Auto Walk", "Walk"],
    "feeds": ["Feeds", "Nearby"],
    "favorites": ["收藏夾", "Favorites"],
    "teleport": ["傳送", "Teleport"],
    "settings": ["設置", "Settings"],
    "cancel": ["取消", "Cancel"],
    "ok": ["確定", "OK", "Confirm"],
    "close": ["關閉", "Close", "X"],
}


def adb(*args, binary=False):
    r = subprocess.run(["adb", "-s", SERIAL, *args], capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode("utf-8", "replace").strip())
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def dump() -> str:
    """Pull the current view hierarchy as XML text."""
    adb("shell", "uiautomator", "dump", REMOTE)
    return adb("shell", "cat", REMOTE)


def nodes(xml_text: str | None = None):
    xml_text = xml_text or dump()
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for n in root.iter("node"):
        m = re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", n.get("bounds") or "")
        if not m:
            continue
        x1, y1, x2, y2 = (int(v) for v in m.groups())
        out.append({
            "text": n.get("text") or "",
            "desc": n.get("content-desc") or "",
            "cls": (n.get("class") or "").split(".")[-1],
            "rid": n.get("resource-id") or "",
            "clickable": n.get("clickable") == "true",
            "cx": (x1 + x2) // 2, "cy": (y1 + y2) // 2,
            "w": x2 - x1, "h": y2 - y1,
        })
    return out


def find(label: str, exact=False):
    """Find a node by text or content-desc (case-insensitive, substring)."""
    cands = KNOWN.get(label.lower(), [label])
    ns = nodes()
    for want in cands:
        w = want.lower()
        for n in ns:
            t = (n["text"] or n["desc"]).lower()
            if (t == w) if exact else (w in t and t):
                return n
    # fall back: any node whose text contains the raw label
    for n in ns:
        if label.lower() in (n["text"] or n["desc"]).lower():
            return n
    return None


def clickable_nodes():
    return [n for n in nodes() if n["clickable"] and not n["text"] and not n["desc"]]


def tap(x, y):
    adb("shell", "input", "tap", str(int(x)), str(int(y)))


def cmd_dump():
    for n in nodes():
        label = (n["text"] or n["desc"]) or "(no label)"
        print(f"  ({n['cx']:>5},{n['cy']:>5}) {n['w']:>5}x{n['h']:<5} "
              f"click={str(n['clickable']):<5} {n['cls']:<18} {label[:50]}")
    return 0


def cmd_nodes():
    for n in clickable_nodes():
        print(f"  ({n['cx']:>5},{n['cy']:>5}) {n['w']:>5}x{n['h']:<5} {n['cls']}")
    return 0


def cmd_find(label):
    n = find(label)
    if not n:
        print(f"not found: {label}")
        return 1
    print(f"{label}: ({n['cx']},{n['cy']}) {n['w']}x{n['h']} class={n['cls']} "
          f"text={n['text']!r} desc={n['desc']!r}")
    return 0


def cmd_tap(target):
    if target.isdigit():
        tap(int(target), int(sys.argv[3]))
    else:
        n = find(target)
        if not n:
            print(f"not found: {target}")
            return 1
        print(f"tap {target} -> ({n['cx']},{n['cy']})")
        tap(n["cx"], n["cy"])
    time.sleep(1.2)
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "dump":
        return cmd_dump()
    if cmd == "nodes":
        return cmd_nodes()
    if cmd == "find":
        return cmd_find(sys.argv[2])
    if cmd == "tap":
        return cmd_tap(sys.argv[2])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
