# 03 — Build, Flash, Debug

## Environment (verified on this machine)

| Tool | Version / path |
| :--- | :--- |
| Python | 3.13.5 |
| pyserial | 3.5 |
| PlatformIO Core | 6.2.0 (`python -m platformio`; `pio` is **not** on PATH) |
| Node | v22.17.0 |
| espressif32 platform | 8.0.0 |
| Arduino core | **3.3.12** |
| Board port | **COM7** (CH340) |

> `pio` is not on PATH. Always use `python -m platformio ...`.

## Build

```bash
python -m platformio run -d firmware/esp32_cyd_chat
```

Expected tail:

```
RAM:   [==        ]  15.4% (used 50348 bytes from 327680 bytes)
Flash: [=======   ]  65.7% (used 1291183 bytes from 1966080 bytes)
======================== [SUCCESS] Took 119.73 seconds ========================
```

PowerShell may report `Exited with code 1` even on success — esptool writes progress
to stderr. Judge by `[SUCCESS]`, not the exit code.

## Flash

```bash
python -m platformio run -d firmware/esp32_cyd_chat -t upload --upload-port COM7
```

Look for:

```
Hash of data verified.
Hard resetting via RTS pin...
======================== [SUCCESS] Took 112.04 seconds ========================
```

## Monitor

PlatformIO monitor:

```bash
python -m platformio device monitor --port COM7
```

Or the local helper (also does a clean reset pulse):

```bash
python esp32_monitor.py COM7 14
```

Healthy boot:

```
ets Jul 29 2019 12:21:46
rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)
...
[BOOT] screen 320 x 240 (rot 1)
```

## Probe an unknown board

```bash
python esp32_probe.py --port COM7
```

It pulses DTR/RTS (EN low → boot) and captures the ROM banner, so you can tell
ESP32 vs ESP32-S3 vs nothing at all.

## Find the port

```powershell
[System.IO.Ports.SerialPort]::GetPortNames()
Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'COM\d+' } |
  Select-Object Name, DeviceID
```

Bluetooth serial ports (COM3–COM6 here) are decoys; the CH340 is the real board.

## Verified on this device (2026-10-31)

```
ets Jul 29 2019 12:21:46
rst:0x1 (POWERON_RESET),boot:0x13 (SPI_FAST_FLASH_BOOT)
[BOOT] screen 320 x 240 (rot 1)
[WiFi] connected, IP 192.168.31.35
[YOU] what is 2+2?
[AI] DEMO mode: no API key. Put your OpenRouter key in platformio.ini (CHAT_API_KEY) and rebuild.
```

- Display driver `ILI9341_2_DRIVER` + rotation 1 is correct for this unit.
- WiFi credentials persisted in NVS namespace `cydmath` and auto-reconnected on reboot.
- Serial console works: `demo` enters chat, any other line is sent as a question.
- Speaker beeps use `tone()` (core 3.x); harmless if no speaker is attached.

## Common failures

| Symptom | Cause | Fix |
| :--- | :--- | :--- |
| `UnknownPackageError` for a lib | name not in PlatformIO registry | use the git URL in `lib_deps` |
| Upload fails, "connecting..." forever | not in download mode | hold BOOT, tap RST, release BOOT |
| White screen after flash | ST7789 panel | switch driver define |
| Negative colours | inverted panel | `tft.invertDisplay(true)` |
| Touch dead | touch on display SPI | use separate `SPIClass(VSPI)` |
| Touch offset | calibration | adjust `TOUCH_MIN/MAX_*` |
| Garbage on serial | boot ROM at 74880/115200 mix | reset and read after 200 ms |
