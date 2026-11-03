#!/usr/bin/env python3
"""Generate ESP32-friendly compact feeds from the repo's data/*.json mirror.

Input : data/{sport}.json  (full LCSD open-data mirror, 3-9MB each, refreshed by Cloudflare Worker every 15 min)
Output: esp32/*.json       (compact, tens of KB, designed for ESP32 + ArduinoJson)

Schema (positional arrays, short):
  index.json        -> {"g": generated_hk, "s": {sport: {"t": today_rows, "d": seven_day_rows, "f": filesize}}}
  today.json        -> {"g": ..., "d": ["YYYY-MM-DD", "YYYY-MM-DD"], "sports": {sport: rows}}
                      rows = [[venueIdx, districtIdx, dateIdx, startMin, endMin, courts], ...]
                      venues = ["場地名", ...], districts = ["區名", ...]
  {sport}-7d.json   -> {"g": ..., "v": venues, "s": districts, "d": dates, "r": rows}
Only rows with Available_Courts > 0 are emitted.
"""
import json, os, sys
from datetime import datetime, timedelta, timezone

HK = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)          # repo root
DATA = os.path.join(ROOT, 'data')
OUT = HERE
SPORTS = ['badminton', 'basketball', 'volleyball', 'tennis', 'turf-soccer-pitch']

now = datetime.now(HK)
today = now.date()
dates_window = [(today + timedelta(days=i)).isoformat() for i in range(7)]
date_idx = {d: i for i, d in enumerate(dates_window)}
gen_hk = now.strftime('%Y-%m-%d %H:%M')

def to_min(t):
    h, m = t.split(':')
    return int(h) * 60 + int(m)

def compact_rows(records, include_7d):
    """records -> (venues, districts, rows). rows=[vIdx,dIdx,dateIdx,startMin,endMin,courts]"""
    venues, districts = {}, {}
    vlist, dlist, rows = [], [], []
    date_range = dates_window if include_7d else dates_window[:2]
    dset = set(date_range)
    for r in records:
        d = (r.get('Available_Date') or '').strip()
        if d not in dset:
            continue
        try:
            courts = int(r.get('Available_Courts') or 0)
        except ValueError:
            continue
        if courts <= 0:
            continue
        v = (r.get('Venue_Name_TC') or '').strip()
        dist = (r.get('District_Name_TC') or '').strip()
        st = (r.get('Session_Start_Time') or '')[:5]
        en = (r.get('Session_End_Time') or '')[:5]
        if not v or len(st) != 5:
            continue
        vi = venues.get(v)
        if vi is None:
            vi = len(vlist); venues[v] = vi; vlist.append(v)
        di = districts.get(dist)
        if di is None:
            di = len(dlist); districts[dist] = di; dlist.append(dist)
        rows.append([vi, di, date_idx[d], to_min(st), to_min(en), courts])
    return vlist, dlist, rows

index = {'g': gen_hk, 's': {}}
today_payload = {'g': gen_hk, 'd': dates_window[:2], 'sports': {}}

for sport in SPORTS:
    src = os.path.join(DATA, f'{sport}.json')
    if not os.path.exists(src):
        print(f'⚠️  skip {sport}: no mirror file')
        continue
    with open(src, encoding='utf-8') as f:
        records = json.load(f)
    v7, d7, r7 = compact_rows(records, include_7d=True)
    # today-only (first 2 window dates: today + tomorrow)
    vt, dt, rt = compact_rows(records, include_7d=False)

    # per-sport 7d file
    f7 = {'g': gen_hk, 'v': v7, 's': d7, 'd': dates_window, 'r': r7}
    name7 = f'{sport}-7d.json'
    with open(os.path.join(OUT, name7), 'w', encoding='utf-8') as f:
        json.dump(f7, f, ensure_ascii=False, separators=(',', ':'))
    kb7 = os.path.getsize(os.path.join(OUT, name7)) / 1024

    today_payload['sports'][sport] = {'v': vt, 's': dt, 'r': rt}
    index['s'][sport] = {'t': len(rt), 'd': len(r7), 'f': [f'{sport}-today' in ('',), name7][1]}
    print(f'✅ {sport}: today {len(rt)} rows / 7d {len(r7)} rows, 7d file {kb7:.0f} KB')

# today.json — all sports today+tomorrow
with open(os.path.join(OUT, 'today.json'), 'w', encoding='utf-8') as f:
    json.dump(today_payload, f, ensure_ascii=False, separators=(',', ':'))
kb_today = os.path.getsize(os.path.join(OUT, 'today.json')) / 1024
print(f'📦 today.json: {kb_today:.0f} KB')

# index.json — tiny manifest
index['files'] = ['today.json'] + [f'{s}-7d.json' for s in index['s']]
with open(os.path.join(OUT, 'index.json'), 'w', encoding='utf-8') as f:
    json.dump(index, f, ensure_ascii=False, separators=(',', ':'))
print(f'📦 index.json: {os.path.getsize(os.path.join(OUT, "index.json"))/1024:.1f} KB')
print(f'🕐 generated: {gen_hk} HKT')
