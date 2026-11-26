# Alerts & Push

## Overview

Everything to do with "tell me when a slot opens": the local watchlist store,
the background poller, and the notification poster. The app is anonymous and
stores nothing on a server, so the whole watchlist lives in DataStore on the
device and every notification is produced locally.

## Interface

### `WatchlistStore` ([WatchlistStore.kt](./WatchlistStore.kt))
- `const val WORK_NAME = "slot-poll"` — unique work name
- `const val MAX_VENUES = 5`
- `fun observe(ctx: Context): Flow<Watchlist>`
- `suspend setSports(ctx, sports)` / `toggleSport(ctx, sport)` / `addSport(ctx, sport)`
- `suspend setDistricts(ctx, districts)` / `addDistrict(ctx, district)` / `toggleDistrict(ctx, district)`
- `suspend addVenue(ctx, venue): Boolean` — false when the five-venue cap is hit
- `suspend removeVenue(ctx, venue)`
- `suspend setWeekdays / toggleWeekday(ctx, weekdays)` — ISO 1 = Monday
- `suspend setTimeRange(ctx, fromMinute, toMinute)`
- `suspend setQuietHours(ctx, startMinute, endMinute)` — `[-1, -1]` disables
- `suspend grantPush(ctx, weeks: Int = 1)`
- `suspend revokePush(ctx)`
- `fun enqueuePoll(ctx)`

### `Watchlist` ([WatchlistStore.kt](./WatchlistStore.kt))
`sports`, `districts`, `venues`, `weekdays`, `fromMinute`, `toMinute`,
`quietStartMinute`, `quietEndMinute`, `pushEnabled`, `pushUntilEpoch`, plus
`fun pushActive(now)` and `val quietHoursEnabled`.

### `SlotPollWorker` ([SlotPollWorker.kt](./SlotPollWorker.kt))
`@HiltWorker` `CoroutineWorker`. `doWork()` returns `Result.success()`, or
`Result.retry()` when the network failed.

### `AlertNotifier` ([AlertNotifier.kt](./AlertNotifier.kt))
- `fun ensureChannel(ctx)`
- `fun notifyRelease(ctx, id: Int, title: String, text: String): Boolean` — `false`
  when the notification could not be posted (no permission, or the platform
  refused it), so the caller can keep the release event

## Invariants

- Push is active only when `pushEnabled` **and** `pushUntilEpoch > now`
  ([Watchlist.pushActive](./WatchlistStore.kt)). `pushUntilEpoch` is epoch
  millis stored as a **Long**; the v1.0 build stored it as an `Int`, which
  wrapped negative and silently disabled push forever.
- `grantPush` sets the expiry to `now + weeks * 7 days` and enqueues the
  poller; `revokePush` clears the flag, zeroes the expiry and cancels the
  poller, so DataStore and WorkManager never disagree.
- Polling is a single unique periodic job every 15 minutes with
  `ExistingPeriodicWorkPolicy.KEEP`, so re-enqueueing does not reset the
  schedule.
- The worker cancels its own unique work when the grant has expired.
- A session is announced **once**, because the release event is detected by
  comparing the snapshot before and after the fetch, not by a seen-key list.
  The first snapshot of a sport establishes the baseline and reports nothing.
- Pending events are read **newest first** and the watchlist predicate is
  applied before the notification limit, so a fresh release is never starved
  by older rows that do not match the watchlist.
- Events that do not match the watchlist are dropped after 24 hours, so the
  table cannot grow without bound.
- Before a notification goes out, the current availability is re-read from the
  cache. A session that was booked again in the meantime is dropped instead
  of being announced as available.
- An event whose notification could not be posted (no notification permission)
  is **kept**, so the alert is not lost.
- The matching predicate: sport (when the watchlist has sports), district
  (empty = all), venue (empty = all), weekday (empty = all days), and a
  half-open time window.
- Notification ids are derived from the session key, so two different sessions
  cannot overwrite each other's notification.
- At most 20 notifications are posted per poll, and at most 3 attempts are
  retried after a network failure: an offline device must not turn the poll
  into an endless retry loop whose backoff replaces the 15-minute cadence.
- During quiet hours the events stay pending and are delivered when the window
  closes.
- On API 33+ `notifyRelease` returns `false` when `POST_NOTIFICATIONS` is not
  granted.
- The notification channel `playfinder_alerts` uses `IMPORTANCE_HIGH`;
  notifications are `PRIORITY_HIGH` and auto-cancel.
- WorkManager is initialised by `PlayFinderApp.onCreate()` with the Hilt
  worker factory; the default AndroidX Startup initializer is removed in the
  manifest. Without that, the default reflection factory would be used and
  `SlotPollWorker` could not be constructed.

## Side Effects

- DataStore reads and writes on the preferences file `playfinder_prefs`
  (keys: `sports`, `districts`, `venues`, `weekdays`, `from_minute`,
  `to_minute`, `quiet_start`, `quiet_end`, `push_enabled`, `push_until_epoch`).
- WorkManager: `enqueueUniquePeriodicWork` and `cancelUniqueWork` for
  `SlotPollWorker`.
- One HTTP GET per watched sport per poll, through
  [../data/PlayFinderRepository.kt](../data/PlayFinderRepository.kt), which
  also refreshes the offline cache.
- Posts a notification through `NotificationManagerCompat` and creates the
  notification channel.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
- `WatchlistTest` covers the expiry semantics and the 64-bit epoch regression.
- No automated test yet for the poller itself or for the notification path.
