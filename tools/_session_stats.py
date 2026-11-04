import json
from collections import Counter

lines = open(r'tools/pgo_sessions/20261101_134712/events.jsonl', encoding='utf-8').readlines()
print('total events:', len(lines))
screens = Counter(json.loads(l)['screen'] for l in lines)
acts = Counter(json.loads(l)['action']['type'] for l in lines)
print('states:', dict(screens))
print('actions:', dict(acts))
for idx in [0, len(lines) // 2, -1]:
    e = json.loads(lines[idx])
    print(f"  {e['i']:>4d} {e.get('screen'):10s} {e['action']['type']:5s} t={e['t']:.0f}")
