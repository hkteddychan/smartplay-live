# ESP32 Development Progress Report

Generated from the consolidated workspace `D:\Teddy\Opencode\ESP32`
(original working directory referenced in `knowledge/07-verify-results.md` was
`D:\Teddy\Opencode\Firsttry`; that folder is no longer present — its notes
have been folded into this workspace's `knowledge/` base).

## 1. Hardware (confirmed on real device)

- Board: **ESP32-2432S028R "CYD"** — classic ESP32 (ROM `Jul 29 2019`),
  2.8" 240×320 ILI9341, XPT2046 resistive touch, 4 MB flash, **no PSRAM**.
- USB-serial: **CH340** (`USB\VID_1A86&PID_7523`), enumerates as **COM8**
  (was COM7 — the number changes between replugs; COM3–COM6 are Bluetooth decoys).
- Display SPI: MISO 12 / MOSI 13 / SCLK 14 / CS 15 / DC 2 / BL 21.
- Touch is on a **separate SPI bus**: CLK 25 / MISO 39 / MOSI 32 / CS 33 / IRQ 36.
- RGB LED R/G/B = 4/16/17 (active LOW); speaker amp on GPIO 26 (optional).
- **Speaker amp wiring settled**: GPIO26 is the ESP32's I2S internal DAC
  *left* channel (`I2S_DAC_CHANNEL_LEFT_EN` → DAC channel 1 → GPIO26); the
  other DAC channel lands on GPIO25, which is the touch clock. Needs the
  legacy `driver/i2s.h` API — the new `i2s_std.h` has no DAC mode.
- Toolchain: Python 3.13.5, PlatformIO Core 6.2.0, espressif32 8.0.0,
  Arduino core **3.3.12**. Note `pio` is not on PATH — use `python -m platformio`.
- Display driver: `ILI9341_2_DRIVER`, rotation 1 → 320×240 landscape.
- Boot log verified: `[BOOT] screen 320 x 240 (rot 1)`, WiFi `192.168.31.34`.

## 2. Firmware projects

### A. `firmware/esp32_cyd_controller` — NEON SERPENT 3D wireless controller
- WebSocket **server** on port 8787; game page connects as client.
- Wi-Fi captive-portal setup (AP `NEON-SERPENT-CYD` / `serpent3d`, `192.168.4.1`),
  credentials persisted in NVS; long-press BOOT 3 s to reset.
- Touch direction pad (FWD/BACK/LT/RT, Y+/Y-, PAUSE, AUTO), BOOT button shortcuts.
- Splash image (`splash_data.h`, RLE) + "HELLO TEDDY!" banner + greeting melody (GPIO 26).
- RGB LED status (blue slow blink = setup, solid = linked).
- Verified by `test/esp32-deep-test.mjs`: hello received, join accepted,
  agent snake present in state, reconnect test done.

### B. `firmware/esp32_cyd_chat` — AI Math Tutor (touch chat toy)
- State machine (WiFi list → keyboard → connecting → chat → settings → model).
- Layered on-screen keyboard (lower/upper/symbol; symbol layer `+-*/=<>^_`).
- Chat bubbles with word-wrap, drag-to-scroll, viewport clipping.
- NVS memory (`cydmath`): last 10 messages survive reboot; cap ~3900 B.
- OpenRouter free models with automatic fallback on 429, 401 stops immediately.
- `max_tokens = 320`, sends last 6 messages as context, `setInsecure()` TLS.
- Personas (Tutor/Short/Exam/Proof), RGB LED status, `tone()` beeps.
- Demo mode when no API key → playable immediately.
- Verified boot on COM7: display init, WiFi connect, serial `demo` command works.
- Flash: 1.29 MB → **1.50 MB after CJK (76.2 % of 1.9 MB)**; RAM 15.4 %.

### C. `firmware/esp32_socks5_proxy` — CYD as SOCKS5 relay
- RFC 1929 username/password sub-negotiation (standard clients work).
- Session state machine: PH_GREETING → PH_AUTH → PH_REQUEST → PH_RELAY.
- Hardening: pipelining leftover handling, per-ATYP length validation,
  blocking DNS/connect, EOF handling, 120 s idle timeout, WiFi reconnect +
  `server.begin()` re-run, `WiFi.setSleep(false)`.
- LED status: green ready, blue blink active, red no WiFi.
- Verified by `tools/test-socks5.py`: greeting 0502 OK, auth 0100 OK,
  CONNECT example.com:80 OK, HTTP 200 over tunnel, bad password rejected 01 01.
  Standard `curl`: HTTP 200 in 0.2 s, HTTPS 200 in 0.45 s.
- Reverse relay (NAT traversal): ESP32 dials out to VM every 5 s, pool of
  spare channels (`tools/cyd_relay.py`), LAN SOCKS stays available simultaneously.

### D. CJK font support (`knowledge/06-cjk-font.md`)
- 16×16 1-bit bitmap font, Big5 symbols + Level 1, **5,905 glyphs**, ~196 KB flash.
- Source: Microsoft JhengHei 16 px (chosen over Noto Sans TC / MingLiU / Kaiu).
- Generator: `tools/make-cjk-font.py`; coverage check: `tools/check-cjk-coverage.py`
  (169 non-ASCII chars used, **all covered**).
- Firmware helpers: `cjkIndex`, `utf8Advance`, `charWidth`, `drawUTF8`,
  `measureUTF8`, `wrapText` (UTF-8 aware; breaks anywhere for CJK).
- AI answers in Traditional Chinese; math stays ASCII. ASCII uses TFT_eSPI font 2.
- Live test (`esp32_cjk_test.py`): send `cjk` over serial → Chinese message injected;
  no crash/reboot, WiFi stays up.

### E. `firmware/esp32_smartplay` — SmartPLAY Live 放場通知器 (new, currently flashed)
- Source brief: `https://hkteddychan.github.io/smartplay-live/esp32/BUILD_HANDOFF.md`
  (generic DevKit sketch v2.1 "release-only") — ported to the CYD with the screen
  and the board speaker.
- ESP32 works **standalone**: WiFi → release detected → beep + screen card.
- **Two paths, deduped**: **PUSH** (board dials out to the VM on :9000, the VM
  pushes the release the moment the feed changes) and **POLL** (HTTPS GET
  `changes-eve.json` every **60 s**) — an event never beeps twice.
- Push protocol: `CYD PUSH 1` → `OK` → `RELEASE {json}` per line.
  `tools/cyd_relay.py` now serves both the SOCKS relay (`CYD RELAY 1`) and the
  push channel on the same port; `tools/cyd_push_test.py` proves the path
  end-to-end locally.
- The **VM resolves venue→district** (using `index.json` to find the 7-day
  feeds, because `today.json` only lists venues that currently have courts),
  so the board never downloads the 28–36 KB session feed.
- Release rule: `(kind=="chg" && new>old) || kind=="new"`; taken-away slots
  never beep. First poll is baseline-only → a reboot never false-alarms.
- CJK font is a **subset generated from the live feed** — 323 glyphs / 10 KB
  (`tools/make-venue-font.py`) instead of the chat toy's 5,905 glyphs / 196 KB.
- Status screen shows last/next poll, feed version, releases seen and the push
  link state; alert card shows sport, district, venue, time range, facility and
  old→new courts. Tap to dismiss, auto-dismiss after 120 s.
- **Blocked on the VM side**: Oracle Cloud Security Group still closes TCP 9000,
  so the board is currently running on the 1-minute poll fallback.
- Serial commands: `b` beep, `p` audio probe (3 pitches), `r` refresh,
  `a` show alert, `h` home, `l` list releases, `v` venue map status.

## 3. Testing & tooling

- `esp32_probe.py` — pulse DTR/RTS, capture ROM banner, identify board.
- `esp32_monitor.py` — serial monitor with clean reset pulse.
- `esp32_chat_test.py`, `esp32_cjk_test.py` — automated serial tests.
- `esp32_socks_log.py`, `esp32_socks_watch.py`, `esp32_watch_raw.py` — proxy diagnostics.
- `esp32_port.py` — resolves the CH340 COM port from its PNP id (the number
  changes between replugs); explicit arg > `ESP32_PORT` env > auto-detect.
  All the serial helpers above use it, so they can never open an unrelated
  device. `test/test_esp32_port.py` — 12 pytest cases, 0.35 s.
- `test/esp32-device-simulator.mjs`, `test/esp32-deep-test.mjs`, `test/cdp-driver.mjs`
  — WebSocket + browser-driven deep tests (deep test log/results present).
- `tools/make-cjk-font.py`, `tools/check-cjk-coverage.py`, `tools/make-splash.mjs`,
  `tools/render-splash-preview.mjs`.
- `tools/make-venue-font.py` — generates the feed-derived CJK subset used by
  the smartplay firmware (316 glyphs / 10 KB).
- `tools/test-socks5.py`, `tools/cyd_relay.py`, `tools/cyd_relay.service`.

## 4. Open items / next steps

1. Chinese **input**: keyboard is ASCII only; Chinese can only come from AI or serial.
2. OTA: no OTA partition with `min_spiffs.csv`; need `default.csv` or custom table.
3. Streaming responses: currently one blocking POST; needs chunked reads + redraw.
4. Audio: speaker optional; `tone()` beeps harmless if absent.
5. "雷神" branding question still open (Thor vs neural vs Chinese answers).
6. CJK charset extensions: Level 2 (~13 k glyphs, +416 KB) or Simplified Chinese.
7. Touch calibration constants may need tuning per board.
8. Panel variant handling (ST7789 / GPIO 27 backlight) documented but not auto-detected.
9. Free OpenRouter slugs rotate; refresh `MODELS[]` if all return 429.

## 5. Source documents

- `knowledge/01-cyd-hardware.md` … `knowledge/07-socks5-proxy.md`,
  `knowledge/05-decisions.md`, `knowledge/07-verify-results.md`.
- `docs/data-layer.md`, `docs/unlock-report.md`.
- Firmware READMEs under `firmware/*/README.md`.
