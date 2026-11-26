# PlayFinder Android APK — Design

**Date:** 2026-11-26
**Status:** Approved (user said "Approved" 2026-11-26)
**Topic:** Native Android court-availability + push-alert app built on the SmartPLAY v5 data pipeline

## Intent & Why

A Hong Kong sports court availability app that is **push-first, not search-first**: it alerts the user when a slot they care about opens up, rather than making them manually search. Built on the SmartPLAY v5 data pipeline (LCSD open data via Oracle poller → ntfy push → feed-api). Free to use; monetized via a value-exchange ad model (3-min banner view → 1 week of push alerts).

## Goals
- Browse LCSD court vacancies by sport/venue/date/time with a visual heatmap
- Browse LCSD programme activities (courses/events)
- Push notifications for slot releases with user-chosen filters
- Watchlist: star slots/venues → alert when they open
- Deep-link to SmartPLAY / LCSD registration
- Offline cache of last-known data
- Monetize via AdSense value-exchange (no paywall, no forced ads)

## Non-goals (v1)
- Game organizer / in-app chat (deferred to v2; use "share to WhatsApp" instead)
- User accounts / cross-device sync (anonymous, local storage)
- Pickleball / table tennis / squash (waiting for LCSD data)
- iOS (Android-only v1)

## Anti-goals
- No forced banner ads on every screen (only value-exchange)
- No personal data collection beyond device-local watchlist
- No affiliation claim with LCSD

## Constraints
- Must use existing data sources: LCSD open-data API, ntfy (https://ntfy.tedton.hk), feed-api Worker (Plan 2)
- Android-only v1 (Kotlin + Jetpack Compose)
- Must work offline (cached data)
- AdSense publisher ID: pub-2824936620876447

## Approaches Considered

### A. Native Kotlin + Jetpack Compose (chosen)
- Best Android UX, native performance, small APK, modern standard
- Data layer abstracted via repository pattern → swap backend without UI changes
- Cons: Android-only, Kotlin learning curve

### B. Flutter
- Cross-platform (iOS later), single codebase, hot reload
- Cons: larger APK (~15MB), Dart learning curve, overkill for Android-only v1

### C. React Native / PWA
- Reuses web skills, fastest prototype
- Cons: less native feel, PWA can't do real push on iOS, weaker offline

**Decision:** A (Native Kotlin). Repository pattern keeps the door open for Flutter migration if iOS is needed later.

## Monetization & Push Incentive Loop

| User action | Reward |
|---|---|
| Click/view 3-min AdSense banner | 1 week of push notifications with chosen filters (sport, weekday, time range, up to 5 venues) |
| No ad engagement | Manual search only (no push alerts) |

- Banner shown on search results screen + watchlist screen
- 3-min timer: banner must stay visible (overlay or scroll-lock); track view duration via AdView impression listener
- Filter config saved locally; ntfy anonymous subscription activated client-side
- After 1 week, prompt to renew (click another banner) → recurring engagement
- AdSense publisher: pub-2824936620876447

## Features (v1)

### 1. Browse Court Vacancies
- Sport chips (horizontal scroll) → Venue cards → Date picker → Time slot list
- Visual availability: green=available, red=full, grey=no data
- Prime-time badge ✅ on Mon-Fri 19:00-22:00 slots
- Pull-to-refresh + offline indicator

### 2. Browse Programme Activities
- Sport → District → Date range → Activity cards
- Detail: venue, time, fee, registration period, quota, instructor
- Deep link to LCSD registration page
- (Differentiator: SeekCourt has no programme activities)

### 3. Search
- One-screen filter bar: sport chips + date picker + time range slider + district dropdown
- Instant results (debounced 300ms)
- Sort by: distance (GPS), availability count, time
- Empty state with suggested adjustments

### 4. Watchlist & Push (ad-gated)
- Long-press any slot → "watch this"
- ntfy anonymous subscription (device-specific topic)
- Push for: new slot, sale7 digest (08:15 daily), programme activity alerts
- Filter config: sport, weekday, time range, up to 5 venues

### 5. Settings
- Notification preferences (sports, districts, quiet hours)
- Ad-gated timer status ("Push active until 2026-12-03")
- About / disclaimer (third-party, not affiliated with LCSD)
- Clear cache / offline data

### 6. Deep Link
- Tap any available slot → open SmartPLAY booking page in browser
- Tap any activity → open LCSD registration page

## Data Flow

```
LCSD API → Oracle poller → SQLite → feed-api Worker (Plan 2) → PlayFinder
                                    ↘ ntfy → PlayFinder (push alerts)
```

Until Plan 2 ships feed-api, app fetches directly from LCSD open-data API with client-side caching (same endpoints as poller).

## Data Layer (Repository Pattern)

```
Repository (interface)
  ├── LcsdDataSource (Retrofit → LCSD API, v1)
  ├── FeedApiDataSource (Retrofit → feed-api Worker, v2)
  └── RoomCache (offline storage)
```

Swap `LcsdDataSource` → `FeedApiDataSource` when Plan 2 ships, zero UI changes.

## Tech Stack
- **Language:** Kotlin
- **UI:** Jetpack Compose + Material 3
- **DI:** Hilt
- **Network:** Retrofit + OkHttp + Moshi (JSON)
- **Local DB:** Room (SQLite)
- **Push:** ntfy HTTP API (subscribe via SSE or polling)
- **Ads:** Google AdMob (AdSense for apps) — banner + rewarded video for the 3-min view
- **Location:** FusedLocationProvider (for distance sort)
- **Min SDK:** 26 (Android 8.0) — covers 95%+ devices

## My Calls (defaults applied)
1. **Platform:** Android-only v1 (Kotlin). iOS deferred; repository pattern keeps migration open.
2. **Monetization:** Ad-gated push only (no always-on banners). Cleaner UX, higher retention.
3. **Game organizer / chat:** Deferred to v2. Use "share to WhatsApp/Telegram" link instead.
4. **Account system:** Anonymous (no login). Watchlist stored locally; ntfy anonymous subscribe. Cross-device sync deferred to v2.

## What's Left to the Builder
- Exact Compose component breakdown
- ntfy subscription mechanism (SSE vs polling) — SSE preferred but needs testing on Android
- AdMob integration details (banner placement, rewarded video for 3-min view)
- Room schema for cache + watchlist
- CI/CD (GitHub Actions → APK build)

## Builder Check
To be dispatched after design approval (already approved by user).

## Next Step
Invoke superpowers:writing-plans to create the implementation plan.