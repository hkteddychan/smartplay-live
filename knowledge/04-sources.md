# 04 — Sources Worth Re-Reading

## The reference implementation (what we adapted)

**kano92-dir/CYD-AI-CHAT** — MIT
<https://github.com/kano92-dir/CYD-AI-CHAT>
Single-file Arduino sketch (~44 KB) for ESP32-2432S028R:
OpenRouter free models, model fallback, touch keyboard, chat bubbles,
NVS memory, personas, languages, RGB LED, NTP clock.

## The community hub

**witnessmenow/ESP32-Cheap-Yellow-Display** — the canonical CYD repo
<https://github.com/witnessmenow/ESP32-Cheap-Yellow-Display>
Pinouts, variants (ILI9341 vs ST7789), display comparisons, buying links,
and a Discord. Start here for any hardware question.

## Other good CYD projects (ideas to steal)

| Repo | What it shows |
| :--- | :--- |
| <https://github.com/ddxfish/CYD-ESP32-LVGL-touch-example> | LVGL + every peripheral (LED, buzzer, LDR, SD, touch) |
| <https://github.com/ropg/LVGL_CYD> | Clean LVGL multi-screen UI, auto-detects ILI9341/ST7789 |
| <https://github.com/gabe-sky/CYD_Doodler> | ESP-NOW mesh between two CYDs, RSSI proximity |
| <https://github.com/billism1/esp32-cheap-yellow-display-examples> | Sand / particles / fluid sim, dual-core tricks |
| <https://github.com/calint/bam> | Tile-map game engine, ~30 FPS on CYD |
| <https://github.com/Pontiac76/CYD-Clock> | NTP clock, SD-card config, OTA-ish config server |
| <https://github.com/tobymarks/esp32-ai-monitor> | LVGL 9 arcs/bars, USB-serial JSON from a companion app |
| <https://github.com/bitbank2/CYD_Projects> | More CYD examples |

## Libraries

| Library | Use |
| :--- | :--- |
| [Bodmer/TFT_eSPI](https://github.com/Bodmer/TFT_eSPI) | display driver (2.5.43) |
| [PaulStoffregen/XPT2046_Touchscreen](https://github.com/PaulStoffregen/XPT2046_Touchscreen) | touch on its own SPI bus |
| [bblanchon/ArduinoJson](https://github.com/bblanchon/ArduinoJson) | v7 `JsonDocument` |
| [lvgl/lvgl](https://github.com/lvgl/lvgl) | if you want a real widget UI |
| [rzeldent/esp32-smartdisplay](https://github.com/rzeldent/esp32-smartdisplay) | board definitions for many Sunton panels |

## AI backends

| Service | Note |
| :--- | :--- |
| <https://openrouter.ai/keys> | one key, many models, `:free` slugs |
| <https://openrouter.ai/models?max_price=0> | live list of free models |

> Free slugs rotate. If every model returns 429, the list in `MODELS[]` is stale —
> refresh it from the page above.

## Reading list (concepts)

- TFT_eSPI viewport + sprite: <https://github.com/Bodmer/TFT_eSPI/wiki>
- ArduinoJson 7 migration (v6 `DynamicJsonDocument` → v7 `JsonDocument`)
- ESP32 NVS (`Preferences`) key/value limits
- `WiFiClientSecure::setInsecure()` trade-offs
