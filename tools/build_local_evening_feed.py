#!/usr/bin/env python3
"""Build a local esp32/evening-7d.json from the live 7-day feeds.

The upstream repo does not publish evening-7d.json yet (the patch in
patches/ adds it), so this script reconstructs the same payload locally so
the ESP32 browse page can be tested against real data over the LAN.

It goes through the *same* build_evening_feed() the source patch uses, so
the file the board parses locally is byte-for-byte the shape it will get
once the patch lands.

Usage:
  python tools/build_local_evening_feed.py          # writes dist/evening-7d.json
  python tools/build_local_evening_feed.py --serve  # also serve dist/ on :8080
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import os
import socketserver
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "patches"))

from evening_feed import build_evening_feed  # noqa: E402

BASE = "https://hkteddychan.github.io/smartplay-live/esp32/"
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist")


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def fmt_min(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def seven_day_files() -> dict:
    idx = fetch_json(BASE + "index.json")
    files = {}
    for sport, meta in (idx.get("s") or {}).items():
        files[sport] = meta.get("f")
    return files


def to_raw_records(sport: str, data: dict) -> list:
    """7d compact rows -> the raw LCSD record shape build_evening_feed wants."""
    v = data.get("v") or []
    s = data.get("s") or []
    dates = data.get("d") or []
    out = []
    for row in data.get("r") or []:
        if len(row) < 6:
            continue
        vi, di, dateIdx, sm, em, courts = row
        if not (0 <= vi < len(v) and 0 <= di < len(s) and 0 <= dateIdx < len(dates)):
            continue
        out.append({
            "Available_Date": dates[dateIdx],
            "Available_Courts": str(courts),
            "Venue_Name_TC": v[vi],
            "District_Name_TC": s[di],
            "Facility_Location_Name_TC": "",
            "Session_Start_Time": fmt_min(sm),
            "Session_End_Time": fmt_min(em),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true", help="also serve dist/ on :8080")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    files = seven_day_files()
    records_by_sport = {}
    for sport, fname in files.items():
        records_by_sport[sport] = to_raw_records(sport, fetch_json(BASE + fname))
        print(f"  {sport}: {len(records_by_sport[sport])} raw records")

    # the 7 day window the feed uses
    one = fetch_json(BASE + files[next(iter(files))])
    dates = one.get("d") or []
    gen = fetch_json(BASE + "index.json").get("g", "")

    payload = build_evening_feed(records_by_sport, gen, dates[:7])
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "evening-7d.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(path)
    print(f"✅ {path}: {size} bytes, {len(payload['r'])} evening rows, "
          f"{len(payload['v'])} venues, {len(payload['s'])} districts")

    if args.serve:
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=OUT)
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("0.0.0.0", args.port), handler) as httpd:
            print(f"🌐 serving {OUT} on :{args.port} (ctrl-c to stop)", flush=True)
            try:
                httpd.serve_forever()
            except KeyboardInterrupt:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
