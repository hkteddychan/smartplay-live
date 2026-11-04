# DEV_STATUS.md — ESP32 CYD SmartPLAY Live

> Last updated: 2026-11-04 (feature/browse-page @ 83092a1)

## Branch / commits
- Branch: `feature/browse-page`
- No git remote configured (local commits only).
- Latest: `83092a1 chore(esp32): remove touch debug print; commit website Noto Sans TC font stack`

## Hardware
- Board: ESP32-2432S028R (CYD), 320x240 ILI9341, COM8, IP 10.45.131.27.
- WiFi Plan A: `Tidy Home` (97470738) then `Teddy Pixel` (teddychan).
- Speaker: GPIO26 via ESP32 internal I2S DAC left channel (legacy driver/i2s.h), quiet beep (amp 4000).
- Touch: XPT2046 on independent VSPI bus (SCK25/MISO39/MOSI32/CS33).

## Features implemented
- Push (port 9000) removed entirely; 1-minute poll of changes-eve.json is sole notification path.
- Notify home: release alerts with date+time+venue+facility; next-poll countdown refreshes every 5s.
- Browse page: 3 regions (香港/九龍/新界), 早/午/晚 time periods, sport selection overlay, Play/Pause chip (▶/⏸), compact 5-row layout, ●可訂 marker, all dates sorted nearest→farthest with pagination.
- Lightweight JSON parser for per-sport 7d files.
- Font subset (venue_font.h, 373 glyphs) covers browse.json + 7d venue names; short glyphs centered.
- Alert card background dark slate (0x2124); top filter chips use drawUTF8 + borders.
- UX: loading spinner, touch click feedback (chip flash), swipe gestures (page/district), bottom tab nav (通知/瀏覽).
- Serial commands: b p r s t o O u g n a h l v B A.

## Pending / next
- Website browse simulator update to match new chip UI (external smartplay-live site; not in this repo).
- UX ideas: favorites, notification history, settings page, backlight sleep, offline cache (see docs/ESP32-BRAINSTORM.md).
- Update DEV_STATUS.md on GitHub once remote is configured.

## OTA (over-the-air)
- ArduinoOTA enabled: hostname `smartplay-cyd`, password `smartplay`, port 3232.
- Custom `partitions.csv`: two 1.5MB app slots (app0/app1) for safe OTA.
- Tested end-to-end: espota upload succeeded, board rebooted into new firmware without cable.
- `python tools/check-browse-font-coverage.py` → no missing chars.
- `python tools/check-cjk-coverage.py` → (legacy chat firmware) not applicable.
- No PlatformIO CLI available in this environment; firmware not compiled here.
