# 02 — Professional AI-Chat Firmware Patterns

Distilled from [kano92-dir/CYD-AI-CHAT](https://github.com/kano92-dir/CYD-AI-CHAT) (MIT),
then adapted into `firmware/esp32_cyd_chat`.

## 1. Explicit state machine

```cpp
enum AppState { ST_WIFI_LIST, ST_KEYBOARD, ST_CONNECTING, ST_CHAT, ST_SETTINGS, ST_MODEL };
AppState state;
bool needRedraw = true;
```

Rules that keep it clean:
- Touch handlers **only mutate state**, never draw.
- `loop()` redraws when `needRedraw` is set.
- Blocking work (WiFi connect, HTTP) happens in its own state, never inside a touch handler.

## 2. Layered on-screen keyboard

```cpp
enum KbLayer { L_LOWER, L_UPPER, L_SYM };
const char* rowsLower[3] = { "qwertyuiop", "asdfghjkl", "zxcvbnm" };
const char* rowsSym[3]   = { "1234567890", "+-*/=<>^_", "()[]{}.,?" };
```

- Row 0: 10 keys full width.
- Row 1: 9 keys, 32 px each, centered.
- Row 2: shift + 7 keys + backspace.
- Row 3: layer toggle + space + confirm.
- Keys are rebuilt into a `std::vector<KeyBox>` on every layer change, then hit-tested
  by rectangle. Simple and reliable.
- Long-press backspace: repeat after 450 ms, then every 120 ms.

**Math twist:** the symbol layer is `+-*/=<>^_` and `()[]{}.,?` instead of `-_./:;,@#`
and `()&%+=?`, because this device answers equations.

## 3. Chat bubbles that fit 320×240

- Word-wrap with `tft.textWidth()` (not character counting) so proportional fonts work.
- Bubble width = longest wrapped line + 14 px padding, capped at `SCR_W - avatar - 24`.
- Draw inside a viewport so scrolling clips cleanly:

```cpp
tft.setViewport(0, CHAT_AREA_Y, SCR_W, CHAT_AREA_H);
tft.fillScreen(C_BG);
// ... draw messages offset by -chatScroll ...
tft.resetViewport();
```

- Content height is precomputed; scrollbar height = `areaH * areaH / contentH`.
- Drag-to-scroll with a 40 ms redraw throttle; only scroll when `abs(dy) > 5`.

## 4. Memory in NVS

```cpp
prefs.begin("cydmath", false);
JsonDocument d;                 // ArduinoJson 7
JsonArray arr = d.to<JsonArray>();
o["r"] = (role == R_USER) ? 0 : 1;
o["t"] = text;
String s; serializeJson(d, s);
if (s.length() <= 3900) prefs.putString("chatlog", s);
```

- NVS string values have a practical size limit (~4000 B). Cap the log.
- Store only the last 10 messages; drop `R_ERR` entries.
- Restore on boot → conversation survives power cycles.

## 5. OpenRouter with automatic fallback

```cpp
ModelOpt MODELS[] = {
  { "Gemma 4 31B",  "google/gemma-4-31b-it:free" },
  { "GPT-OSS 120B", "openai/gpt-oss-120b:free"   },
  ...
};
```

- Try `selModel` first, then every other model.
- On `429` (free-tier rate limit) → next model.
- On `401` → stop immediately (bad key).
- `WiFiClientSecure` + `client.setInsecure()` avoids shipping a CA bundle
  (acceptable for a toy; pin a CA for production).
- Send only the last `API_HISTORY = 6` messages as context to keep tokens low.
- `max_tokens = 320` because the screen can't show more anyway.

## 6. UTF-8 → ASCII folding

The built-in TFT_eSPI font is ASCII-only. Turkish/Cyrillic/CJK would render as boxes,
so the reference project folds text before drawing:

```cpp
String foldASCII(const String& in);   // decode UTF-8 code points -> ASCII
```

Keep the **real UTF-8** for the API payload; fold only for the display.
CJK needs an actual CJK font (VLW) — folding turns it into `?`.

## 7. Physical status LED

| Colour | Meaning |
| :--- | :--- |
| Blue | thinking / connecting |
| Green | reply received |
| Red | error (401 / 429 / no WiFi) |

Cheap, and makes the device feel alive during a 5–20 s API call.

## 8. Personas as system prompts

```cpp
Persona PERSONAS[] = {
  { "Tutor", "Solve step by step..." },
  { "Short", "Final result first..." },
  { "Exam",  "Fastest valid method..." },
  { "Proof", "Explain why from definitions..." },
};
```

Plus a global language/format rule appended to every persona
(e.g. "plain ASCII math, no LaTeX, under 300 chars").
