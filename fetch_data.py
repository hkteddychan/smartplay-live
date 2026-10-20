#!/usr/bin/env python3
"""SmartPLAY Live Data mirror — fetch all 6 open-data datasets, compact + save.
Run by GitHub Actions every 15 min; commits only changed files."""
import json, urllib.request, os, time
from datetime import datetime, timezone

BASE = 'https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data'
DATASETS = ['badminton', 'basketball', 'volleyball', 'tennis', 'turf-soccer-pitch', 'activity-prog']
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(OUT, exist_ok=True)

def fetch(name):
    url = f'{BASE}/{name}/file'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 SmartPlay-Live-Mirror', 'Accept-Encoding': 'gzip'})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

total = 0
for ds in DATASETS:
    for attempt in range(3):
        try:
            data = fetch(ds)
            payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            with open(os.path.join(OUT, f'{ds}.json'), 'wb') as f:
                f.write(payload)
            n = len(data)
            total += n
            print(f'✅ {ds}: {n} records, {len(payload)/1024:.0f} KB')
            break
        except Exception as e:
            print(f'⚠️  {ds} attempt {attempt+1}: {e}')
            time.sleep(5)
    else:
        print(f'❌ {ds}: failed all attempts')

meta = {
    'generated_utc': datetime.now(timezone.utc).isoformat(),
    'source': BASE,
    'datasets': DATASETS,
    'total_records': total,
}
with open(os.path.join(OUT, 'meta.json'), 'w', encoding='utf-8') as f:
    json.dump(meta, f, ensure_ascii=False, indent=1)
print(f'\n📦 Total: {total} records → {OUT}/')