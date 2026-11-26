# Core Logic

## Overview

Pure, side-effect-free logic that two layers need: the Compose screens (to
show the filtered list) and the background poller (to decide whether a session
matches the user's watchlist). Nothing here touches Android APIs, so all of it
is unit tested.

## Interface

### `FilterEngine` ([FilterEngine.kt](./FilterEngine.kt))
- `fun minuteOf(time: String): Int` — minutes from midnight, or `-1` when the
  timestamp is malformed
- `fun apply(slots: List<SlotEntity>, f: SlotFilter): List<SlotEntity>`
- `fun sort(slots: List<SlotEntity>, mode: SortMode, userLat: Double?, userLon: Double?): List<SlotEntity>`
- `fun distanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double`
- `fun isPrimeTime(date: String, startTime: String): Boolean`
- `fun heatmap(slots: List<SlotEntity>): IntArray`

### `SlotFilter` ([FilterEngine.kt](./FilterEngine.kt))
`district`, `date`, `fromMinute`, `toMinute`, `onlyAvailable`, `search`.

### `SortMode` ([FilterEngine.kt](./FilterEngine.kt))
`TIME`, `AVAILABILITY`, `DISTANCE`.

### `ReleaseDetector` ([ReleaseDetector.kt](./ReleaseDetector.kt))
- `fun key(s: SlotEntity): String` — the session identity used for diffing
- `fun detect(previous: List<SlotEntity>, current: List<SlotEntity>): List<SlotEntity>` —
  sessions whose available count went up

## Invariants

- `apply` ANDs every predicate: exact district, exact date, a half-open
  start-time window (`fromMinute <= m < toMinute`), `available > 0` when
  requested, and a case-insensitive substring of **venue or facility** for the
  search term.
- `minuteOf` returns `-1` for a malformed timestamp, so a bad time can never
  satisfy a time filter.
- The default filter window is the whole day (`0..1440`).
- `heatmap` returns 24 hourly buckets counting only rows with `available > 0`
  and a parsable start time.
- Prime time is Monday–Friday and 19:00–22:00; weekends and unparsable dates
  are not prime time.
- `SortMode.DISTANCE` falls back to sorting by venue name when the user
  location is unknown.
- `ReleaseDetector.detect` returns nothing when `previous` is empty: the first
  snapshot only establishes a baseline. A session is a release when its
  available count is strictly greater than before, so a session that loses
  courts or stays the same is not a release.

## Side Effects

- None. Pure functions over data classes.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
- `FilterEngineTest` (9 tests) and `ReleaseDetectorTest` (6 tests).
