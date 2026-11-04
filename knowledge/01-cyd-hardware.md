# 01 — CYD Hardware (ESP32-2432S028R)

## Identity

Confirmed by boot log on the real device:

```
ets Jul 29 2019 12:21:46
rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)
=== CYD smoke test ===
display reported: 320 x 240
```

- Classic ESP32 (not S3/C3): ROM `Jul 29 2019`, boot mode `SPI_FAST_FLASH_BOOT`.
- USB-serial chip: **CH340** (`USB\VID_1A86&PID_7523`), enumerates as a COM port
  that **changes between replugs** (seen as COM7, then COM8). Resolve it by
  hardware ID, not by number — see `esp32_port.py`.
- 4 MB flash, **no PSRAM**. Budget: app partition ~1.9 MB with `min_spiffs.csv`
  (3 MB with `huge_app.csv`).

## Pinout

### Display (SPI)
| Signal | GPIO |
| :--- | :--- |
| MISO | 12 |
| MOSI | 13 |
| SCLK | 14 |
| CS | 15 |
| DC | 2 |
| RST | -1 (tied to EN) |
| Backlight | 21 (PWM-able) |

### Touch (XPT2046 — **separate SPI bus**)
| Signal | GPIO |
| :--- | :--- |
| CLK | 25 |
| MISO | 39 |
| MOSI | 32 |
| CS | 33 |
| IRQ | 36 |

> This is the single most important CYD gotcha. The touch controller is **not** on the
> display SPI. TFT_eSPI's built-in `getTouch()` often works "sometimes"; a dedicated
> `SPIClass touchSPI(VSPI)` is the reliable pattern.

### Other
| Thing | GPIO | Note |
| :--- | :--- | :--- |
| RGB LED R/G/B | 4 / 16 / 17 | **active LOW** |
| Speaker amp | 26 | onboard amp, 2P JST on back |
| LDR (some variants) | 34 | analog |
| SD card CS | 5 | shares display SPI |
| BOOT button | 0 | `INPUT_PULLUP`, LOW = pressed |

## Panel variants (the "white screen" trap)

CYD boards ship with **ILI9341** *or* **ST7789** panels, and it does not track the
model number reliably.

- Our board works with `ILI9341_2_DRIVER` + `TFT_WIDTH=240 TFT_HEIGHT=320` + `rotation 1`.
- If you get a white/blank screen: switch to `ST7789_DRIVER`.
- If colours look inverted (negative): `tft.invertDisplay(true)`.
- Some variants put the backlight on **GPIO 27** instead of 21.

## Touch calibration

TFT_eSPI `setTouch()` style (used by the NEON SERPENT firmware):

```c
uint16_t cal[5] = { 300, 3800, 300, 3800, 1 };  // {xMin,xMax,yMin,yMax,rot}
tft.setTouch(cal);
```

XPT2046_Touchscreen style (used by the chat toy, separate bus):

```c
#define TOUCH_MIN_X 200
#define TOUCH_MAX_X 3900
#define TOUCH_MIN_Y 200
#define TOUCH_MAX_Y 3900
int x = constrain(map(p.x, TOUCH_MIN_X, TOUCH_MAX_X, 0, SCR_W), 0, SCR_W - 1);
int y = constrain(map(p.y, TOUCH_MIN_Y, TOUCH_MAX_Y, 0, SCR_H), 0, SCR_H - 1);
```

If taps are offset or axis-swapped, adjust the MIN/MAX constants (and check
`ts.setRotation()` matches `tft.setRotation()`).

## Power / audio notes

- No battery; USB powered.
- Speaker is **optional hardware** — many boards are sold without the JST speaker.
  Code must never assume audio is present.
- Arduino core 3.x removed `ledcSetup()` / `ledcAttachPin()`.
  Use `tone(pin, freq, ms)` / `noTone(pin)` or `ledcAttach()` / `ledcWriteTone()`.
- `analogWrite(21, 0..255)` works for backlight brightness on core 3.x.

### Which GPIO drives the speaker amp (settled 2026-11-04)

The amp is fed from **GPIO26**, and it is an *analog* input, so it must be driven
by the ESP32's **internal DAC through I2S** — `tone()` on GPIO26 is not the way.

The mapping is not in most datasheets; it is in the Arduino core's legacy
`driver/i2s_types_legacy.h`:

```c
I2S_DAC_CHANNEL_RIGHT_EN = 1,  // DAC channel 0 -> GPIO25
I2S_DAC_CHANNEL_LEFT_EN  = 2,  // DAC channel 1 -> GPIO26  <-- the amp
```

So the CYD uses `i2s_set_dac_mode(I2S_DAC_CHANNEL_LEFT_EN)`, which is exactly what
the canonical CYD "HelloRadio" example does and what the community pin map
lists next to "IO26 | Connected to amp". GPIO25 is the *other* DAC channel and
also the XPT2046 touch clock, so it must be left alone.

> The legacy `driver/i2s.h` API is required — the newer `driver/i2s_std.h` has
> **no** DAC mode at all. It is deprecated but still present in core 3.3.12.

Speaker socket: **P4**, 2P 1.25 mm Molex PicoBlade, labelled "SPEAK", on the
back of the board. Verified working implementation:
`firmware/esp32_smartplay/cyd_audio.h`.
