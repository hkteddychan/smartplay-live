# Consolidated Review Report

EGM goldfish review of the PlayFinder Android app, 2026-11-27.
Target documents: `docs/designs/2026-11-26-playfinder-android.md` (spec) and
`docs/designs/2026-11-26-playfinder-android-plan.md` (plan).

Stage reports: [zoom_out](./zoom_out_report.md) · [comprehension](./comprehension_report.md) ·
[critic](./critic_report.md) · [implementation_readiness](./implementation_readiness_report.md).
Drift: [../2026-11-27_DRIFT_REPORT.md](../2026-11-27_DRIFT_REPORT.md).

## What the reviewers found

The eight reviewers agreed on the root problem: **the design documents
described a product that did not exist.** The documents specified ntfy push,
a banner-ad monetisation model with a three-minute visible banner, a
speculative repository interface, a starred-slot watchlist with weekday and
time-range filters, quiet hours, a sale7 digest, three-state availability, a
CI workflow and a package layout — none of which the code contained. The
code, meanwhile, had four critical runtime defects the documents never
mentioned: an Int-overflowed push expiry, an activity feed that was never
collected, duplicate rows on every refresh, and a `MobileAds.initialize()`
that was never called.

## Action items and dispositions

| # | Action item | Source | Severity | Disposition |
|---|---|---|---|---|
| 1 | Push transport is device-local polling, not ntfy | zoom-out, critic, style, readiness | Blocker | **Fixed in the document.** Alternatives B records the choice and the trade-offs; the data-flow diagram was rewritten |
| 2 | The banner-ad model does not exist and would violate Ad policy | zoom-out, critic, style | Blocker | **Fixed in the document and the code path.** Rewarded video + 180 s in-app gate; every banner mention removed |
| 3 | No `Repository` interface; the "zero UI changes" claim is false | zoom-out, critic | Major | **Fixed in the document.** The speculative hierarchy was deleted; the real guarantee ("screens and ViewModels do not change") is stated instead |
| 4 | Push filters lack weekday, time window and the five-venue cap | critic, readiness | Major | **Fixed in the code.** Store, worker predicate and Notifications screen |
| 5 | Quiet hours do not exist | zoom-out, readiness | Major | **Fixed in the code** |
| 6 | The first poll floods notifications; a 2 → 4 release is missed | inventive catalyst | Major | **Fixed in the code.** `core/ReleaseDetector` + a Room release-event log; the seen-key set was deleted |
| 7 | The poller bypasses the repository and never refreshes the cache | inventive catalyst | Nit | **Fixed in the code.** The poller calls `PlayFinderRepository.fetchAndCache` |
| 8 | `MobileAds.initialize()` is never called: no ad can load | readiness | Blocker | **Fixed in the code** |
| 9 | The activity registration period exists in the feed but is dropped | drift, readiness | Blocker | **Fixed in the code.** `ENROL_START_DATE` / `ENROL_END_DATE` through to the card |
| 10 | Activity browse has no date range | drift, readiness | Blocker | **Fixed in the code.** `ActivityRange` in the SQL query |
| 11 | Search has no debounce | drift, critic, style | Major | **Fixed in the code** (300 ms in both ViewModels) |
| 12 | Notification permission is never requested | readiness | Blocker | **Fixed in the code** |
| 13 | Notification ids overwrite each other | critic | Nit | **Fixed in the code.** One id per session |
| 14 | No ProGuard rules with R8 on; HTTP logging in release | critic | Major | **Fixed in the code** |
| 15 | Release signing produces an unsigned bundle when the keystore is missing | readiness | Major | **Fixed in the build** (explicit failure) |
| 16 | `ads.txt` is not in the app assets | readiness | Major | **Fixed** (`app/src/main/assets/ads.txt`) |
| 17 | No CI workflow | drift, readiness | Major | **Fixed** (`.github/workflows/android-apk.yml`; `gradlew` made executable) |
| 18 | The spec has no Problem Statement, Alternatives or Risks section | structural | Blocker | **Fixed in the document** |
| 19 | The spec's feature list contradicts the code | style, codebase-details | Blocker | **Fixed in the document**; every feature is now described as built |
| 20 | "Green" availability does not exist (the pill is teal/primary) | zoom-out, verification | Nit | **Fixed in the document** |
| 21 | "No data" availability has no data source | codebase-details | Blocker | **Fixed in the document** (a missing count is stored as 0 and shown as full) |
| 22 | The plan's file inventory does not match the tree | drift, readiness | Blocker | **Fixed in the document.** As-built file map with an action per row |
| 23 | The plan's 87 checkboxes are stale | drift, style | Major | **Fixed in the document.** The plan is marked as executed and points at the specification |
| 24 | `PRIVACY.md` claims ntfy delivery | verification | Blocker | **Fixed.** The policy now describes device-local polling |
| 25 | "No personal data may be collected" contradicts the ad SDK | zoom-out | Major | **Fixed in the document.** The constraint is qualified and a privacy row was added to the risk table |
| 26 | The poller only refreshes watched sports | zoom-out (stage 8) | Major | **Fixed in the document** (data flow + risk row) |
| 27 | The DTO-nullability mitigation is overstated | zoom-out (stage 8) | Major | **Fixed in the document.** A type change still fails the refresh |
| 28 | The spec duplicated the package contracts | zoom-out (stage 8) | Major | **Fixed.** The package READMEs are linked as the component contracts |
| 29 | No package contracts existed | bootstrap | Major | **Fixed.** A `README.md` per package with Interface / Invariants / Side Effects |
| 30 | Sale7 digest, programme-activity alerts, per-session starring | several | Major | **Accepted as v2.** Recorded under Out of Scope (v2) |
| 31 | Per-slot booking deep links | several | Major | **Accepted.** SmartPLAY publishes no per-session URL; the limitation is documented instead of faked |
| 32 | A server-side push broker with per-user topics | inventive catalyst | Major | **Deferred to v2.** Recorded in Alternatives B with its trade-offs, including the fact that a client-local grant cannot protect a server-side topic |
| 33 | Repository, DAO and ViewModel test coverage | readiness | Major | **Partly fixed.** `ReleaseDetector` and `FilterEngine` are covered; the rest remain open and are listed in the audit |

## Traceability

| Document claim | Status | Evidence |
|---|---|---|
| "Push for: new slot" | true, and now exactly once | `core/ReleaseDetector`, `release_events` table |
| "sale7 digest, programme-activity alerts" | false → moved to v2 | `docs/designs/…-android.md`, Out of Scope |
| "Filter config: sport, weekday, time range, up to 5 venues" | true | `alerts/WatchlistStore`, `SlotPollWorker.matches` |
| "green=available, red=full, grey=no data" | partly false → corrected | `ui/HomeScreen.kt` availability pill |
| "Push: ntfy HTTP API" | false → corrected | no ntfy client in the tree |
| "3-min AdSense banner … AdView impression listener" | false → corrected | `ads/RewardedAdManager`, `ui/AlertsScreen` |
| "Repository (interface) … FeedApiDataSource" | false → corrected | `data/PlayFinderRepository` |
| "CI: build debug APK on push" | true now | `.github/workflows/android-apk.yml` |
| "Room schema for cache + watchlist" | cache only; the watchlist is DataStore | `alerts/WatchlistStore` |

## Status

**Resolved.** Every blocker and major finding in the stage reports is either
fixed in the code or corrected in the documents; the remainder is recorded as
an explicit v2 item with a reason. The verification pass re-read the code and
the documents and confirmed the remaining statements.
