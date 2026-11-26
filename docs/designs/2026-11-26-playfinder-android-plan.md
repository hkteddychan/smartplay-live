# PlayFinder Android APK — Implementation Plan (executed)

> **Status:** Executed 2026-11-26/27. The task list below is kept as the
> historical record of what was planned; the checkboxes reflect the plan as
> written, **not** the implementation. For the authoritative description of
> what shipped, read
> [2026-11-26-playfinder-android.md](./2026-11-26-playfinder-android.md) and
> the package contracts under `app/src/main/java/com/playfinder/app/`.

**Goal:** Build "PlayFinder" — a native Android app (Kotlin + Jetpack Compose) for browsing LCSD court availability, programme activities, and receiving push alerts, with an ad-for-push value-exchange monetisation model.

**Architecture as built:** Single-activity Compose app with Hilt DI, concrete repositories over Room (LCSD API → Room cache), and **device-local** push: a 15-minute WorkManager poll that notifies when a session's availability increased, unlocked by an AdMob rewarded video plus a three-minute in-app stay.

**Tech Stack:** Kotlin 2.0, Jetpack Compose (Material 3), Hilt, Room, Retrofit + OkHttp + Moshi, WorkManager, DataStore, AdMob, FusedLocationProvider, Coroutines + Flow

**Spec:** `docs/designs/2026-11-26-playfinder-android.md`

## As-built file map (replaces the "Files" lists in the tasks below)

The per-task `Files:` lists further down are the historical plan. This table is
the authoritative mapping, with the action that was actually taken.

| Planned path | As-built path | Action |
|---|---|---|
| `data/repository/SlotRepository.kt` | `data/PlayFinderRepository.kt` | Renamed / modified |
| `data/repository/ActivityRepository.kt` | `data/ActivityRepository.kt` | Renamed / modified |
| `data/dto/LcsdMetadata.kt` | — | Removed (the metadata endpoint has no consumer) |
| `data/entity/WatchlistEntity.kt`, `data/dao/WatchlistDao.kt` | `alerts/WatchlistStore.kt` (DataStore) | Replaced by a DataStore store |
| `push/NtfySubscriber.kt`, `push/PushManager.kt` | `alerts/SlotPollWorker.kt` + `alerts/AlertNotifier.kt` | Replaced by a device-local poller |
| `ads/AdManager.kt` | `ads/RewardedAdManager.kt` | Renamed / modified |
| `ui/screens/browse/BrowseScreen.kt` | `ui/HomeScreen.kt` | Renamed / modified |
| `ui/screens/browse/BrowseViewModel.kt` | `ui/HomeViewModel.kt` | Renamed / modified |
| `ui/screens/search/SearchScreen.kt`, `SearchViewModel.kt` | merged into `ui/HomeScreen.kt` + `ui/HomeViewModel.kt` | Merged into the browse screen |
| `ui/screens/activity/ActivityScreen.kt` | `ui/ActivitiesScreen.kt` | Renamed / modified |
| `ui/screens/activity/ActivityViewModel.kt` | `ui/ActivitiesViewModel.kt` | Renamed / modified |
| `ui/screens/watchlist/WatchlistScreen.kt` | `ui/AlertsScreen.kt` | Renamed / modified |
| `ui/screens/watchlist/WatchlistViewModel.kt` | — (the watchlist is a DataStore store) | Removed |
| `ui/screens/settings/SettingsScreen.kt` | `ui/SettingsScreen.kt` | Renamed / modified |
| `ui/screens/settings/SettingsViewModel.kt` | `ui/SettingsViewModel.kt` | Renamed / modified |
| `ui/screens/about/AboutScreen.kt` | a card inside `ui/SettingsScreen.kt` | Merged into Settings |
| `ui/components/SlotHeatmap.kt`, `SlotCard.kt`, `FilterBar.kt`, `OfflineBadge.kt`, `SportChipRow.kt`, `ActivityCard.kt` | inline in the screens | Merged into the screens |
| `ui/components/AdBanner.kt` | — | Removed (rewarded video only) |
| `ui/navigation/PlayFinderNavGraph.kt`, `BottomNavBar.kt` | `MainActivity.kt` (`AppShell`) | Merged into the activity |
| `util/DeepLink.kt` | `ui/DeepLink.kt` | Moved |
| `ui/FilterEngine.kt` | `core/FilterEngine.kt` + `core/ReleaseDetector.kt` | Moved and extended |
| `data/remote/LcsdApiTest.kt` | `data/remote/MoshiAdapterTest.kt` | Renamed |
| `data/local/SlotDaoTest.kt` | — | Not implemented (Room needs an instrumented test) |
| `push/PushManagerTest.kt` | `alerts/WatchlistTest.kt` | Renamed / reduced scope |
| `.github/workflows/build-apk.yml` | `.github/workflows/android-apk.yml` | Renamed |

