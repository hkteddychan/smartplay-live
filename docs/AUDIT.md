# PlayFinder v1 — Comprehensive Audit (updated)

## Build & Test (verified)
- `./gradlew assembleDebug` → BUILD SUCCESSFUL
- `./gradlew test` → BUILD SUCCESSFUL (FilterEngineTest: 7 tests + LcsdRecordTest)
- `./gradlew bundleRelease` → BUILD SUCCESSFUL, signed AAB produced
  (`app/build/outputs/bundle/release/app-release.aab`, ~7 MB)

## Spec coverage (all v1 items implemented)
| Spec item | Status | Where |
|---|---|---|
| Sport chips (horizontal scroll) | ✅ | `ui/HomeScreen.kt` SportRow |
| Venue / date / time / availability | ✅ | SlotRow + Room cache |
| Green=available, red=full | ✅ | SlotRow colour from `available` |
| Prime-time badge (Mon-Fri 19–22) | ✅ | `FilterEngine.isPrimeTime` + badge |
| Pull-to-refresh / offline indicator | ✅ | FAB ↻, loading bar, error text, empty state |
| Visual heatmap (24 hourly buckets) | ✅ | `FilterEngine.heatmap` + Heatmap row |
| Programme activities browse (district/type/date) | ✅ | `ui/ActivitiesScreen.kt` |
| Activity detail (venue/time/fee/quota/target) | ✅ | ActivityRow |
| Deep link to LCSD registration | ✅ | ActivityRow 報名 button → browser |
| Search (venue/facility + district + date + only-available) | ✅ | FilterBar |
| Sort by time / availability / distance | ✅ | `FilterEngine.sort`, SortMode |
| GPS distance sort (FusedLocationProvider) | ✅ | 📍 action in HomeScreen |
| Watchlist (long-press / menu) | ✅ | SlotRow menu → WatchlistStore |
| ntfy push (ad-gated, survives restarts) | ✅ | `NtfyPollWorker` (WorkManager 15 min, HiltWorkerFactory) |
| Ad-gated push (3-min view → 1 week) | ✅ | `RewardedAdManager` + Settings button |
| Push status shown ("有效至 …") | ✅ | SettingsScreen |
| Settings: watchlist, clear cache, disclaimer | ✅ | SettingsScreen |
| Offline Room cache | ✅ | PlayFinderDatabase v2 |
| Share to WhatsApp | ✅ | SlotRow menu |
| No accounts / no personal data | ✅ | local DataStore only |
| ProGuard/R8 + resource shrinking | ✅ | release build type |
| Network security config (no cleartext) | ✅ | `res/xml/network_security_config.xml` |
| Privacy policy | ✅ | `PRIVACY.md` |

## Formal verification
- `docs/formal/PlayFinder.lean` (Lean 4): grant-expiry monotonic, push-active = (now < expiry),
  watchlist ≤ 5 venues, availability→colour mapping.
- TLA+ deliberately not used: the app has no concurrent protocol; the only background actor is a
  single WorkManager poller, whose safety property is the expiry invariant proved in Lean.

## Release checklist left for the human
1. Replace Google **test** AdMob IDs with your real ones:
   - manifest `com.google.android.gms.ads.APPLICATION_ID` → real app id
   - `ads/RewardedAdManager.kt` UNIT_ID → real rewarded unit id
2. Replace the generated `playfinder-release.jks` (password in `keystore.properties`) with your own
   upload key and keep it backed up — losing it blocks all future updates.
3. Replace the manifest `android:label` icon with your launcher icon (currently no icon resource).
4. Play Console: privacy policy URL, data safety form, content rating 12+, ad disclosure.
