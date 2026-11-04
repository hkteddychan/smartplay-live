# Knowledge Base — ESP32 / CYD / AI Chat

Reusable notes collected while building `firmware/esp32_cyd_chat`.
Everything here was verified against the actual board on **COM7** (CH340).

| File | What's inside |
| :--- | :--- |
| [01-cyd-hardware.md](01-cyd-hardware.md) | Pinout, panel variants, touch bus, RGB LED, speaker, gotchas |
| [02-ai-chat-patterns.md](02-ai-chat-patterns.md) | The professional firmware architecture we copied |
| [03-build-flash-debug.md](03-build-flash-debug.md) | PlatformIO commands, probing, flashing, boot log |
| [04-sources.md](04-sources.md) | GitHub repos and links worth re-reading |
| [05-decisions.md](05-decisions.md) | Why we chose X over Y (and what to revisit) |
| [06-cjk-font.md](06-cjk-font.md) | How Chinese text is rendered (16×16 bitmap pipeline) |
| [07-socks5-proxy.md](07-socks5-proxy.md) | CYD as a SOCKS5 proxy node (protocol, hardening, NAT) |

## The 30-second version

- Board is **ESP32-2432S028R "CYD"**: ESP32-WROOM, 2.8" 240×320 ILI9341, XPT2046 resistive touch, 4 MB flash, no PSRAM.
- Display SPI: MISO 12, MOSI 13, SCLK 14, CS 15, DC 2, BL 21.
- **Touch is on a separate SPI bus**: CLK 25, MISO 39, MOSI 32, CS 33, IRQ 36. Do not share the display bus.
- RGB LED: R 4, G 16, B 17 (active LOW). Speaker amp: GPIO 26.
- Toolchain: PlatformIO Core 6.2.0, espressif32 platform, Arduino core **3.3.12**.
- Build+flash: `python -m platformio run -d firmware/esp32_cyd_chat -t upload --upload-port COM7`.
