# UI Layer

## Overview

All Compose screens, their ViewModels, and the pure filter/sort engine that
turns cached rows into what the user sees. The screens never touch Room or
Retrofit; they read `StateFlow`s from a ViewModel and call its methods.

## Interface

### Screens
- `HomeScreen` ([HomeScreen.kt](./HomeScreen.kt)) — court availability: sport chips,
  search field, filter sheet, heatmap, slot list, pull-to-refresh.
- `ActivitiesScreen` ([ActivitiesScreen.kt](./ActivitiesScreen.kt)) — programme activities:
  district/type filters, search, activity cards, registration deep link.
- `AlertsScreen` ([AlertsScreen.kt](./AlertsScreen.kt)) — push status, ad gate,
  watchlist sports/districts/venues, weekday and time-window filters, quiet
  hours, notification permission.
- `SettingsScreen` ([SettingsScreen.kt](./SettingsScreen.kt)) — about, privacy, cache
  counts, clear-cache confirmation.

### ViewModels
- `HomeViewModel` ([HomeViewModel.kt](./HomeViewModel.kt)) — exposes `loading`, `error`,
  `filter`, `sort`, `sport`, `userLat`, `userLon`, `lastSync`, `all`,
  `districts`, `availableDates`, `visible`, `heatmap`; mutators
  `selectSport`, `setFilter`, `setSearch`, `setSort`, `setLocation`,
  `toggleHour`, `clearFilters`, `refresh`.
- `ActivitiesViewModel` ([ActivitiesViewModel.kt](./ActivitiesViewModel.kt)) — exposes
  `loading`, `error`, `district`, `type`, `search`, `range`, `lastSync`,
  `districts`, `types`, `visible`; mutators `setDistrict`, `setType`,
  `setSearch`, `setRange`, `clearFilters`, `refresh`.
- `SettingsViewModel` ([SettingsViewModel.kt](./SettingsViewModel.kt)) — exposes `clearing`,
  `slotCount`, `activityCount`; `clearCache(onResult)`.

### Pure logic
Shared with the background poller, so it lives in
[../core/](../core/README.md), not here:
- `FilterEngine` — `minuteOf`, `apply`, `sort`, `distanceMeters`,
  `isPrimeTime`, `heatmap`
- `SlotFilter` — `district`, `date`, `fromMinute`, `toMinute`, `onlyAvailable`, `search`
- `SortMode` — `TIME`, `AVAILABILITY`, `DISTANCE`

### Helpers
- `SPORTS` ([HomeScreen.kt](./HomeScreen.kt)) — the five sport keys with labels.
- `DeepLink.openInBrowser(ctx)` ([DeepLink.kt](./DeepLink.kt)) — opens the official site.
- `Context.findActivity()` ([ContextExt.kt](./ContextExt.kt)) — unwraps a hosting `Activity`.

Subdirectories:
- [theme/](./theme/README.md) — Material 3 colour schemes and the app theme

## Invariants

- `FilterEngine.apply` ANDs every predicate: exact district, exact date,
  half-open start-time window (`fromMinute <= m < toMinute`), `available > 0`
  when requested, and a case-insensitive substring of **venue or facility**
  for the search term.
- Search input is debounced by 300 ms before the list is recomputed; the
  filter object keeps the raw text so the field stays in sync.
- `minuteOf` returns `-1` for a malformed timestamp, so a bad time can never
  satisfy a time filter.
- The default filter window is the whole day (`0..1440`).
- `heatmap` returns 24 hourly buckets counting only rows with `available > 0`
  and a parsable start time; `HeatmapCard` sums them pairwise into 12
  two-hour cells.
- Prime time is Monday–Friday and 19:00–22:00; weekends and unparsable dates
  are not prime time.
- `SortMode.DISTANCE` falls back to sorting by venue name when the user
  location is unknown.
- `visible` is a derived `StateFlow` (`combine(all, filter, sort, userLat, userLon)`),
  so Room writes and filter changes both recompose the list. `districts` and
  `heatmap` are derived the same way.
- The heatmap is computed over the **already filtered** rows, so it reflects
  the active filter.
- `districts` comes from the cached rows of the currently selected sport only.
- `selectSport` ignores a repeat selection, and clears the cached rows before
  re-observing.
- `refresh` is a no-op while a refresh is in flight; on failure it exposes the
  fixed message `載入失敗，請檢查網絡連線`, never the raw exception.
- `toggleHour` is idempotent: tapping the active bucket restores the full-day
  window.
- `setLocation` also switches the sort mode to `DISTANCE`.
- The Home list states are mutually exclusive: loading with no rows → skeleton;
  error with no rows → error; no rows at all → "not synced"; rows but nothing
  visible → "no results" with a clear-filters action.
- The offline banner appears only when an error occurred **and** cached rows
  exist; otherwise a relative "更新於" line is shown.
- Activity filters re-issue the Room query for district/type/date range; the
  search term is applied in memory against the activity name or venue.
- `ActivityRange` selects 全部日期 / 未來 7 日 / 未來 30 日; the range is pushed
  into the SQL query as `startDate BETWEEN from AND to`.
- The ad gate is 180 seconds: the reward must be earned first, and the grant
  is only written after the countdown finishes. Leaving the screen cancels the
  countdown and forfeits the grant.
- `SettingsViewModel.clearCache` deletes rows through the DAOs, never by
  deleting the open database file, and reports success through a callback.

## Side Effects

- Navigation: the four routes are hosted by the `NavHost` in
  [../MainActivity.kt](../MainActivity.kt); bottom-bar taps navigate with
  `popUpTo(startDestination) { saveState = true }`.
- Runtime location permission request (`ACCESS_FINE_LOCATION`,
  `ACCESS_COARSE_LOCATION`) and a `FusedLocationProviderClient.lastLocation`
  read.
- Runtime notification permission request (`POST_NOTIFICATIONS`) on API 33+.
- DataStore writes: `WatchlistStore.addSport`, `addDistrict`, `addVenue`,
  `toggleSport`, `setDistricts`, `removeVenue`, `toggleWeekday`,
  `setTimeRange`, `setQuietHours`, `grantPush`, `revokePush`.
- Room writes: `SettingsViewModel.clearCache` clears the `slots` and
  `activities` tables through the DAOs.
- WorkManager scheduling and cancellation happen inside
  [../alerts/WatchlistStore.kt](../alerts/WatchlistStore.kt) when push is
  granted or revoked.
- Browser launches: the official SmartPLAY site, and the activity
  `TC_URL` for registration.
- System share sheet with the slot details.
- Rewarded ad display through [../ads/RewardedAdManager.kt](../ads/RewardedAdManager.kt).
- Every screen runs its own `Scaffold` with `contentWindowInsets = WindowInsets(0,0,0,0)`;
  the shell and the `NavigationBar` own the system-bar insets.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
- `FilterEngineTest` covers the filter, sort, prime-time, heatmap and
  malformed-timestamp rules.
- No instrumented UI tests yet.
