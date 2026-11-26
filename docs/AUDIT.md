# PlayFinder v1 — Audit, UI/UX Review & Verification

Updated: 2026-11-27. This supersedes the earlier optimistic audit.

## 1. Verification evidence

All commands run with `JAVA_HOME=C:\Users\Teddy\.jdks\jbr-17.0.14`.

| Command | Result |
|---|---|
| `.\gradlew.bat test assembleDebug bundleRelease --no-daemon` | **BUILD SUCCESSFUL** (6m 41s) |
| Unit tests | **17 tests, 0 failures** |
| Debug APK | `app/build/outputs/apk/debug/app-debug.apk` |
| Signed AAB | `app/build/outputs/bundle/release/app-release.aab` |

Test breakdown (`app/build/test-results/testDebugUnitTest`):

- `FilterEngineTest` — 9 (district, time range, availability, sort, prime time, heatmap, distance, malformed time x2)
- `LcsdRecordTest` — 3 (parse, empty, null tolerance)
- `MoshiAdapterTest` — 3 (slot JSON, activity JSON, null optional columns)
- `WatchlistTest` — 2 (expiry semantics, 64-bit epoch regression)

## 2. Critical defects found and fixed

| # | Defect | Fix |
|---|---|---|
| C1 | Push expiry stored with `intPreferencesKey` + `.toInt()`; epoch millis wrapped negative, so push never activated | `longPreferencesKey("push_until_epoch")` in `alerts/WatchlistStore.kt`; `Watchlist.pushActive()`; regression test `WatchlistTest` |
| C2 | Activities never loaded: Room flow was never collected | `ActivitiesViewModel` now derives `visible` from `repo.observe(...)` via `flatMapLatest`, plus `observeAll()` for filter lists |
| C3 | Duplicate slot rows on every refresh (`autoGenerate` PK + REPLACE) | Unique index `(sport, venue, facility, location, date, startTime)` + transactional `replaceSport()`; DB version 3 |
| C4 | `POST_NOTIFICATIONS` declared but never requested on API 33+ | Runtime permission card + launcher in `ui/AlertsScreen.kt` |
| C5 | Build was red (`BuildConfig`, missing `launch` import, missing `ExperimentalLayoutApi`) | Fixed; clean build verified above |
| I1 | UI stale: `visible`/`districts`/`heatmap` were plain getters over a non-collected flow | `combine(...).stateIn(...)` in `HomeViewModel`; screens collect `StateFlow`s |
| I2 | Collector leak on sport switch; old sport could overwrite data | `observeJob?.cancel()` before re-collecting |
| I3 | Non-2xx HTTP silently showed "no results" | Repositories `error("HTTP ...")`; ViewModels show a friendly error + retry |
| I4 | Rewarded ad could hang on "loading" | `onAdFailedToShowFullScreenContent` + `try/catch` always resume |
| I5 | Poller re-alerted the same slot every 15 min and ran forever | Seen-key FIFO (800), watchlist filtering, self-cancel on expiry |
| I6 | Cache clear deleted the open Room database file | `SettingsViewModel` + DAO `clearAll()` |
| I7 | Watchlist stored only a sport | Sports + districts + venues setters; long-press a slot to watch its sport and district |
| I8 | 3-minute reward gate not enforced | 180-second in-app countdown after the ad (`AlertsScreen`); leaving cancels the grant |
| M1 | `minuteOf` returned 0 for malformed times, passing every filter | Returns `-1`; excluded by filters and heatmap |
| M2 | Non-null DTO fields aborted a whole refresh on JSON `null` | All DTO fields nullable + null-tolerant tests |
| M3 | Only 7 of 14 date chips reachable | Full 14-day list inside the filter sheet |
| M4 | No launcher icon | Adaptive icon (`mipmap-anydpi-v26`) + manifest `android:icon` |
| M5 | Dead `LcsdMetadata` endpoint modelled the wrong envelope | Removed |

## 3. UI/UX changes (research-driven)

Source check: `github.com/topics/user-interface` lists desktop/terminal toolkits (iced, Slint, MAUI, tview, FTBUI…). No Compose repos on page 1, so patterns were taken from **android/nowinandroid**, **android/compose-samples (JetNews)** and **Material 3 tokens**.

