# 05 — Decisions & Open Questions

## Decisions made

| Decision | Why | Revisit when |
| :--- | :--- | :--- |
| New project `firmware/esp32_cyd_chat` instead of editing `esp32_cyd_controller` | Don't destroy the working NEON SERPENT game controller | — |
| Separate `SPIClass(VSPI)` for touch | Reliable on CYD; matches the reference project | If touch proves flaky, try TFT_eSPI `getTouch()` with cal `{300,3800,300,3800,1}` |
| `ILI9341_2_DRIVER`, 240×320, rotation 1 | Matches the board's existing smoke test (`320 x 240`) | If screen is white → `ST7789_DRIVER` |
| Landscape 320×240 | Chat lines are wider; keyboard rows fit | — |
| ASCII-only UI + English AI answers | TFT_eSPI built-in font has no CJK glyphs | When a VLW CJK subset font is added |
| `max_tokens = 320` | Screen can't show more; saves quota | If a scrollable long-answer view is added |
| Demo mode when no API key | Toy is playable immediately, no signup | — |
| OpenRouter instead of raw OpenAI | Free models + fallback chain | If you want a local LLM |
| `setInsecure()` on TLS | No CA bundle to ship on a toy | Before any production use |

## Open questions

1. ~~**Chinese output.**~~ **Resolved** — 16×16 bitmap font, 5,905 Big5 level-1
   glyphs, ~196 KB flash. See `06-cjk-font.md`. AI now answers in Traditional
   Chinese; ASCII math stays ASCII.
2. **"雷神" naming.** Ambiguous: Thor theme vs 類神經 (neural) vs Chinese answers.
   Chinese answers are now done; the branding question is still open.
3. **Audio.** Speaker on GPIO 26 is optional hardware. `tone()` beeps are harmless
   if absent.
4. **Streaming.** Currently one blocking POST. Streaming would need chunked reads +
   incremental bubble redraw.
5. **OTA.** No OTA partition with `min_spiffs.csv`. Use `default.csv` or a custom
   partition table with two app slots if OTA is wanted.
6. **Chinese input.** The on-screen keyboard is ASCII only; Chinese text can only
   come from the AI or from the serial port.

## Known-good facts (don't re-derive)

- Board is classic ESP32, 4 MB flash, no PSRAM.
- COM7 = CH340. COM3–COM6 are Bluetooth decoys.
- Arduino core 3.3.12: no `ledcSetup`/`ledcAttachPin`; `tone()` exists.
- `VSPI` = 3, `HSPI` = 2, `FSPI` = 1 on classic ESP32.
- PlatformIO lib name `paulstoffregen/XPT2046_Touchscreen` is **not** in the registry;
  use `https://github.com/PaulStoffregen/XPT2046_Touchscreen.git`.
- PowerShell may print `Exited with code 1` on a successful esptool upload.
