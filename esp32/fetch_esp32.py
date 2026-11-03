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
import json, os, sys, subprocess
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

# ============================================================
# 「最新改變」diff — compare current data/*.json vs previous mirror version
# Uses git history: previous mirror commit = last commit touching data/{sport}.json
# Output: esp32/changes.json (also served as ESP32 live-change feed)
# ============================================================
def prev_version(sport):
    """Return (prev_ts, dict) of the previous committed version of data/{sport}.json, or None."""
    try:
        # last 2 commits that touched this file: [0]=current, [1]=previous
        log = subprocess.run(
            ['git', 'log', '--format=%H %cI', '-n', '2', '--', f'data/{sport}.json'],
            cwd=ROOT, capture_output=True, text=True, timeout=30).stdout.strip().splitlines()
        if len(log) < 2:
            return None
        sha, ts = log[1].split(' ', 1)
        blob = subprocess.run(['git', 'show', f'{sha}:data/{sport}.json'],
                              cwd=ROOT, capture_output=True, timeout=60)
        if blob.returncode != 0:
            return None
        return ts, json.loads(blob.stdout.decode('utf-8'))
    except Exception as e:
        print(f'⚠️  prev_version({sport}): {e}')
        return None

def diff_sport(records, prev):
    """records/prev -> list of change tuples:
       [sport, date, venue, location, startMin, endMin, kind, old, new]
       kind: 'new' (new available slot), 'gone' (slot disappeared), 'chg' (courts changed)"""
    def kmap(rows):
        out = {}
        for r in rows:
            v = (r.get('Venue_Name_TC') or '').strip()
            loc = (r.get('Facility_Location_Name_TC') or '').strip()
            d = (r.get('Available_Date') or '').strip()
            st = (r.get('Session_Start_Time') or '')[:5]
            en = (r.get('Session_End_Time') or '')[:5]
            if not v or len(st) != 5:
                continue
            try:
                c = int(r.get('Available_Courts') or 0)
            except ValueError:
                continue
            out[(d, v, loc, st, en)] = c
        return out
    cur_m, prev_m = kmap(records), kmap(prev)
    changes = []
    for k, c in cur_m.items():
        d, v, loc, st, en = k
        if k not in prev_m:
            if c > 0:
                changes.append([d, v, loc, to_min(st), to_min(en), 'new', 0, c])
        elif prev_m[k] != c:
            changes.append([d, v, loc, to_min(st), to_min(en), 'chg', prev_m[k], c])
    for k, c in prev_m.items():
        if k not in cur_m:
            d, v, loc, st, en = k
            changes.append([d, v, loc, to_min(st), to_min(en), 'gone', c, 0])
    changes.sort(key=lambda x: (x[0], x[3]))
    return changes

changes_payload = {'g': gen_hk, 'prev': {}, 'sports': {}}
total_changes = 0
for sport in SPORTS:
    if sport not in index['s']:
        continue
    src = os.path.join(DATA, f'{sport}.json')
    with open(src, encoding='utf-8') as f:
        records = json.load(f)
    pv = prev_version(sport)
    if pv is None:
        print(f'ℹ️  {sport}: no previous version to diff')
        changes_payload['sports'][sport] = []
        continue
    prev_ts, prev_records = pv
    prev_hk = datetime.fromisoformat(prev_ts).astimezone(HK).strftime('%Y-%m-%d %H:%M')
    changes_payload['prev'][sport] = prev_hk
    ch = diff_sport(records, prev_records)
    changes_payload['sports'][sport] = ch
    total_changes += len(ch)
    kinds = {}
    for x in ch:
        kinds[x[5]] = kinds.get(x[5], 0) + 1
    print(f'✅ {sport}: diff vs {prev_hk} -> {len(ch)} changes {kinds}')

with open(os.path.join(OUT, 'changes.json'), 'w', encoding='utf-8') as f:
    json.dump(changes_payload, f, ensure_ascii=False, separators=(',', ':'))
kb = os.path.getsize(os.path.join(OUT, 'changes.json')) / 1024
print(f'📦 changes.json: {kb:.0f} KB, {total_changes} changes')

# ============================================================
# ESP32 evening feed — changes-eve.json
# 「最新改變」ESP32 精簡版：
#   - 淨係晚上場次（session start >= 18:00）
#   - 排除最後一日（day-7 未開放預訂，LCSD 半夜成批放 -> 假警報）
#   - diff 範圍同樣只計可預訂日（今日..今日+5）
# ============================================================
EVE_START_MIN = 18 * 60   # 1080

def is_eve_bookable(change):
    """change = [date, venue, loc, startMin, endMin, kind, old, new]"""
    d, sm = change[0], change[3]
    return sm >= EVE_START_MIN and d in bookable_dates

bookable_dates = set(dates_window[:6])   # 今日..今日+5（day-7 = dates_window[6] 排除）

eve_payload = {'g': gen_hk, 'prev': {}, 'sports': {}}
total_eve = 0
for sport in SPORTS:
    if sport not in index['s']:
        continue
    ch = changes_payload['sports'].get(sport, [])
    eve = [c for c in ch if is_eve_bookable(c)]
    # record the prev window only when evening changes exist
    if eve and sport in changes_payload['prev']:
        eve_payload['prev'][sport] = changes_payload['prev'][sport]
    eve_payload['sports'][sport] = eve
    total_eve += len(eve)
    if eve:
        print(f'🌙 {sport}: {len(eve)} evening changes (from {len(ch)})')

with open(os.path.join(OUT, 'changes-eve.json'), 'w', encoding='utf-8') as f:
    json.dump(eve_payload, f, ensure_ascii=False, separators=(',', ':'))
kb_eve = os.path.getsize(os.path.join(OUT, 'changes-eve.json')) / 1024
print(f'📦 changes-eve.json: {kb_eve:.1f} KB, {total_eve} evening changes')

print(f'🕐 generated: {gen_hk} HKT')