| Change | Why |
|---|---|
| Home chrome reduced: sport chips + search + one “篩選 (n)” button; dates/district/time/sort moved into a `ModalBottomSheet` | Four stacked filter rows ate ~200dp before any content |
| Active-filter chips with one-tap removal | Filters were applied but invisible |
| Distinct states: skeleton loading, first-sync empty, no-results (with 清除篩選), error (with 重試), offline banner | Previously all collapsed into one string, and raw exception text was shown |
| Pull-to-refresh replaces the floating button | Refresh is discoverable; FAB no longer covers the last row |
| “更新於 X 分鐘前” + offline banner | Users can tell live data from stale cache |
| Heatmap: 12 two-hour buckets, hour labels, 少→多 legend, tap to filter, per-cell content description | 24 cells at 360dp were ~12dp wide and unreadable; colour alone carried meaning |
| Slot row: venue truncates with ellipsis, time on its own line, availability pill with icon + text (“3 位” / “滿額”), separate overflow icon | Six fields concatenated into a 3-line wrap; the count looked like a label, not a menu |
| Material icons + `contentDescription` (refresh, locate, more, available/full) | Emoji are announced as “round pushpin” by TalkBack |
| Real dark theme (`PlayFinderTheme`, dynamic colour on Android 12+, `values-night`) | App was light-only; night-time court checking was glaring |
| 通知 and 設定 are now separate screens | Both tabs previously rendered the same screen |
| Long-press a slot → watch sport + district, with snackbar confirmation | Watchlist was effectively undiscoverable |
| Settings: cache counts, confirmation dialog, snackbar result | Destructive action ran without confirmation |
| Search text survives rotation (`rememberSaveable`) | Typed query was lost |

## 4. Spec coverage (honest status)

| Spec item | Status | Notes |
|---|---|---|
| Sport chips (6 sports incl. programme activities) | ✅ | 5 court sports; activities have their own tab |
| Venue / date / time / availability | ✅ | |
| Availability colour + non-colour signal | ✅ | Pill text + icon |
| Prime-time badge (Mon–Fri 19–22) | ✅ | |
| Search, district, date, time, only-available | ✅ | Debounce not implemented (in-memory filter is cheap) |
| Sort time / availability / distance | ✅ | |
| GPS distance sort | ✅ | FusedLocationProvider, runtime permission |
| Heatmap | ✅ | 12 buckets, legend, tappable |
| Activities browse + detail fields + registration link | ✅ | Card shows venue/time/fee/quota/target/enrol method; 報名 opens `TC_URL` |
| Watchlist | ✅ (sport/district/venue) | Per-slot subscription is approximated by sport+district |
| Push on new slot, deduped, ad-gated | ✅ | Local 15-min poll (not ntfy/SSE) |
| 3-minute reward gate → 1 week | ✅ | Enforced in-app |
| Offline cache | ✅ | Room v3, snapshot replace |
| Share to WhatsApp/Telegram | ✅ | System chooser |
| No accounts / no personal data | ✅ | DataStore only |
| ProGuard/R8 + shrink, network security config, privacy policy | ✅ | |
| Deep link to a *specific* slot booking | ⚠️ | SmartPLAY exposes no public per-slot URL; opens the official site |
| ntfy anonymous subscription | ❌ (deferred) | Worker polls LCSD directly; class renamed `SlotPollWorker` to stop claiming ntfy |
| Sale-day digest / programme alerts / weekday+5-venue caps | ❌ (v2) | Not implemented |

## 5. Remaining known limitations

1. **AdMob test IDs** are still in place (`ca-app-pub-3940256099942544/...`). Replace before release or the build violates AdMob policy.
2. **Upload keystore** is the generated `playfinder-release.jks` (password in `keystore.properties`). Replace with your own and back it up.
3. Push polling is subject to Doze/App Standby; 15 minutes is a floor, not a guarantee.
4. Watchlist does not yet enforce the “max 5 venues” rule from the spec.
5. Location sorting requests `lastLocation`; if no cached fix exists the list falls back to venue-name order.
6. Full i18n is not done: UI copy is Cantonese/Chinese; content descriptions are in `strings.xml`.
7. No instrumented/UI tests (unit tests only); Compose UI tests would need an emulator.

## 6. Formal verification

`docs/formal/PlayFinder.lean` (Lean 4) proves:

- grant expiry is monotonic (`grant` never shortens an active window),
- `pushActive ⇔ enabled ∧ now < expiry`,
- watchlist size bound,
- availability → colour mapping.

TLA+ is intentionally omitted: the app has no concurrent protocol; the only background actor is a single periodic worker whose safety property is the expiry invariant above.

## 7. Release checklist

1. Replace test AdMob app ID (manifest) and rewarded unit ID (`ads/RewardedAdManager.kt`).
2. Replace/back up the upload keystore.
3. Play Console: privacy policy URL (`PRIVACY.md`), data safety (no data collected, location not stored/uploaded), content rating 12+, ads disclosure.
4. Test on a physical API 33+ device: grant push, background the app, confirm a notification, confirm no duplicate alerts.
