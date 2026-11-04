# 06 — CJK Bitmap Font Pipeline

How Chinese text gets onto a 320×240 TFT with no CJK font in TFT_eSPI.

## The problem

- TFT_eSPI's built-in fonts are **ASCII only** (font 1/2/4/6/7/8).
- Smooth `.vlw` fonts work but need the Processing "Create_font" tool and are
  awkward to subset for CJK.
- Full Unicode CJK is ~20,000 glyphs → far too much flash.

## The solution

A **16×16 1-bit bitmap font** for Big5 symbols + Level 1 (~5,900 glyphs),
generated offline with Pillow from a Windows TTF, stored as a `const` array in
flash, and drawn with `tft.drawBitmap()`.

| Item | Value |
| :--- | :--- |
| Source font | `C:\Windows\Fonts\msjh.ttc` (Microsoft JhengHei) at 16 px |
| Charset | Big5 `A140–C67E` (symbols + level 1) + a few math extras |
| Glyphs | 5,905 |
| Bytes/glyph | 32 (16 rows × 2 bytes, MSB first) |
| Bitmap | 184.5 KB |
| Index | 11.5 KB (`uint16_t` sorted code points) |
| Total flash | ~196 KB |
| Firmware flash | 1.29 MB → **1.50 MB** (76.2% of 1.9 MB) |
| RAM | unchanged (15.4%) — the table stays in flash |

## Why JhengHei

Compared four fonts at 16 px (`docs/font-compare.png`):

| Font | Verdict |
| :--- | :--- |
| **Microsoft JhengHei** | **chosen** — boldest strokes, best on a small LCD |
| Noto Sans TC | too thin, strokes break up |
| MingLiU | mushy at 16 px |
| Kaiu (標楷) | calligraphic, hard to read small |

## Generator

`tools/make-cjk-font.py`

```python
for hi in range(0xA1, 0xC7):                    # Big5 symbol + level-1 ranges
    for lo in list(range(0x40,0x7F)) + list(range(0xA1,0xFF)):
        ch = bytes([hi, lo]).decode("big5")     # Python has big5 built in
        cps.add(ord(ch))
```

Then each glyph is rasterized into a 16×16 `Image.new("1", ...)`, packed
MSB-first, and emitted as:

```c
static const uint16_t cjk_cp[CJK_COUNT];                 // sorted, binary search
static const uint8_t  cjk_bits[CJK_COUNT * 32];          // glyph bitmaps
```

Run it:

```bash
python tools/make-cjk-font.py
```

It also writes `docs/cjk-chat-preview.png`, a faithful mock of the chat screen
(same font, same 8 px ASCII / 16 px CJK advance, same wrapping).

## Firmware side

```cpp
#include "cjk_font.h"

int cjkIndex(uint16_t cp);          // binary search over cjk_cp[]
int utf8Advance(s, i, cp);          // decode one UTF-8 code point
int charWidth(cp);                  // ASCII -> tft.textWidth(ch,2); CJK -> 16
void drawUTF8Char(cp, x, y, fg, bg);
void drawUTF8(s, x, y, fg, bg);
int  measureUTF8(s);
std::vector<String> wrapText(s, maxW);   // UTF-8 aware, breaks anywhere for CJK
```

- ASCII still uses TFT_eSPI font 2 (8 px advance, crisp, already tuned).
- CJK uses `tft.drawBitmap(x, y, cjk_bits + idx*32, 16, 16, fg, bg)`
  — the 2-colour overload clears the cell background, so no ghosting.
- Missing glyph → hollow box, so gaps are obvious instead of silent.
- Wrapping breaks **anywhere** for CJK (no spaces) and measures per character;
  bitmap fonts have no kerning, so per-char sums are exact.

## Verification

```bash
python tools/check-cjk-coverage.py
```

Scans the `.ino` for every non-ASCII character and confirms each one exists in
`cjk_font.h`. Current result: **169 used, all covered**.

Live test (`esp32_cjk_test.py`): send `cjk` over serial → injects a Chinese
message; no crash, no reboot, WiFi stays up.

## Extending the charset

- Add Big5 Level 2: change the loop to `range(0xA1, 0xFA)` → ~13,000 glyphs,
  ~416 KB (firmware would be ~1.7 MB, still under 1.9 MB).
- Add Simplified Chinese: use a GB2312/GBK charset loop instead.
- Add more symbols: append to `EXTRA` in the generator.
- Smaller glyphs: set `CELL = 12` → 24 bytes/glyph, ~30% less flash, harder to read.
