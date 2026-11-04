import sys, time, math
sys.path.insert(0, 'tools')
import numpy as np
import pgo_bot as B, pgo_layer as L, pgo_walk as W, pgo_direct as D
import _avatar as A, _sprites as S

def snap():
    img = B.grab()
    feet = None
    got = A.find_avatar(img)
    if got:
        feet = (got[0], got[1] + A.FEET_OFFSET)
    sp = S.find_sprites(img, feet)
    return img, feet, sp

print('state', L.state())
img, feet, sp = snap()
print('feet', feet, 'sprites', len(sp))
for s in sp[:6]:
    print('  ', s)

# pick nearest sprite to feet
if feet and sp:
    near = min(sp, key=lambda t: math.hypot(t[0]-feet[0], t[1]-feet[1]))
    print('target', near)
    for i in range(4):
        d = math.hypot(near[0]-feet[0], near[1]-feet[1])
        print('iter', i, 'dist_px', round(d,1))
        if d <= 150:
            print('tap', near[0], near[1])
            r = L.tapwait(near[0], near[1], 1200, nowarm=True)
            print('  ->', r['state'], 'changed', r['changed'], 'texts', r['texts'][:8])
            if r['state'] == 'encounter':
                print('ENCOUNTER! mon:', L.mon())
                res = L.catch_seq()
                print('catch:', res)
                break
            if r['state'] != 'map':
                D.back_to_map()
            break
        dx, dy = near[0]-feet[0], near[1]-feet[1]
        n = math.hypot(dx, dy)
        W.walk(dx/n*25.0, dy/n*25.0, settle=1.5)
        time.sleep(0.5)
        img, feet, sp = snap()
        if not feet or not sp:
            print('lost track'); break
        near = min(sp, key=lambda t: math.hypot(t[0]-feet[0], t[1]-feet[1]))
        print('  now target', near, 'feet', feet)
print('final state', L.state())
