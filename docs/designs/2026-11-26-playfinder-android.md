# PlayFinder — Feature Specification

**Approved:** 2026-11-26 · **Revised:** 2026-11-27 (as-built, after the EGM
goldfish review) · **Status:** implemented.

This document describes the product as built. Where the 2026-11-26 draft
disagreed with the code, the disagreement is recorded in
[Implementation Status and Deviations](#implementation-status-and-deviations)
rather than left implicit.

**Vocabulary**

| Term | Meaning |
|---|---|
| LCSD | Leisure and Cultural Services Department (康文署), the Hong Kong government department that operates the venues |
| session | one bookable time block for one facility at one venue ("slot" in the original draft) |
| facility / location | the court or pitch, and where inside the venue it is (main hall, side hall) |
| venue | the sports centre or park |
| district | one of Hong Kong's 18 districts |
| SmartPLAY | the LCSD sports booking site and app; also the name of the public open-data feed this app reads |
| Oracle poller | the server-side Python poller of the SmartPLAY v5 pipeline; it runs on an Oracle Cloud VM, writes SQLite, and publishes alerts to Telegram first, with ntfy as the fallback channel. It is the website/ESP32 side of the project, not part of this app |
| feed-api Worker | the planned (not yet built) HTTP service that would serve the poller's SQLite to clients |
| Plan 2 | the project phase in which the feed-api Worker is built |
| quiet hours | a daily time window in which no push notification is shown |
| release event | a session whose available court count increased compared with the previous snapshot |

---

## Problem Statement

A Hong Kong court is booked in a lottery-like release: a session opens, the
available courts are visible for minutes, and whoever books first gets it.
Checking the LCSD app or website repeatedly is the only way to notice, and the
release window is short enough that a manual check usually misses it.

The user we serve wants three things:

1. **To know when a session they care about opens.** They care about a
   combination of sport, area, day and time of day — not about every session
   in Hong Kong.
2. **To browse what is open right now** without a deep dive, including while
   out of coverage.
3. **To pay nothing** for the alerting service, accepting a single ad in
   exchange.

The app is anonymous by design: no account, no cross-device sync, no personal
data collected. That constraint is what makes a one-week push grant cheap to
run, and it is also what limits the alerting to the device that holds the
grant.

---

## Goals & Non-Goals

### Goals

- Show court availability per sport, with a heatmap of when sessions open.
- Show LCSD programme activities with their registration details.
- Notify the user when a watched session gains available courts.
- Work offline on the last downloaded snapshot.
- Trade one watched ad for one week of push, with no always-on ads.

### Non-Goals (v1)

- No accounts, no login, no cross-device sync.
- No chat, no game organiser, no community features — share to WhatsApp or
  Telegram instead.
- No iOS app.
- No sports without an LCSD open-data feed (pickleball, table tennis and squash
  are waiting for upstream data).
- No server component of our own.

### Out of Scope (v2)

- A server-side push broker with per-user topics (the feed-api Worker).
- A daily digest and programme-activity notifications.
- Per-session starring (v1 watches a sport/district/venue/weekday/time
  filter set instead).
- Seller-side tools and in-app booking.

---

## Constraints

- Only public LCSD open data may be used.
- The app must work offline from a cached snapshot.
- **The app itself** collects and transmits no personal data: no account, no
  analytics, no server of our own. The ad SDK is the one exception, and it
  processes the advertising ID and IP address under Google's policies; see
  the privacy row in the risk table.
- The monetisation must be a value exchange, not a paywall or forced ads.
- The app must not claim affiliation with LCSD.
- Android only, min SDK 26 (Android 8.0), target SDK 35 (Android 15).

---

## Proposed Architecture

### Component Layout

```
app/src/main/java/com/playfinder/app/
├── MainActivity.kt          single activity, Compose NavHost, bottom navigation
├── PlayFinderApp.kt         Hilt application, WorkManager + AdMob bootstrap
├── core/                    pure logic, unit tested
│   ├── FilterEngine.kt        filter, sort, prime-time, heatmap (used by the UI and the poller)
│   └── ReleaseDetector.kt     "availability went up" detection (used by the repository)
├── data/                    the only layer that knows HTTP or SQL
│   ├── PlayFinderRepository.kt  court sessions: fetch, cache, diff
│   ├── ActivityRepository.kt    programme activities
│   ├── remote/                 Retrofit service + Moshi DTOs
│   └── local/                  Room database, DAOs, entities
├── alerts/                  watchlist store, background poller, notifications
├── ads/                     rewarded video
├── di/                      Hilt modules
└── ui/                      Compose screens, ViewModels, theme
```

### Data Flow

```
LCSD open-data API
  ├── {sport}/file        ──► PlayFinderRepository ──► Room cache ──► Compose screens
  │                              │
  │                              └─► release events ──► poller ──► local notification
  └── activity-prog/file  ──► ActivityRepository  ──► Room cache ──► Compose screens
```

The app has no server component and no push broker. It reads the same public
LCSD endpoints as the server-side poller, on the device.

The background poller refreshes **only the watched sports**. A cached sport
that the user does not watch is refreshed when they open that sport's screen,
not in the background.

### Data Layer

Two concrete `@Singleton` repositories over one Room database:

- `PlayFinderRepository` — `observeSlots(sport)`, `fetchAndCache(sport)`,
  `pendingReleaseEvents(limit)`, `clearReleaseEvents(ids)`.
- `ActivityRepository` — `observe(district, type, from, to)`, `observeAll()`,
  `refresh()`.

There is deliberately **no** data-source interface. One upstream exists today;
an interface would be speculative. When the feed-api Worker lands, the
repositories and the DTOs change — the screens and the ViewModels do not.

Filtering by district, date, time window and search text happens in memory in
`core/FilterEngine`; the SQL layer only fetches by sport and by date range.

### Tech Stack

Kotlin · Jetpack Compose (Material 3) · Hilt · Room · Retrofit + OkHttp +
Moshi · WorkManager · DataStore · AdMob rewarded video · FusedLocationProvider ·
Coroutines + Flow.

---

## Alternatives Considered

### A. UI framework

| Option | Trade-off | Decision |
|---|---|---|
| **Native Kotlin + Compose** | One codebase, smallest APK, best platform integration; Android-only | **Chosen** |
| Flutter | Cross-platform for a later iOS port, but a second UI codebase and a Dart rewrite of the data layer | Rejected |
| React Native / PWA | Fast to write, but weaker native feel, no background push without extra plumbing | Rejected |

The repository pattern is justified by upstream swappability and testability,
not by a future Flutter port — a Flutter app would rewrite the data layer
regardless.

### B. Push transport

| Option | Trade-off | Decision |
|---|---|---|
| **Device-local poll (WorkManager, 15 min)** | No server cost, works with no account, but latency is a 15-minute floor that Doze can stretch, and every device re-downloads the snapshot | **Chosen for v1** |
| ntfy anonymous subscription | Real server push in seconds, but ntfy's anonymous topic endpoint is read-only and the upstream publisher posts to one global topic, so per-watchlist filtering would need a server-side registry | Rejected for v1 |
| FCM | Proper push, but requires a Firebase project, a server and an account system | Rejected |
| feed-api Worker + per-topic ntfy (v2) | Segments the event namespace (sport/district/venue), gives second-long latency, but adds a server dependency and a publish fan-out | Deferred to v2 |

### C. Data source topology

| Option | Trade-off | Decision |
|---|---|---|
| **Direct LCSD open-data calls** | Zero infrastructure, works today; N devices × full snapshots | **Chosen** |
| feed-api Worker (SQLite → HTTP) | One server fetch serves all devices; needs a deployed Worker and a migration of the client | Deferred to Plan 2 |

### D. Cache

| Option | Trade-off | Decision |
|---|---|---|
| **Room (SQLite)** | Queryable, holds the previous snapshot needed for release detection, supports a release-event table | **Chosen** |
| DataStore only | Simple, but no queries and no snapshot history | Rejected for the cache (used for the watchlist instead) |

### E. Monetisation

| Option | Trade-off | Decision |
|---|---|---|
| **Rewarded video + in-app dwell** | Policy-safe, standard SDK pattern; the user can forfeit the reward by leaving the app | **Chosen** |
| Timed banner (3 min visible) | Matches the original draft, but a forced multi-minute banner dwell is invalid-traffic behaviour under Google policy | Rejected |
| Freemium subscription | Predictable revenue, but needs accounts and payments | Rejected |
| Always-on banner | Simple, but the anti-goal and bad for retention | Rejected |

---

## Features (v1)

### 1. Browse court sessions
- Sport chips for badminton, basketball, volleyball, tennis and turf soccer
  pitches.
- One flat, sorted session list with venue, date, time range, district and
  facility. Venue grouping and a date picker are not implemented; dates are
  chosen from chips in the filter sheet.
- Availability is a count pill: teal (the theme's primary) when courts
  remain, red when full — on Android 12+ the teal comes from the wallpaper
  palette. A missing or unparsable `Available_Courts` is stored as `0` and
  therefore shown as full, so the app has no explicit "no data" state; the
  live feed is assumed to publish a count on every row.
- Prime-time badge on Monday–Friday 19:00–22:00 sessions.
- Pull-to-refresh, a "updated N minutes ago" label, and an offline banner when
  the last refresh failed but cached rows exist.

### 2. Heatmap
Twelve two-hour buckets of the filtered list, shaded by how many available
sessions start in each bucket, with a 少→多 legend. Tapping a bucket filters
the list to that two-hour window.

### 3. Search and filters
Free-text search over venue and facility (debounced by 300 ms) sits above the
list, next to the filter button. The filter sheet holds the district dropdown,
date chips, a five-option time-window chip set and an "only sessions with
availability" switch. Sort by time, by availability or by distance from the
user.

### 4. Programme activities
District and activity-type filters, a free-text search, a date range
(全部 / 未來 7 日 / 未來 30 日) and cards showing venue, date, time, day,
registration period, fee, quota, places left, target group and enrolment
method. Each card opens the LCSD registration URL from the feed.

### 5. Watchlist and push
- Long-press a session to watch its sport, district and venue. A watchlist
  holds at most five venues; beyond that the sport and district are still
  added and the app says so.
- Push filters: sports, districts, venues, weekdays, a time window, and quiet
  hours.
- A push grant lasts one week and is bought with one rewarded video plus a
  three-minute in-app stay.
- The background poller refreshes the snapshot every 15 minutes and posts a
  notification for every session whose availability increased since the
  previous snapshot — each session is announced once.
- Quiet hours are **off** by default; switching them on sets 23:00–07:00, and
  notifications are held back until the window closes.

### 6. Settings
About and disclaimer, privacy summary, cache size with a confirmed clear
action, and a pointer to the Notifications tab.

### 7. Deep links
Activity cards open the registration URL supplied by the LCSD feed. A court
session opens the SmartPLAY home page: the LCSD publishes no public per-session
booking URL, so the app does not fabricate one.

---

## Monetisation & Push Incentive Loop

| Trigger | Reward |
|---|---|
| Watch one rewarded video to completion, then stay on the Notifications tab for three minutes | One week of push notifications with the user's own filters |
| No ad engagement | Manual browsing only, no push |

Eligibility is stored on the device: a `push_until_epoch` expiry timestamp and
an enabled flag in DataStore. Clearing app data clears the grant.

The three minutes measure **application dwell after the ad**, not ad
exposure. A rewarded video cannot be watched for three minutes; forcing a
banner to stay visible for that long is prohibited by Google Ad policy. The
implementation therefore splits the two: the SDK's own reward fires when the
video completes, and a separate in-app countdown must run to completion. The
countdown lives on the Notifications tab, so leaving that tab cancels it.

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation | Fallback |
|---|---|---|---|---|
| LCSD feed changes shape or disappears | No data at all | Medium | A null or missing column is tolerated — every DTO field is nullable, so one bad column cannot abort a refresh. A **type** change (a column that stops being a string) still fails the refresh and is only logged | Manual check on the LCSD site |
| Ad SDK processes the advertising ID and IP | The app itself collects nothing, but the ad SDK is outside our control | Certain | Disclosed in `PRIVACY.md` and in the app's privacy card; no other SDK is embedded | Disable ads in a future build |
| Doze / App Standby delay the poller | Alerts arrive late | High | 15-minute WorkManager period, grant expires after a week regardless | Pull-to-refresh shows current data |
| Notification permission denied | No notifications while the paid week burns | Medium | Permission card on the Notifications tab | The grant can be bought again after the week ends |
| AdMob test ids shipped in a release build | Policy violation, no revenue | High until release | The test ids are marked as blockers in the release checklist; `ads.txt` is in `app/src/main/assets` | Replace before upload |
| Release is device-local | Reinstall or a second device loses the grant and the watchlist | Certain | Stated in the privacy policy and the app's About card | Watch another ad |
| Snapshot grows stale | User books a session that is already taken | Medium | "Updated N minutes ago" and an offline banner; the poller refreshes the watched sports even when no screen is open | The app always shows the source's own disclaimer |
| Unwatched sports keep a stale cache | A user opens a sport they do not watch and sees old rows | Medium | The screen refreshes that sport on open; the label says how old the data is | Pull-to-refresh |
| R8 strips reflection-based code | Release build crashes at runtime | Low | Explicit keep rules for Moshi DTOs, Retrofit interfaces, Room and WorkManager | Build the debug variant |
| Release signing misconfigured | Unsigned bundle | Low | The build fails with an explicit message when `keystore.properties` is missing | Use the debug variant |
| Logcat leaks request URLs in release | Minor privacy issue | Low | The OkHttp logging interceptor is compiled out unless `BuildConfig.DEBUG` | — |

---

## Implementation Status and Deviations

| Original decision | As built | Why |
|---|---|---|
| ntfy anonymous subscription for push | Device-local WorkManager poll (15 min) with local notifications | ntfy's anonymous topic endpoint is read-only and the upstream publisher uses one global topic; per-watchlist filtering would need a server-side registry (v2) |
| AdSense banner, three-minute visible, tracked by an impression listener | Rewarded video, then a three-minute in-app countdown | An impression callback fires once and cannot measure duration; a forced multi-minute banner dwell violates Ad policy |
| `Repository` interface with `LcsdDataSource` / `FeedApiDataSource` / `RoomCache` | Two concrete repositories over one Room database | Only one upstream exists; the interface was speculative |
| Watchlist as starred sessions, "up to 5 venues", weekday and time range | Sport + district + venue (max 5) + weekday + time window + quiet hours | The filter set delivers the same user intent without a per-session star model |
| Sale7 digest at 08:15 and programme-activity alerts | Not implemented | Needs a server-side schedule; deferred to v2 |
| Green / red / grey availability | A teal/red count pill (dynamic colour on Android 12+) | The live feed publishes a court count on every row, so "no data" has no source; a missing count is stored as 0 and shown as full |
| Venue cards → date picker → session list | One flat, filtered session list | The feed exposes sessions, not venues with nested dates |
| Activity browse by sport → district → date range | District + activity type + date range | The activity feed has no sport dimension; it has a type |
| `Resource<T>` wrapper with an `isStale` flag | A `lastSync` timestamp and a separate offline banner | One flag does less work than a wrapper the UI never reads differently |
| Room schema for cache **and** watchlist | Room for the cache, DataStore for the watchlist | The watchlist is a small key-value set; a table would add a schema without a query |
| KAPT for Room and Hilt | KSP for both | Faster, and required by the Moshi code generator |
| CI builds a debug APK on push | `.github/workflows/android-apk.yml` runs the unit tests and `assembleDebug` on app changes | — |

## Component contracts

The per-package contracts under `app/src/main/java/com/playfinder/app/` are
the component-level source of truth for interfaces, invariants and side
effects: [app](../app/README.md), [core](../app/core/README.md),
[data](../app/data/README.md), [alerts](../app/alerts/README.md),
[ads](../app/ads/README.md), [di](../app/di/README.md), [ui](../app/ui/README.md).

---

## Verification

- Unit tests: `.\gradlew.bat testDebugUnitTest`
  (`FilterEngineTest`, `ReleaseDetectorTest`, `WatchlistTest`, `LcsdRecordTest`,
  `MoshiAdapterTest`).
- Build: `.\gradlew.bat assembleDebug bundleRelease`
- Coverage gaps that remain: the Room schema and DAOs, the poller, the ad
  gate, the deep link and all three ViewModels have no automated tests yet;
  the `androidTest` dependencies are declared but unused.
