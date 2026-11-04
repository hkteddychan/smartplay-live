# patches/ — source-side patches for the SmartPLAY Live repo

## v3.0 — no patch needed

The upstream repo (`hkteddychan/smartplay-live`) already publishes the feed the
ESP32 browse page consumes:

- **`esp32/browse.json`** — `https://hkteddychan.github.io/smartplay-live/esp32/browse.json`
  Schema: `{"g","k":[icons],"d":["MM-DD 周"],"v":["venue|district"],"r":[[vIdx,sportIdx,dateIdx,start,end,courts]]}`
  ~6 KB, ~200 evening rows, 6 pre-formatted dates, 5 sports.

- **`esp32/changes-eve.json`** — release notifications (unchanged).

So **no source patch is required** for the browse feature.  The ESP32 firmware
pulls `browse.json` directly.

## `fetch_esp32.py.orig`

The pristine upstream generator, kept for reference / diff regeneration.  Not
applied anywhere.
","path":"D:\\Teddy\\Opencode\\ESP32\\patches\\README.md