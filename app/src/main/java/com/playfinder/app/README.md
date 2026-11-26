# PlayFinder App Blueprint

## System Overview

PlayFinder is an Android app (Kotlin + Jetpack Compose, Material 3) that shows
Hong Kong LCSD court availability and programme activities, and notifies the
user when a session they watch gains available courts. It is anonymous: no
account, no server-side profile, and the watchlist never leaves the device.

The system has five layers, each with one job:

1. **[core/](./core/README.md)** — pure filter, sort and release-detection
   logic, shared by the UI and the background poller.
2. **[data/](./data/README.md)** — fetch the LCSD open-data feed, keep a Room
   snapshot, record release events, expose them as flows. The layer that owns
   the HTTP calls and the SQL queries.
3. **[alerts/](./alerts/README.md)** — the watchlist, the 15-minute background
   poller, and the notification poster.
4. **[ads/](./ads/README.md)** — the rewarded ad that buys a week of push.
5. **[ui/](./ui/README.md)** — Compose screens and ViewModels; they read
   `StateFlow`s and call ViewModel methods, nothing else.

**[di/](./di/README.md)** wires the singletons (database, Retrofit, API) with
Hilt.

Push is device-local: the app polls the public feed itself with `WorkManager`
while a grant is active. There is no server component in v1, so push cannot
follow the user to a second device and the poll interval is bounded by
Android's Doze and App Standby behaviour.

## Local Interface & Invariants

- `MainActivity` ([MainActivity.kt](./MainActivity.kt)) — `@AndroidEntryPoint`
  single activity. Calls `enableEdgeToEdge()`, then hosts `AppShell` inside
  `PlayFinderTheme`.
- `AppShell` — the `Scaffold` with the bottom `NavigationBar` and the
  `NavHost`. Four routes: `home`, `activities`, `alerts`, `settings`; the
  start destination is `home`.
- `PlayFinderApp` ([PlayFinderApp.kt](./PlayFinderApp.kt)) — `@HiltAndroidApp`;
  implements `Configuration.Provider` so `SlotPollWorker` can be constructed
  by the Hilt worker factory, and initialises the AdMob SDK in `onCreate`
  (without that call no ad can load).
- Route constants are private to `MainActivity.kt`; no other file references
  them.

## Subdirectories & System Boundaries

- [ads/](./ads/README.md) — rewarded ad display; no other ad format.
- [alerts/](./alerts/README.md) — watchlist state, background polling,
  notifications.
- [core/](./core/README.md) — pure logic shared by the UI and the poller.
- [data/](./data/README.md) — Retrofit + Room + repositories; the only layer
  that touches the network or the database.
- [di/](./di/README.md) — Hilt modules for the database and the HTTP stack.
- [ui/](./ui/README.md) — Compose screens, ViewModels, theme.

## Global Invariants

- No account, no login, no personal data leaves the device. The watchlist,
  the push grant and the push filters are stored in DataStore only.
- Location is used to sort by distance and is never uploaded or persisted.
- The push grant is a **Long** epoch-millisecond expiry; it must never be
  narrowed to an `Int`.
- Every Room **cache** write path replaces a full snapshot inside a
  transaction, so the cache cannot accumulate duplicate sessions. The
  release-event log is append-only.
- A session is announced at most once: release detection compares the
  snapshot before and after the fetch and stores the event in Room.
- HTTP failures are surfaced as errors, never silently turned into an empty
  list.
- The upstream feed is treated as a snapshot mirror; rows without a usable
  date and start time are dropped rather than stored.
- `AllowBackup` is off, the network security config forbids cleartext, the
  release build runs R8 with resource shrinking and keep rules, and the HTTP
  logging interceptor only logs in debug builds (`Level.NONE` in release).

## Global Side Effects

- Network calls to `data.smartplay.lcsd.gov.hk` (read-only, public feed).
- Writes to the `playfinder.db` SQLite file (sessions, activities, release
  events).
- Writes to the `playfinder_prefs` DataStore file.
- WorkManager schedules one unique periodic job (`slot-poll`) while a push
  grant is active.
- Posts notifications on the `playfinder_alerts` channel.
- Loads and shows a Google AdMob rewarded ad on request.

## System Verification

- Run: `.\gradlew.bat test assembleDebug`
- Release bundle: `.\gradlew.bat bundleRelease` (needs `keystore.properties`;
  the build fails with an explicit message when it is missing).
- CI: `.github/workflows/android-apk.yml` runs the unit tests and builds the
  debug APK on every change that touches the app.
