import zipfile, re, collections

APK = r'C:\Users\Teddy\AppData\Local\Temp\pgo.apk'
z = zipfile.ZipFile(APK)

rx = re.compile(rb'[A-Za-z0-9._-]{2,60}(?:\.pokemongo\.com|holoholo|\.internal|\.sandbox|\.test)[A-Za-z0-9._/-]{0,60}')
hits = collections.Counter()
for n in z.namelist():
    if not n.endswith(('.dex', '.arsc', '.so', '.json', '.xml')):
        continue
    try:
        data = z.read(n)
    except Exception:
        continue
    for m in rx.finditer(data):
        hits[m.group(0).decode('latin-1').lower()] += 1

print('--- endpoint-ish strings ---')
for h, c in hits.most_common(40):
    print(f'{c:5d}  {h}')

print('\n--- assets that look like server config ---')
for n in z.namelist():
    if re.search(r'(config|server|endpoint|env)', n, re.I) and not n.endswith('.dex'):
        print(n, z.getinfo(n).file_size)