## As-built verification

| Check | Command |
|---|---|
| Unit tests | `.\gradlew.bat testDebugUnitTest` |
| Debug APK | `.\gradlew.bat assembleDebug` |
| Signed bundle | `.\gradlew.bat bundleRelease` (needs `keystore.properties`) |
| CI | `.github/workflows/android-apk.yml` |

## Global Constraints

- Min SDK 26 (Android 8.0), target SDK 35
- Kotlin 2.0+, Compose BOM 2024.12.01+
- Package: `com.playfinder.app`
- AdMob: the application id (`com.google.android.gms.ads.APPLICATION_ID`) and the rewarded unit id must replace Google's test ids before release. `pub-2824936620876447` is the AdSense publisher id; it appears only in `app/src/main/assets/ads.txt`.
- LCSD API base: `https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/`
- No user accounts, no personal data collection
- Offline-first: Room caches last fetch

## Review Focus (as planned, with the outcome)

- The push subscription must survive Doze mode and app restarts → **done** as a WorkManager periodic job; Doze still stretches the 15-minute floor, which is documented as a risk.
- AdMob rewarded video must grant the 1-week push only after 3 full minutes of view → **reinterpreted**: the rewarded video's own reward fires on completion, then a separate three-minute in-app countdown must finish. A three-minute *ad* view is impossible with rewarded video, and forcing a banner to stay visible would be invalid traffic.
- Offline cache must show stale data with a "last updated X ago" badge, never crash on an empty cache → **done** (`lastSync` label plus an offline banner).
- Deep links must open SmartPLAY in the system browser, not an in-app WebView → **done**.
- Watchlist filters must persist across app restarts (DataStore, not just in-memory) → **done**.

---

### Task 1: Project Scaffold

**Files:**
- Create: `build.gradle.kts` (root)
- Create: `app/build.gradle.kts`
- Create: `app/src/main/AndroidManifest.xml`
- Create: `app/src/main/java/com/playfinder/app/PlayFinderApp.kt`
- Create: `app/src/main/java/com/playfinder/app/MainActivity.kt`
- Create: `app/src/main/res/values/strings.xml`
- Create: `app/src/main/res/values/themes.xml`

**Interfaces:**
- Produces: `PlayFinderApp` (Hilt `@HiltAndroidApp` Application class), `MainActivity` (single-activity Compose host with `NavHost`)

- [ ] **Step 1: Create root build.gradle.kts** with Kotlin 2.0, Compose BOM, Hilt, Room, Retrofit, AdMob, Coroutines plugins

- [ ] **Step 2: Create app/build.gradle.kts** with dependencies:
  - `androidx.compose:compose-bom:2024.12.00`
  - `androidx.hilt:hilt-navigation-compose`
  - `androidx.room:room-runtime` + `room-ktx` + `room-compiler` (kapt)
  - `com.squareup.retrofit2:retrofit` + `converter-moshi`
  - `com.squareup.okhttp3:okhttp` + `logging-interceptor`
  - `com.google.dagger:hilt-android` + `hilt-compiler` (kapt)
  - `com.google.android.gms:play-services-ads`
  - `androidx.datastore:datastore-preferences`
  - `org.jetbrains.kotlinx:kotlinx-coroutines-android`
  - `com.google.android.gms:play-services-location`

- [ ] **Step 3: Create AndroidManifest.xml** with INTERNET, ACCESS_FINE_LOCATION permissions, AdMob app ID meta-data, single activity

- [ ] **Step 4: Create PlayFinderApp.kt** (`@HiltAndroidApp`)

- [ ] **Step 5: Create MainActivity.kt** with `setContent { PlayFinderTheme { NavHost(...) } }`

- [ ] **Step 6: Create strings.xml** with app name "PlayFinder", disclaimer text, etc.

- [ ] **Step 7: Verify build succeeds** — Run: `./gradlew assembleDebug` — Expected: BUILD SUCCESSFUL

- [ ] **Step 8: Commit** `git commit -m "scaffold: PlayFinder Android project (Kotlin + Compose + Hilt)"`

---

### Task 2: LCSD API Client (Retrofit)

