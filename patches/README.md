# patches/ — source-side patches for the SmartPLAY Live repo

The upstream repo (`hkteddychan/smartplay-live`) is **not** on this machine, so
changes to it are delivered as patches instead of commits.

## `evening-7d.patch` — new ESP32 browse feed

Adds `esp32/evening-7d.json`: the next 7 days of **evening** slots only
(start ≥ 18:00, courts ≥ 1) as a flat table the ESP32 can hold in RAM.

```
r rows = [districtIdx, venueIdx, sportIdx, dateIdx, startMin, endMin, courts]
```

Every district in the source data is listed, including the ones with no
evening slots, so the ESP32's district picker can show them as empty.

### Apply

```bash
git clone https://github.com/hkteddychan/smartplay-live
cd smartplay-live
git apply /path/to/evening-7d.patch
python esp32/fetch_esp32.py          # regenerate the feeds
```

Verified: `git apply --check` passes against the pristine upstream tree, and
the patched generator was run end-to-end here (`test/test_fetch_esp32_run.py`).

### Expected output

```
🌙 evening-7d.json: 7.2 KB, 198 evening rows, 18 districts
```

Real feed today: **4,325 slots over 7 days → only 198 of them are evening**,
which is why the browse page can keep the whole dataset in ~2 KB of RAM.

## Files

| File | What it is |
| :-- | :-- |
| `evening-7d.patch` | the diff to apply to the upstream repo |
| `evening_feed.py` | new file the patch adds (`esp32/evening_feed.py`) |
| `fetch_esp32.py` | the patched upstream generator, for reference |
| `fetch_esp32.py.orig` | the pristine upstream file, so the diff can be regenerated |
