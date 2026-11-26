# Stage 9 — Implementation Readiness Test

Target: `docs/designs/2026-11-26-playfinder-android-plan.md` (lines 1-420)
Reviewer: fresh-context Goldfish (`agents/implementation_readiness.md`,
`agents/codebase_details.md`), read-only.

## Verdict

The plan fails the Zero-Decision Rule and the Test Plan requirement. The file
and interface boundary was abandoned almost wholesale: the executed app is a
different architecture, and roughly ten architectural decisions were invented
during implementation because the plan never made them.

## Implementation-readiness findings

### I1 — Blocker — Task 8 mandates ntfy, the code polls from the device
`NtfySubscriber.kt` and `PushManager` do not exist. The root cause the plan
could not have predicted: the only publisher in this repository
(`poller/notify.py`) POSTs to one global ntfy topic, so there is no
per-device or per-watchlist topic, and the plan specifies no server change to
create one.
**Guidance:** state the transport decision explicitly, rename the interfaces to
`WatchlistStore.isPushActive()` / `grantPush(weeks)`, and delete the ntfy file
list. *(Implemented: `WatchlistStore` + `SlotPollWorker`; the plan now records
the decision.)*

### I2 — Blocker — the watchlist model in the plan is not the one implemented
The plan's watchlist entity is `(sport, venue, weekday, timeStart, timeEnd,
createdAt)` in Room; the code stores DataStore sets. "Watch every weekday
19:00–21:00" was not expressible.
**Guidance:** pin the watchlist model and the alert-matching predicate,
including empty-set semantics. *(Implemented: sports, districts, venues,
weekdays, time window and quiet hours; the matching predicate is documented in
`alerts/README.md`.)*

### I3 — Blocker — the reward gate does not measure what the plan says
The plan requires "3 full minutes of view"; the code grants the reward the
instant the rewarded callback fires, with a separate 180-second Compose
countdown that is cancelled when the user leaves. Separately,
`MobileAds.initialize()` was never called, so **no ad could ever load**.
**Guidance:** specify where SDK init happens and move the timer out of
composable scope. *(Implemented: `MobileAds.initialize(this)` in
`PlayFinderApp.onCreate`.)*

### I4 — Major — the dependency list is wrong and incomplete
kapt vs KSP, and the plan omits `work-runtime-ktx`, `hilt-work`,
`navigation-compose`, `moshi-kotlin-codegen` and every test dependency.
**Guidance:** paste the exact `build.gradle.kts` block. *(The plan now points
at the build file.)*

### I5 — Major — the planned tests are not executable as written
Room DAO tests need `room-testing` or Robolectric; "mock Retrofit" needs
`mockwebserver`; ViewModel tests need `kotlinx-coroutines-test`. Six planned
test files do not exist. Actual coverage: pure JVM logic only — no coverage of
the Room schema, `replaceSport`/`replaceAll`, the poller, the ad gate, the
deep link, `WatchlistStore` persistence, or either ViewModel.
**Guidance:** name the test file, dependency set, assertion and run command per
behaviour; assign Room/WorkManager tests to `androidTest`. *(Partly
implemented: `core/ReleaseDetectorTest` and `core/FilterEngineTest` now cover
the release-detection and filter logic; the rest remain open.)*

### I6 — Major — AdMob configuration is unspecified
Only an AdSense publisher id is given; AdMob needs an application id and ad
unit ids. The manifest hardcodes Google's test ids with no release flag.
`ads.txt` also lives at the repository root, not in `app/src/main/assets/`.
**Guidance:** add an AdMob configuration block and a rule that test ids must be
swapped before release. *(Implemented: `app/src/main/assets/ads.txt` and a
release checklist item.)*

### I7 — Major — Task 14's CI and release steps are missing
`.github/workflows/build-apk.yml` did not exist; release signing was
unspecified and the `if (kp.exists())` guard left a release build with no
store file on a clean checkout; `isMinifyEnabled` was on with an empty
`proguard-rules.pro`.
**Guidance:** add the CI file, keystore provisioning via secrets, keep rules and
the Play Console checklist. *(Implemented: `.github/workflows/android-apk.yml`,
ProGuard rules, and a release-signing guard that fails with a clear message.)*

### I8 — Major — the schema in the plan does not match the code
Plan: `version = 1`, `SlotEntity(sport, venue, facility, date, startTime,
endTime, courts, fetchedAt)`, DAO queries by sport/venue/date. Code: version 4
with destructive migration, a unique composite index, and venue/district
filtering done in memory by `FilterEngine`.
**Guidance:** publish the exact tables, index set, version and migration policy,
and say whether filtering is SQL or in-memory.

### I9 — Major — `Resource<T>` and the staleness badge do not exist
`lastSync` lived in ViewModel memory, so the "last updated" badge disappears
after process death.
**Guidance:** persist `lastFetchedAt` and define the staleness threshold.

### I10 — Major — the DeepLink API in the plan was never specified
No URL template, no parameter mapping, and no statement that per-session
booking URLs do not exist.
**Guidance:** state the exact template or state that only the landing page is
supported. *(Implemented: the spec now states the limitation.)*

### I11 — Major — the screen decomposition in the plan was abandoned
`SearchScreen`, `WatchlistScreen`, `AboutScreen`, `PlayFinderNavGraph`,
`BottomNavBar`, `SportChipRow`, `SlotHeatmap`, `SlotCard`, `FilterBar` do not
exist; `HomeScreen.kt` inlines all of it. A write allowlist built from the
plan would flag most of the real tree as out of scope.
**Guidance:** update the file lists to the as-built decomposition or state the
boundary as a directory glob.

### I12 — Nit — DTO column names in the plan are wrong
The plan names `Date`; the feed uses `Available_Date`. It omits
`District_Name_TC`, `Facility_Location_Name_TC`, the coordinates and
`Available_Courts`, and specifies a metadata endpoint that has no consumer.

### I13 — Nit — tasks without verification steps, and a write conflict
Tasks 7, 11 and 12 end at "Commit" with no verification; Task 9's only check
is manual; Task 9 modifies a file Task 8 creates.
**Guidance:** give every task a verification command and sequence the conflict.

## Codebase-details findings (documentation accuracy)

Eleven 🔴 Blockers: the data-layer architecture described does not exist;
ntfy does not exist; the plan's file inventory does not match the tree; three
documented availability colours against two implemented (with "no data"
conflated with "full"); venue cards and a date picker do not exist; the
activity "instructor" and "registration period" fields do not exist; the push
filter config is a subset of the documented one; the sale7 digest and
programme-activity push do not exist; the slot deep link is a fixed URL; the
"banner + rewarded video" model is rewarded video only; and the AdSense
publisher id appears in no code.

Nine 🟡 Majors: no debounce and no time-range slider; the heatmap is an
hour-of-day histogram, not a 7-day grid; undocumented hardcoded values
(channel id, poll interval, 180-second gate, 800-key cap, 7-day grant,
prime-time window, sport list, base URLs, database version, destructive
migration, malformed-timestamp handling, nullable upstream columns, non-2xx
handling, notification permission, Doze limits, empty ProGuard rules); no
CI/CD and stale status in both documents; and a test plan that does not match
the tests that exist.

Five 🟢 Nits: emoji in the prime-time bullet, "Sport → District" versus
district + type filtering, the removed metadata endpoint, and vocabulary that
mixes slot / session / venue / facility / location.

## Bottom line

The spec describes a push-first, ntfy-subscribed, banner-ad, venue-card app
with three-state availability, weekday/time-range/five-venue push filters,
quiet hours and a sale7 digest. The code was a local-poll, rewarded-video-only
app with a flat session list, two-state availability, sport+district filters
and no quiet hours. Both documents must be re-baselined against the
implementation.