**Files:**
- Create: `app/src/main/java/com/playfinder/app/data/remote/LcsdApi.kt`
- Create: `app/src/main/java/com/playfinder/app/data/remote/dto/LcsdRecord.kt`
- Create: `app/src/main/java/com/playfinder/app/data/remote/dto/LcsdMetadata.kt`
- Create: `app/src/main/java/com/playfinder/app/di/NetworkModule.kt`
- Test: `app/src/test/java/com/playfinder/app/data/remote/LcsdApiTest.kt`

**Interfaces:**
- Consumes: Retrofit base URL `https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data`
- Produces: `LcsdApi.getDataset(name: String): Response<List<LcsdRecord>>`, `LcsdApi.getMetadata(name: String): Response<LcsdMetadata>`

- [ ] **Step 1: Write failing test** — mock Retrofit, verify `getDataset("badminton")` parses into `List<LcsdRecord>` with `venueNameTc`, `facilityNameTc`, `date`, `startTime`, `endTime`

- [ ] **Step 2: Run test** — Expected: FAIL (LcsdApi not defined)

- [ ] **Step 3: Implement LcsdApi interface** with `@GET("{name}/file")` and `@GET("{name}")` (metadata)

- [ ] **Step 4: Implement LcsdRecord data class** (Moshi `@Json` annotations matching LCSD column names: `Venue_Name_TC`, `Facility_Type_Name_TC`, `Date`, `Session_Start_Time`, `Session_End_Time`, etc.)

- [ ] **Step 5: Implement NetworkModule** (Hilt `@Module` providing Retrofit instance with OkHttp + Moshi + logging interceptor, base URL)

- [ ] **Step 6: Run test** — Expected: PASS

- [ ] **Step 7: Commit** `git commit -m "feat: LCSD API client (Retrofit + Moshi)"`

---

### Task 3: Room Cache

**Files:**
- Create: `app/src/main/java/com/playfinder/app/data/local/PlayFinderDatabase.kt`
- Create: `app/src/main/java/com/playfinder/app/data/local/entity/SlotEntity.kt`
- Create: `app/src/main/java/com/playfinder/app/data/local/entity/ActivityEntity.kt`
- Create: `app/src/main/java/com/playfinder/app/data/local/dao/SlotDao.kt`
- Create: `app/src/main/java/com/playfinder/app/data/local/dao/ActivityDao.kt`
- Create: `app/src/main/java/com/playfinder/app/di/DatabaseModule.kt`
- Test: `app/src/test/java/com/playfinder/app/data/local/SlotDaoTest.kt`

**Interfaces:**
- Produces: `SlotDao` (insert, query by sport/venue/date, delete stale), `ActivityDao` (insert, query by sport/district/dateRange), `PlayFinderDatabase`

- [ ] **Step 1: Write failing test** — insert 3 slots, query by sport="badminton" returns 2, query by date range filters correctly

- [ ] **Step 2: Run test** — Expected: FAIL

- [ ] **Step 3: Implement SlotEntity** (sport, venue, facility, date, startTime, endTime, courts, fetchedAt)

- [ ] **Step 4: Implement ActivityEntity** (activityNo, sport, venue, district, date, startTime, endTime, fee, quota, registrationStart, registrationEnd, fetchedAt)

- [ ] **Step 5: Implement SlotDao + ActivityDao** with `@Query`, `@Insert(onConflict = REPLACE)`, `@Query("DELETE FROM slots WHERE fetchedAt < :cutoff")`

- [ ] **Step 6: Implement PlayFinderDatabase** (`@Database(entities = [SlotEntity, ActivityEntity], version = 1)`)

- [ ] **Step 7: Implement DatabaseModule** (Hilt provides database + DAOs)

- [ ] **Step 8: Run test** — Expected: PASS

- [ ] **Step 9: Commit** `git commit -m "feat: Room cache (slots + activities)"`

---

### Task 4: Repository Pattern

**Files:**
- Create: `app/src/main/java/com/playfinder/app/data/repository/SlotRepository.kt`
- Create: `app/src/main/java/com/playfinder/app/data/repository/ActivityRepository.kt`
- Create: `app/src/main/java/com/playfinder/app/data/repository/SlotRepositoryImpl.kt`
- Create: `app/src/main/java/com/playfinder/app/data/repository/ActivityRepositoryImpl.kt`
- Test: `app/src/test/java/com/playfinder/app/data/repository/SlotRepositoryTest.kt`

