# PlayFinder — Audit, UI/UX Review & Verification

Updated 2026-11-27 (after the EGM goldfish review cycle). This supersedes the
earlier audits.

## 1. Verification evidence

| Command | Result |
|---|---|
| `.\gradlew.bat test assembleDebug bundleRelease --no-daemon` | **BUILD SUCCESSFUL** |
| Unit tests | **23 tests, 0 failures** |
| Debug APK | `app/build/outputs/apk/debug/app-debug.apk` |
| Signed AAB | `app/build/outputs/bundle/release/app-release.aab` |
| CI | `.github/workflows/android-apk.yml` (unit tests + debug APK on push) |

Test breakdown (`app/build/test-results/testDebugUnitTest`):

- `core/FilterEngineTest` — 9 (district, time range, availability, sort, prime
  time, heatmap, distance, malformed time x2)
- `core/ReleaseDetectorTest` — 6 (baseline, 0→n release, n→m release, n→m
  decrease, unchanged, brand-new session)
- `alerts/WatchlistTest` — 2 (expiry semantics, 64-bit epoch regression)
- `data/LcsdRecordTest` — 3 (parse, empty, null tolerance)
- `data/remote/MoshiAdapterTest` — 3 (slot JSON, activity JSON, null columns)

## 2. Defects found and fixed

### Runtime defects (found by the first audit)

| Defect | Fix |
|---|---|
| Push expiry stored as `Int` → epoch millis wrapped, push never activated | `longPreferencesKey("push_until_epoch")`; regression test |
| Activities never loaded (Room flow never collected) | `ActivitiesViewModel` derives `visible` from the Room query |
| Duplicate slot rows on every refresh | Unique composite index + transactional `replaceSport`; DB v3 |
| `POST_NOTIFICATIONS` never requested | Runtime permission card + launcher |
| `MobileAds.initialize()` never called → **no ad could ever load** | Initialised in `PlayFinderApp.onCreate` |
| Rewarded ad could hang on "loading" | `onAdFailedToShowFullScreenContent` + `try/catch` always resume |
| Stale UI (plain getters over a non-collected flow) | `combine(...).stateIn(...)`; screens collect `StateFlow`s |
| Collector leak on sport switch | `observeJob?.cancel()` before re-collecting |
| Non-2xx HTTP silently showed "no results" | Repositories throw; the UI shows a friendly error + retry |
| Cache clear deleted the open Room file | `SettingsViewModel` + DAO `clearAll()` |
| `proguard-rules.pro` empty with R8 on | Explicit keep rules for Moshi, Retrofit, Room, WorkManager |
| HTTP logging active in release builds | Level `NONE` unless `BuildConfig.DEBUG` |
| Release signing silently produced an unsigned bundle | The build fails with an explicit message when `keystore.properties` is missing |
| No `ads.txt` in the app assets | `app/src/main/assets/ads.txt` |

### Review-cycle defects (found by the EGM goldfish reviewers)

| Defect | Fix |
|---|---|
| The poller re-announced the same slots every cycle and missed "2 → 4 courts" | Release detection moved into the repository (`core/ReleaseDetector`); events stored in a Room table; the DataStore seen-key set was deleted |
| The poller never refreshed the offline cache | The poller now goes through `PlayFinderRepository.fetchAndCache` |
| Push filters lacked weekday, time window and the five-venue cap | Added to `WatchlistStore`, the worker predicate and the Notifications screen |
| Quiet hours did not exist | Added to the store, the worker and the screen |
| Activity registration period was dropped although the feed has it | `ENROL_START_DATE` / `ENROL_END_DATE` added to the DTO, entity and card |
| Activity date range was pinned to today | `ActivityRange` (全部 / 7 日 / 30 日) pushed into the SQL query |
| Search recomputed on every keystroke | 300 ms debounce in both ViewModels |
| Date chips offered 14 days while the feed publishes ~8 | The chips now come from the dates present in the cache |
| Notification ids overwrote each other (`sport.hashCode()`) | One id per session, derived from the session key |
| The first poll flooded the notification shade | A first snapshot only establishes the baseline |
| `FilterEngine` was in `ui` but needed by the poller | Moved to `core/`, with `ReleaseDetector` alongside |
| The spec and the plan described an app that does not exist | Both re-baselined (see `docs/designs/`) |
| `PRIVACY.md` claimed ntfy delivery | Corrected to device-local polling |
| No package contracts existed | A `README.md` contract per package (Interface / Invariants / Side Effects) |

## 3. UI/UX changes (research-driven)

The `github.com/topics/user-interface` page lists desktop/terminal toolkits
only, so patterns came from **Now in Android**, **JetNews** and Material 3.

| Change | Why |
|---|---|
| Home chrome reduced to sport chips + search + one “篩選 (n)” button; dates/district/time/sort moved into a `ModalBottomSheet` | Four stacked filter rows ate ~200dp before any content |
| Active-filter chips with one-tap removal | Filters were applied but invisible |
| Distinct skeleton / first-sync / no-results / error / offline states | Previously one string, with raw exception text |
| Pull-to-refresh replaces the floating button | Refresh is discoverable; the FAB covered the last row |
| “更新於 X 分鐘前” + offline banner | Users can tell live data from stale cache |
| Heatmap: 12 two-hour buckets, hour labels, 少→多 legend, tap to filter, per-cell content description | 24 cells at 360dp were ~12dp wide and unreadable |
| Slot row: venue truncates with ellipsis, time on its own line, availability pill with icon + text (“3 位” / “滿額”), separate overflow icon | Six fields concatenated into a 3-line wrap |
| Material icons + `contentDescription` | Emoji are announced as “round pushpin” by TalkBack |
| Real dark theme (dynamic colour on Android 12+, `values-night`) | The app was light-only |
| 通知 and 設定 are now separate screens | Both tabs previously rendered the same screen |
| Long-press a session → watch its sport, district and venue (max five venues) | The watchlist was undiscoverable |
| Settings: cache counts, confirmation dialog, snackbar result | A destructive action ran without confirmation |
| Search text survives rotation (`rememberSaveable`) | The typed query was lost |

## 4. Known limitations

1. **AdMob test IDs** are still in place. Replace before release or the build
   violates AdMob policy.
2. **The upload keystore** is the generated `playfinder-release.jks`. Replace
   it and back it up.
3. Push polling is subject to Doze/App Standby; 15 minutes is a floor.
4. The poller refreshes only watched sports in the background.
5. The entitlement is device-local: reinstalling or switching device loses it.
6. No per-session booking URL exists in SmartPLAY, so a session opens the
   SmartPLAY home page.
7. No instrumented tests; the `androidTest` dependencies are declared but
   unused. The Room schema, the DAOs, the poller, the ad gate, the deep link
   and all three ViewModels have no automated coverage.
8. Full i18n is not done: the UI copy is Cantonese/Chinese.

## 5. Formal verification

`docs/formal/PlayFinder.lean` (Lean 4) proves grant-expiry monotonicity,
`pushActive ⇔ enabled ∧ now < expiry`, the watchlist bound and the
availability → colour mapping.

TLA+ is intentionally omitted: the app has no concurrent protocol; the only
background actor is a single periodic worker, whose safety property is the
expiry invariant proved in Lean.

## 6. Release checklist

1. Replace the test AdMob app id and rewarded unit id.
2. Replace and back up the upload keystore.
3. Play Console: privacy policy URL (`PRIVACY.md`), data safety (the app
   collects nothing; the ad SDK processes the advertising ID), content rating
   12+, ads disclosure.
4. Test on a physical API 33+ device: grant push, background the app, confirm
   a notification, and confirm no duplicate alerts.
