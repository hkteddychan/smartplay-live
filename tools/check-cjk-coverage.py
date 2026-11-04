"""Check that every CJK character used in the firmware exists in cjk_font.h."""
import re
import sys

INO = "firmware/esp32_cyd_chat/esp32_cyd_chat.ino"
HDR = "firmware/esp32_cyd_chat/cjk_font.h"

src = open(INO, encoding="utf-8").read()

# strip comments so we only check real string literals
src_nc = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
src_nc = re.sub(r"//[^\n]*", "", src_nc)

used = {ord(ch) for ch in src_nc if ord(ch) > 0x7F}

hdr = open(HDR, encoding="utf-8").read()
m = re.search(r"static const uint16_t cjk_cp\[CJK_COUNT\] = \{(.*?)\};", hdr, re.S)
have = {int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{4})", m.group(1))}

missing = sorted(used - have)
print(f"characters used in firmware : {len(used)}")
print(f"glyphs in font table        : {len(have)}")
if missing:
    print("MISSING:", "".join(chr(c) for c in missing))
    print("codes  :", ", ".join(f"U+{c:04X}" for c in missing))
    sys.exit(1)
print("OK - every character is covered")
