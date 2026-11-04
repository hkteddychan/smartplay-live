#pragma once
// ---------------------------------------------------------------------------
// UTF-8 / CJK text helpers for the SmartPLAY CYD firmware.
//
// ASCII is drawn with TFT_eSPI font 2 (16 px tall, variable 3-9 px wide).
// CJK comes from the subset bitmap table in venue_font.h (16x16, 1 bit).
// Both share the same baseline, so mixed strings line up.
// ---------------------------------------------------------------------------
#include <Arduino.h>
#include <TFT_eSPI.h>

#include "venue_font.h"

extern TFT_eSPI tft;

inline int cjkIndex(uint16_t cp) {
  int lo = 0, hi = (int)CJK_COUNT - 1;
  while (lo <= hi) {
    int mid = (lo + hi) >> 1;
    uint16_t v = cjk_cp[mid];
    if (v == cp) return mid;
    if (v < cp) lo = mid + 1;
    else hi = mid - 1;
  }
  return -1;
}

// Decode one code point starting at byte i; returns the next byte index.
inline int utf8Advance(const String &s, int i, uint16_t &cp) {
  int n = (int)s.length();
  uint8_t c = (uint8_t)s[i];
  if (c < 0x80) { cp = c; return i + 1; }
  if ((c & 0xE0) == 0xC0 && i + 1 < n) {
    cp = ((c & 0x1F) << 6) | ((uint8_t)s[i + 1] & 0x3F);
    return i + 2;
  }
  if ((c & 0xF0) == 0xE0 && i + 2 < n) {
    cp = ((uint16_t)((c & 0x0F) << 12)) | (((uint16_t)((uint8_t)s[i + 1] & 0x3F)) << 6) |
         ((uint8_t)s[i + 2] & 0x3F);
    return i + 3;
  }
  cp = '?';
  return i + 1;
}

inline int charWidth(uint16_t cp) {
  if (cp < 0x80) return tft.textWidth(String((char)cp), 2);
  return CJK_GLYPH_W;
}

inline void drawUTF8Char(uint16_t cp, int x, int y, uint16_t fg, uint16_t bg) {
  if (cp < 0x20) return;
  if (cp < 0x80) {
    tft.setTextColor(fg, bg);
    tft.setTextDatum(TL_DATUM);
    tft.drawChar((uint16_t)cp, x, y, 2);
    return;
  }
  int idx = cjkIndex(cp);
  if (idx >= 0) {
    tft.drawBitmap(x, y, cjk_bits + (uint32_t)idx * CJK_GLYPH_BYTES,
                   CJK_GLYPH_W, CJK_GLYPH_H, fg, bg);
  } else {
    // glyph missing from the subset — draw a hollow box so it is obvious
    tft.drawRect(x + 3, y + 3, CJK_GLYPH_W - 6, CJK_GLYPH_H - 6, fg);
  }
}

inline void drawUTF8(const String &s, int x, int y, uint16_t fg, uint16_t bg) {
  int i = 0;
  while (i < (int)s.length()) {
    uint16_t cp;
    i = utf8Advance(s, i, cp);
    drawUTF8Char(cp, x, y, fg, bg);
    x += charWidth(cp);
  }
}

inline int measureUTF8(const String &s) {
  int total = 0, i = 0;
  while (i < (int)s.length()) {
    uint16_t cp;
    i = utf8Advance(s, i, cp);
    total += charWidth(cp);
  }
  return total;
}

// Draw a CJK string at 2x scale (32 px tall) — used for the venue headline.
inline void drawUTF8Scaled(const String &s, int x, int y, uint16_t fg, uint16_t bg, int scale) {
  int i = 0;
  while (i < (int)s.length()) {
    uint16_t cp;
    i = utf8Advance(s, i, cp);
    if (cp < 0x80) {
      // ASCII has no bitmap here — fall back to the normal renderer
      drawUTF8Char(cp, x, y, fg, bg);
      x += charWidth(cp) * scale;
      continue;
    }
    int idx = cjkIndex(cp);
    if (idx < 0) {
      drawUTF8Char(cp, x, y, fg, bg);
      x += CJK_GLYPH_W * scale;
      continue;
    }
    const uint8_t *g = cjk_bits + (uint32_t)idx * CJK_GLYPH_BYTES;
    for (int row = 0; row < CJK_GLYPH_H; row++) {
      uint16_t bits = ((uint16_t)g[row * 2] << 8) | g[row * 2 + 1];
      for (int col = 0; col < CJK_GLYPH_W; col++) {
        bool on = (bits & (1 << (15 - col))) != 0;
        if (on) tft.fillRect(x + col * scale, y + row * scale, scale, scale, fg);
        else if (bg != fg) tft.fillRect(x + col * scale, y + row * scale, scale, scale, bg);
      }
    }
    x += CJK_GLYPH_W * scale;
  }
}

inline int measureUTF8Scaled(const String &s, int scale) {
  return measureUTF8(s) * scale;
}

// Truncate to maxW pixels, appending an ellipsis when it does not fit.
inline String fitUTF8(const String &s, int maxW) {
  if (measureUTF8(s) <= maxW) return s;
  String dots = "…";
  int dotsW = measureUTF8(dots);
  String out;
  int w = 0, i = 0;
  while (i < (int)s.length()) {
    uint16_t cp;
    int next = utf8Advance(s, i, cp);
    int cw = charWidth(cp);
    if (w + cw + dotsW > maxW) break;
    out += s.substring(i, next);
    w += cw;
    i = next;
  }
  return out + dots;
}
