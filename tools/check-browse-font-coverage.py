import re
src=open('firmware/esp32_smartplay/cyd_browse.h').read()
s=open('firmware/esp32_smartplay/venue_font.h').read()
m=re.search(r'cjk_cp\[CJK_COUNT\]\s*=\s*\{([^}]*)\}', s, re.S)
nums=m.group(1).replace(',',' ').split()
cps=set(int(x,0) for x in nums if x.strip() and x.strip()!='0')
strs=re.findall(r'"([^"]*)"', src)
missing=set()
for st in strs:
    for ch in st:
        if ord(ch)>0x7F and ord(ch) not in cps:
            missing.add(ch)
print('missing chars:', sorted(missing))