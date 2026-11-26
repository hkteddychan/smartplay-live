# PlayFinder v1 — Comprehensive Audit

## Build & Test
- `./gradlew assembleDebug` → BUILD SUCCESSFUL
- `./gradlew test` → BUILD SUCCESSFUL

## Spec coverage
| Spec item | Status | Where |
|---|---|---|
| Browse vacancies (sport chips, venue, date, time, colour) | ✅ | HomeScreen, SlotRow colour |
| Prime-time badge | ⚠️ partial | not yet rendered |
| Pull-to-refresh / offline indicator | ✅ | FAB refresh, loading/error, empty state |
| Programme activities | ⚠️ partial | ActivityRepository/DAO only, no screen |
| Search filters (date/time/district) | ❌ | not implemented |
| Watchlist long-press | ✅ | SlotRow dropdown |
| ntfy push (ad-gated) | ✅ | NtfyPollWorker (15 min) + WatchlistStore |
| Settings (push status, disclaimer) | ✅ | SettingsScreen |
| Deep link to booking | ✅ | SlotRow menu + DeepLink |
| Share WhatsApp | ✅ | SlotRow menu |
| Offline Room cache | ✅ | PlayFinderDatabase |
| Location distance sort | ❌ | not implemented |
| Heatmap | ⚠️ partial | colour per row only |

## Formal verification
- Lean 4 file: `docs/formal/PlayFinder.lean` proves grant-expiry, push-active, watchlist≤5, and colour invariants.
- TLA+ not used: Android UI is not a concurrent protocol; the only concurrency (WorkManager poll) is single-threaded and the safety property is the expiry invariant proved in Lean.

## Known gaps to close next
1. Activities screen + detail.
2. Search filter bar (district/date/time) with debounce.
3. Prime-time badge rendering.
4. Location permission + distance sort.
5. Full heatmap grid.
6. Real AdMob unit IDs + signed AAB.