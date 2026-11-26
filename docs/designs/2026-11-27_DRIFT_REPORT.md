# DRIFT REPORT

Generated 2026-11-27 by an EGM drift-report pass (fresh-context analyst,
read-only) comparing the checked-in design documents with the current source.

Scope: the PlayFinder Android app only. The website rebuild design
(`docs/specs/2026-11-26-smartplay-live-rebuild-design.md`) and the ESP32
firmware are a separate product and were not audited here.

---

## 2026-11-26-playfinder-android.md (Design)

- **ntfy push replaced by device-local polling** — Doc says: "Push: ntfy HTTP API (subscribe via SSE or polling)"; "ntfy anonymous subscription (device-specific topic)"; constraint "Must use existing data sources: … ntfy (https://ntfy.tedton.hk)" (lines 32, 63, 89, 129). Code does: no ntfy client exists anywhere in `app/src`; `alerts/SlotPollWorker.kt:27` fetches the LCSD API itself every 15 min via WorkManager, so there is no server push, no device topic, no anonymous subscribe. Impact: the "push-first" core value proposition is unimplemented as specified.
- **Banner ad model absent; the 3-min gate is not a banner view** — Doc says: "Banner shown on search results screen + watchlist screen"; "3-min timer: banner must stay visible (overlay or scroll-lock); track view duration via AdView impression listener" (lines 61–62). Code does: only a full-screen rewarded video (`ads/RewardedAdManager.kt:22`); the 180 s window is an idle in-app countdown *after* the ad, with no ad on screen (`ui/AlertsScreen.kt:34, 63–74`); no banner component and no search/watchlist screen exist. Impact: the monetisation mechanism and its measurement differ from the spec.
- **AdSense publisher ID never used** — Doc says: "AdSense publisher ID: pub-2824936620876447" (lines 35, 65). Code does: the manifest uses Google's test app ID `ca-app-pub-3940256099942544~3347511713` (`app/src/main/AndroidManifest.xml:21`) and the test rewarded unit `…/5224354917` (`ads/RewardedAdManager.kt:15`); `pub-2824936620876447` appears nowhere. Impact: the build cannot serve real ads and violates AdMob policy.
- **Push filter config missing two of four dimensions** — Doc says: "Filter config: sport, weekday, time range, up to 5 venues" (lines 58, 91). Code does: `alerts/WatchlistStore.kt:19-26` persists only `sports`, `districts`, `venues`; no weekday, no time range, no 5-venue cap (`WatchlistStore.setVenues` accepts unbounded sets). Impact: users cannot express the filters the doc promises.
- **Only one of three push types exists** — Doc says: "Push for: new slot, sale7 digest (08:15 daily), programme activity alerts" (line 90). Code does: `alerts/SlotPollWorker.kt:46-60` emits only new-slot notifications; no digest schedule and no activity alerts. Impact: 2 of 3 notification commitments missing.
- **No repository interface / no swappable data source** — Doc says: "Repository (interface)", "LcsdDataSource … FeedApiDataSource … Swap `LcsdDataSource` → `FeedApiDataSource` when Plan 2 ships, zero UI changes" (lines 112–121). Code does: `data/PlayFinderRepository.kt:12` and `data/ActivityRepository.kt:12` are concrete `@Singleton class` bound directly to `LcsdApi`; no data-source interface exists. Impact: the stated migration path is not available.
- **Activity detail drops registration period** — Doc says: "Detail: venue, time, fee, registration period, quota, instructor" (line 77). Code does: the feed supplies `ENROL_START_DATE` / `ENROL_END_DATE` (verified live: 25 of the first 200 records carry them, the rest are null), but `LcsdActivity` and `ActivityEntity` omit them; the card shows fee/quota/target/enrol method only. Impact: users cannot see when registration opens.
- **Slot DTO drops feed columns** — The feed supplies `Venue_Address_TC/EN`, `Venue_Phone_No.`, `District_Name_EN`, `Venue_Name_EN`, `Facility_Location_Name_EN` (verified live); `LcsdRecord` keeps only the TC venue/district/facility/location and `SlotEntity` has no address/phone column. Impact: bilingual and contact data present upstream is discarded.
- **Deep link ignores the tapped slot** — Doc says: "Tap any available slot → open SmartPLAY booking page in browser" (line 100). Code does: `ui/DeepLink.kt:7-13` holds one constant `BOOKING_BASE = "https://www.lcsd.gov.hk/smartplay"`; no sport/venue/date/time is encoded. Impact: the user lands on the site root, not the session.
- **Heatmap semantics differ from the spec** — Doc says: "Visual availability: green=available, red=full, grey=no data" (line 71). Code does: `ui/HomeScreen.kt` renders 12 two-hour buckets of the already-filtered list as a single-hue `primary` alpha ramp with a 少→多 legend; no 7-day axis and no grey "no data" state. Impact: the documented visual language is absent. (Live feed check: `Available_Courts` is populated on every row, so a "no data" state has no data source today.)
- **Search filter bar is not one-screen; no debounce** — Doc says: "One-screen filter bar: sport chips + date picker + time range slider + district dropdown"; "Instant results (debounced 300ms)" (lines 82–83). Code does: filters live in a `ModalBottomSheet`; the time range is 5 preset chips, not a slider; search applies on every keystroke with zero debounce. Impact: differs from the spec on both layout and behaviour.
- **Settings has no notification preferences or quiet hours** — Doc says: "Notification preferences (sports, districts, quiet hours)"; "Ad-gated timer status" (lines 94–95). Code does: `ui/SettingsScreen.kt` contains About / Data-source / Privacy / Cache cards only; sport and district toggles sit in the Alerts tab and no quiet-hours setting exists anywhere. Impact: the quiet-hours commitment is unimplemented.
- **Activity browse lacks date range and uses type, not sport** — Doc says: "Sport → District → Date range → Activity cards" (line 76). Code does: filters are district + 活動類型 + free text; `ActivitiesViewModel.setFrom` exists but no UI calls it, so the range is pinned to today. Impact: date-range browsing is impossible.
- **Watchlist is not in Room** — Doc says: "Room schema for cache + watchlist" (line 144). Code does: the watchlist lives in DataStore (`alerts/WatchlistStore.kt:17`); `PlayFinderDatabase` has only `slots` + `activities`. Impact: architecture diverges from the stated cache plan.
- **Empty state offers no suggested adjustments** — Doc says: "Empty state with suggested adjustments" (line 85). Code does: fixed copy plus a clear-filters button. Impact: minor UX divergence.
- **Nit — sport chip set** — The doc/plan list 6 chips including 🏃活動; the code defines 5 and puts activities on their own tab.