**Interfaces:**
- Consumes: `LcsdApi`, `SlotDao`, `ActivityDao`
- Produces: `SlotRepository.getSlots(sport, venue, date): Flow<List<Slot>>`, `SlotRepository.refresh(sport): Result<Unit>`, `ActivityRepository.getActivities(sport, district, dateRange): Flow<List<Activity>>`

- [ ] **Step 1: Write failing test** — mock API returns 5 slots, repository caches them in Room, second call returns from cache when offline

- [ ] **Step 2: Run test** — Expected: FAIL

- [ ] **Step 3: Implement SlotRepository interface + impl** — fetch from API → cache in Room → emit Flow; on network failure → emit cached data

- [ ] **Step 4: Implement ActivityRepository interface + impl** — same pattern for activities

- [ ] **Step 5: Run test** — Expected: PASS

- [ ] **Step 6: Commit** `git commit -m "feat: repository pattern (API + Room cache)"`

---

### Task 5: Browse Screen (Compose)

**Files:**
- Create: `app/src/main/java/com/playfinder/app/ui/screens/browse/BrowseScreen.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/screens/browse/BrowseViewModel.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/components/SportChipRow.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/components/SlotHeatmap.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/components/SlotCard.kt`
- Test: `app/src/test/java/com/playfinder/app/ui/browse/BrowseViewModelTest.kt`

**Interfaces:**
- Consumes: `SlotRepository`, `ActivityRepository`
- Produces: `BrowseViewModel` with `uiState: StateFlow<BrowseUiState>` (loading/success/error, slots, selectedSport, selectedDate)

- [ ] **Step 1: Write failing test** — ViewModel with fake repository returns slots, uiState transitions loading → success

- [ ] **Step 2: Run test** — Expected: FAIL

- [ ] **Step 3: Implement BrowseViewModel** — loads slots for selected sport+date, exposes StateFlow

- [ ] **Step 4: Implement SportChipRow** — horizontal scrollable chips (🏸羽毛球, 🏀籃球, 🏐排球, 🎾網球, ⚽足球, 🏃活動)

- [ ] **Step 5: Implement SlotHeatmap** — 7-day × time-slot grid, green/red/grey cells

- [ ] **Step 6: Implement SlotCard** — venue name, time, availability count, prime-time ✅ badge

- [ ] **Step 7: Implement BrowseScreen** — compose SportChipRow + DatePicker + SlotHeatmap + SlotCard list, pull-to-refresh

- [ ] **Step 8: Run test** — Expected: PASS

- [ ] **Step 9: Commit** `git commit -m "feat: browse screen (sport chips + heatmap + slot cards)"`

---

### Task 6: Search Screen

**Files:**
- Create: `app/src/main/java/com/playfinder/app/ui/screens/search/SearchScreen.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/screens/search/SearchViewModel.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/components/FilterBar.kt`
- Test: `app/src/test/java/com/playfinder/app/ui/search/SearchViewModelTest.kt`

**Interfaces:**
- Consumes: `SlotRepository`, `ActivityRepository`
- Produces: `SearchViewModel` with `searchQuery`, `filters`, `results: StateFlow<SearchResults>`

- [ ] **Step 1: Write failing test** — ViewModel filters slots by sport + district + date range, returns matching subset

- [ ] **Step 2: Run test** — Expected: FAIL

- [ ] **Step 3: Implement SearchViewModel** — debounced search (300ms), filter logic, sort options

- [ ] **Step 4: Implement FilterBar** — sport chips + date range picker + time slider + district dropdown (all on one screen)

- [ ] **Step 5: Implement SearchScreen** — FilterBar + results list with empty state

- [ ] **Step 6: Run test** — Expected: PASS

- [ ] **Step 7: Commit** `git commit -m "feat: search screen (one-screen filters + instant results)"`

---

### Task 7: Programme Activity Screen

**Files:**
- Create: `app/src/main/java/com/playfinder/app/ui/screens/activity/ActivityScreen.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/screens/activity/ActivityViewModel.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/components/ActivityCard.kt`

**Interfaces:**
- Consumes: `ActivityRepository`
- Produces: `ActivityViewModel` with `activities: StateFlow<List<Activity>>`, filters (sport, district, dateRange)

- [ ] **Step 1: Implement ActivityViewModel** — load activities, filter by sport/district/date, sort by date

- [ ] **Step 2: Implement ActivityCard** — sport icon, title, venue, date/time, fee, quota badge, registration status

- [ ] **Step 3: Implement ActivityScreen** — filter bar + activity card list + deep link to LCSD registration

