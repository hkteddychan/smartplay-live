"""Quick font comparison at 16px for the CYD CJK bitmap font."""
from PIL import Image, ImageDraw, ImageFont

SAMPLE = "數學導師：微積分證明與最優化"
FONTS = [
    (r"C:\Windows\Fonts\msjh.ttc", 0, "JhengHei"),
    (r"C:\Windows\Fonts\NotoSansTC-VF.ttf", 0, "NotoSansTC"),
    (r"C:\Windows\Fonts\mingliu.ttc", 0, "MingLiU"),
    (r"C:\Windows\Fonts\kaiu.ttf", 0, "Kaiu"),
]

SCALE = 4
PAD = 4
CELL = 16

rows = []
for path, idx, name in FONTS:
    try:
        font = ImageFont.truetype(path, CELL, index=idx)
    except Exception as exc:  # noqa: BLE001
        print(f"{name}: FAILED {exc}")
        continue
    w = CELL * len(SAMPLE)
    img = Image.new("L", (w, CELL), 0)
    d = ImageDraw.Draw(img)
    for i, ch in enumerate(SAMPLE):
        d.text((i * CELL, 0), ch, font=font, fill=255, anchor="lt")
    rows.append((name, img))
    print(f"{name}: ok")

if rows:
    out = Image.new("L", (max(r[1].width for r in rows), (CELL + PAD) * len(rows)), 0)
    y = 0
    for name, img in rows:
        out.paste(img, (0, y))
        y += CELL + PAD
    out = out.resize((out.width * SCALE, out.height * SCALE), Image.NEAREST)
    out.save("docs/font-compare.png")
    print("saved docs/font-compare.png")