---

## 2026-11-26-playfinder-android-plan.md (Implementation Plan)

- **No Android CI workflow** — Plan says: "Create `.github/workflows/build-apk.yml` (CI: build debug APK on push)" (Task 14 Step 5). Code does: `.github/workflows/` contains only `esp32-feed.yml`, `esp32-ota.yml` and `update-data.yml` — all ESP32/Pages. Impact: no APK build on push; Task 14 Step 5 unfulfilled.
- **All 87 plan steps remain unchecked** — Plan says: "Steps use checkbox (`- [ ]`) syntax for tracking" (line 3). Code does: 87 `- [ ]`, 0 `- [x]`, despite most features existing. Impact: plan tracking is stale and hides what actually shipped.
- **Plan points at a non-existent spec path** — Plan says: "**Spec:** `docs/superpowers/specs/2026-11-26-playfinder-android-design.md`" (line 11). Code does: that path does not exist; the design now lives at `docs/designs/2026-11-26-playfinder-android.md`. Impact: the plan's normative reference was broken (fixed during this pass).
- **Directory/package layout diverges wholesale** — Plan Tasks 5–13 specify `ui/screens/**`, `ui/components/**`, `ui/navigation/**`, `push/**`, `util/**`, `data/repository/**`. Code does: flat `ui/*.kt`, plus `ui/theme/`, `alerts/`, `ads/`, `data/*.kt`; none of `ui/screens`, `ui/components`, `ui/navigation`, `push` or `util` exists. Impact: every "Create: …" path in Tasks 5–13 is wrong.
- **Named files never created** — Plan lists `dto/LcsdMetadata.kt` (Task 2), `entity/WatchlistEntity.kt` + `dao/WatchlistDao.kt` + `push/NtfySubscriber.kt` + `push/PushManager.kt` (Task 8), `ads/AdManager.kt` + `ui/components/AdBanner.kt` (Task 9), `ui/components/OfflineBadge.kt` (Task 12), `ui/screens/about/AboutScreen.kt` (Task 11), `ui/navigation/PlayFinderNavGraph.kt` + `ui/components/BottomNavBar.kt` (Task 13). Code does: none exist (surrogates: `ads/RewardedAdManager.kt`, `alerts/WatchlistStore.kt`, inline navigation in `MainActivity.kt`, About card in `ui/SettingsScreen.kt`). Impact: the plan's named interfaces (`PushManager.isPushActive()`, `AdManager.loadBanner`, `Resource.Success`) are absent.
- **Six of seven named test files missing** — Plan names `LcsdApiTest.kt` (Task 2), `SlotDaoTest.kt` (Task 3), `SlotRepositoryTest.kt` (Task 4), `BrowseViewModelTest.kt` (Task 5), `SearchViewModelTest.kt` (Task 6), `PushManagerTest.kt` (Task 8). Code does: `app/src/test` holds `FilterEngineTest.kt`, `LcsdRecordTest.kt`, `MoshiAdapterTest.kt`, `WatchlistTest.kt` — no repository, DAO, ViewModel or API-contract test. Impact: the TDD steps of Tasks 2–8 never ran; "second call returns from cache when offline" is untested.
- **Repository interface/impl contract not implemented** — Plan says: "Produces: `SlotRepository.getSlots(sport, venue, date)`, `SlotRepository.refresh(sport): Result<Unit>`" (Task 4). Code does: concrete classes with `observeSlots(sport)` and `refreshSport(sport)` that throws instead of returning `Result`. Impact: no venue-filtered query and no `Result` contract.
- **ActivityEntity schema drift** — Plan says: "ActivityEntity (activityNo, sport, venue, district, date, startTime, endTime, fee, quota, registrationStart, registrationEnd, fetchedAt)" (Task 3 Step 4). Code does: the entity has no `registrationStart`/`registrationEnd` and no `sport` (it has `type`), and the plan's `date` is split into `startDate`/`endDate`. Impact: the registration period available in the feed is unreachable.
- **`deleteStale` defined but never called** — Plan makes `@Query("DELETE FROM slots WHERE fetchedAt < :cutoff")` the eviction path (Task 3 Step 5). Code does: `SlotDao.deleteStale` and `ActivityDao.deleteStale` exist with no caller; `SlotDao.observeBySportAndDate` is likewise unused. Impact: dead code; no expiry path is exercised.
- **Navigation tabs differ** — Plan says: "4 tabs — Browse, Search, Activities, Watchlist (Settings via overflow menu)" (Task 13). Code does: 4 tabs 場地 / 活動 / 通知 / 設定, with Settings as a bottom tab and no separate Search or Watchlist tab. Impact: the tab model and screen inventory differ.
- **3-min reward semantics differ** — Plan says: "AdMob rewarded video must grant the 1-week push only after 3 full minutes of view (not just 'ad loaded')" (Review Focus) and "show with 3-min view timer" (Task 9 Step 1). Code does: the grant happens after ad completion plus 180 s of idle in-app countdown with no ad on screen; the reward callback is the standard `onUserEarnedReward`. Impact: the timer measures app presence, not ad view duration.
- **Rewarded trigger not on a WatchlistScreen** — Plan says: "Add rewarded video trigger to `WatchlistScreen`" (Task 9 Step 4). Code does: the button lives on the Alerts tab; no `WatchlistScreen` exists. Impact: the plan's file contract and screen placement are unmet.
- **DeepLink API differs** — Plan says: "Produces: `DeepLink.openSmartPlay(context, sport, venue, date, time)` plus `DeepLink.openLcsdActivity`" (Task 10). Code does: only `DeepLink.openInBrowser(context)` with a constant URL; activities link straight to `activity.url`. Impact: no per-slot deep link.
- **No `Resource<T>` stale-data wrapper** — Plan says: "emit `Resource.Success(data, isStale)`" (Task 12 Step 1) and create `OfflineBadge.kt` (Step 2). Code does: no `Resource` type exists; staleness is a separate `lastSync: StateFlow<Long?>` rendered by an inline `SyncBanner`. Impact: the plan's specified API shape is absent.
- **LCSD metadata endpoint missing** — Plan says: "Implement LcsdApi with `@GET("{name}/file")` and `@GET("{name}")` (metadata)" plus `dto/LcsdMetadata.kt` (Task 2). Code does: the API exposes only `getDataset` and `getActivities`; the metadata DTO was removed as dead code during this pass. Impact: metadata-driven dataset discovery is unimplemented (and unused).
- **kapt vs KSP** — Plan says: "`room-compiler` (kapt)", "`hilt-compiler` (kapt)" (Task 1 Step 2). Code does: KSP is used for both. Impact: minor build-tool divergence from the specified setup.
- **Nit — no "activities" chip, and a 12-bucket heatmap instead of a 7-day grid** — Plan Task 5 Steps 4–5 specify 6 chips incl. 🏃活動 and a "7-day × time-slot grid, green/red/grey cells"; the code has 5 chips and a 12-cell alpha ramp of the filtered list.

---

## Live-feed facts recorded during this pass

Useful for resolving the findings above; all fetched from
`https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/`:

- `badminton/file` → 13,664 rows, 8 distinct dates (2026-11-27 … 2026-12-04).
  Every column is populated — including `Available_Courts` — so the spec's
  grey "no data" availability state has no source in the current feed.
- The feed carries columns v1 drops: `Venue_Address_TC/EN`,
  `Venue_Phone_No.`, `Venue_Name_EN`, `District_Name_EN`,
  `Facility_Location_Name_EN`.
- `activity-prog/file` → 8,193 rows, 35 columns. `ENROL_START_DATE` and
  `ENROL_END_DATE` are populated on a minority of rows (25 of the first 200)
  and null on the rest; `TC_URL` is always present and is the registration
  deep link.