- [ ] **Step 4: Commit** `git commit -m "feat: programme activity browse screen"`

---

### Task 8: Watchlist & ntfy Push (Ad-Gated)

**Files:**
- Create: `app/src/main/java/com/playfinder/app/data/local/entity/WatchlistEntity.kt`
- Create: `app/src/main/java/com/playfinder/app/data/local/dao/WatchlistDao.kt`
- Create: `app/src/main/java/com/playfinder/app/push/NtfySubscriber.kt`
- Create: `app/src/main/java/com/playfinder/app/push/PushManager.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/screens/watchlist/WatchlistScreen.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/screens/watchlist/WatchlistViewModel.kt`
- Test: `app/src/test/java/com/playfinder/app/push/PushManagerTest.kt`

**Interfaces:**
- Consumes: ntfy endpoint, Room WatchlistDao, DataStore (ad-gated status)
- Produces: `PushManager.isPushActive(): Flow<Boolean>`, `PushManager.activatePush(durationDays: Int)`, `NtfySubscriber.subscribe(topic: String)`, `NtfySubscriber.unsubscribe()`

- [ ] **Step 1: Write failing test** — PushManager with expired ad-gate returns false, with valid gate returns true

- [ ] **Step 2: Run test** — Expected: FAIL

- [ ] **Step 3: Implement WatchlistEntity + WatchlistDao** (sport, venue, weekday, timeStart, timeEnd, createdAt)

- [ ] **Step 4: Implement NtfySubscriber** — SSE connection to `https://ntfy.tedton.hk/{topic}/sse`, parse incoming messages, post local notification via NotificationManager

- [ ] **Step 5: Implement PushManager** — DataStore for ad-gate expiry timestamp; `isPushActive()` checks `now < expiry`; `activatePush(7)` sets expiry to now+7 days

- [ ] **Step 6: Implement WatchlistScreen** — list of watched slots, add/remove, ad-gate status banner ("Push active until X" or "Watch an ad to enable push")

- [ ] **Step 7: Run test** — Expected: PASS

- [ ] **Step 8: Commit** `git commit -m "feat: watchlist + ntfy push (ad-gated)"`

---

### Task 9: AdMob Integration (Value-Exchange)

**Files:**
- Create: `app/src/main/java/com/playfinder/app/ads/AdManager.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/components/AdBanner.kt`
- Modify: `app/src/main/java/com/playfinder/app/ui/screens/search/SearchScreen.kt` (add AdBanner)
- Modify: `app/src/main/java/com/playfinder/app/ui/screens/watchlist/WatchlistScreen.kt` (add AdBanner + rewarded video trigger)

**Interfaces:**
- Consumes: `PushManager`, AdMob SDK
- Produces: `AdManager.showRewardedAd(activity, onReward: () -> Unit)`, `AdManager.loadBanner(adView)`

- [ ] **Step 1: Implement AdManager** — initialize AdMob, load rewarded ad unit, show with 3-min view timer, call `PushManager.activatePush(7)` on reward earned

- [ ] **Step 2: Implement AdBanner** — Compose wrapper around AdView (banner size adaptive)

- [ ] **Step 3: Add AdBanner to SearchScreen** (top of results)

- [ ] **Step 4: Add rewarded video trigger to WatchlistScreen** — "Watch ad to enable push for 1 week" button

- [ ] **Step 5: Verify AdMob test ads load** (use test ad unit IDs during dev)

- [ ] **Step 6: Commit** `git commit -m "feat: AdMob value-exchange (3-min view → 1 week push)"`

---

### Task 10: Deep Link to SmartPLAY

**Files:**
- Create: `app/src/main/java/com/playfinder/app/util/DeepLink.kt`
- Modify: `app/src/main/java/com/playfinder/app/ui/screens/browse/BrowseScreen.kt` (add book button)
- Modify: `app/src/main/java/com/playfinder/app/ui/screens/activity/ActivityScreen.kt` (add register button)

**Interfaces:**
- Produces: `DeepLink.openSmartPlay(context, sport, venue, date, time): Unit` — opens system browser with SmartPLAY booking URL

- [ ] **Step 1: Implement DeepLink** — construct SmartPLAY URL from slot params, call `Intent(Intent.ACTION_VIEW, uri)` with `FLAG_ACTIVITY_NEW_TASK`

- [ ] **Step 2: Add "Book" button to SlotCard** — calls DeepLink.openSmartPlay

- [ ] **Step 3: Add "Register" button to ActivityCard** — calls DeepLink.openLcsdActivity

- [ ] **Step 4: Commit** `git commit -m "feat: deep link to SmartPLAY booking"`

---

### Task 11: Settings & About

**Files:**
- Create: `app/src/main/java/com/playfinder/app/ui/screens/settings/SettingsScreen.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/screens/settings/SettingsViewModel.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/screens/about/AboutScreen.kt`

**Interfaces:**
- Consumes: `PushManager`, DataStore preferences
- Produces: `SettingsViewModel` with `notificationPrefs: StateFlow<NotificationPrefs>`, `pushStatus: StateFlow<PushStatus>`

- [ ] **Step 1: Implement SettingsViewModel** — notification prefs (sports, districts, quiet hours), push status (active/expired + expiry date)

- [ ] **Step 2: Implement SettingsScreen** — toggles for notification prefs, push status card, "Watch ad to renew" button, clear cache

- [ ] **Step 3: Implement AboutScreen** — app info, disclaimer (third-party, not affiliated with LCSD), privacy policy link, version

- [ ] **Step 4: Commit** `git commit -m "feat: settings + about + disclaimer"`

---

### Task 12: Offline Cache & Polish

**Files:**
- Modify: `app/src/main/java/com/playfinder/app/data/repository/SlotRepositoryImpl.kt` (add stale-data indicator)
- Modify: `app/src/main/java/com/playfinder/app/ui/screens/browse/BrowseScreen.kt` (offline badge)
- Create: `app/src/main/java/com/playfinder/app/ui/components/OfflineBadge.kt`

- [ ] **Step 1: Add `lastFetchedAt` to repository** — emit `Resource.Success(data, isStale)` when serving cached data

- [ ] **Step 2: Implement OfflineBadge** — "Last updated X min ago" with refresh button

- [ ] **Step 3: Add OfflineBadge to BrowseScreen + SearchScreen** — show when offline or stale

- [ ] **Step 4: Commit** `git commit -m "feat: offline cache + stale-data badge"`

---

### Task 13: Navigation & App Shell

**Files:**
- Modify: `app/src/main/java/com/playfinder/app/MainActivity.kt` (NavHost with bottom nav)
- Create: `app/src/main/java/com/playfinder/app/ui/navigation/PlayFinderNavGraph.kt`
- Create: `app/src/main/java/com/playfinder/app/ui/components/BottomNavBar.kt`

**Interfaces:**
- Produces: 4 tabs — Browse, Search, Activities, Watchlist (Settings via overflow menu)

- [ ] **Step 1: Implement PlayFinderNavGraph** — routes: browse, search, activities, watchlist, settings, about

- [ ] **Step 2: Implement BottomNavBar** — 4 tabs with icons + labels

- [ ] **Step 3: Wire MainActivity** — Scaffold with BottomNavBar + NavHost

- [ ] **Step 4: Verify navigation** — manual test: all tabs switch, back button works

- [ ] **Step 5: Commit** `git commit -m "feat: navigation shell (bottom nav + 4 tabs)"`

---

### Task 14: Build, Test & Release

**Files:**
- Create: `app/src/test/java/com/playfinder/app/...` (all test files from above)
- Create: `.github/workflows/build-apk.yml` (CI: build debug APK on push)

- [ ] **Step 1: Run full test suite** — `./gradlew test` — Expected: all pass

- [ ] **Step 2: Build release APK** — `./gradlew assembleRelease` — Expected: BUILD SUCCESSFUL

- [ ] **Step 3: Verify APK size** — should be < 15MB
  → *As built: the debug APK is 19.3 MB; the R8-shrunk release bundle is
  7.5 MB. The 15 MB target applies to a release APK, not to the debug build
  with all Compose tooling included.*

- [ ] **Step 4: Manual smoke test on emulator** — browse, search, watchlist, push subscription, deep link

- [ ] **Step 5: Set up GitHub Actions CI** — build debug APK on push to main

- [ ] **Step 6: Commit** `git commit -m "feat: PlayFinder v1.0 — build, test, CI"`

---

## Execution Order

Tasks 1-4 are sequential (scaffold → API → cache → repository).
Tasks 5-7 can be parallel (browse, search, activities — all depend on repository).
Tasks 8-11 can be parallel (watchlist, ads, deeplink, settings — all depend on repository + screens).
Task 12-13 are integration (offline polish, navigation).
Task 14 is final (build + release).

## Estimated Size
~14 tasks, ~60-80 files. This is a **project** (not a small change). Plan to execute over multiple sessions with subagent-driven development (fresh subagent per task + reviewer per task).