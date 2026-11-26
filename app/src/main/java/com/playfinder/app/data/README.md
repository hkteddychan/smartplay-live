# Data Layer

## Overview

The data layer of PlayFinder. It owns everything between the LCSD open-data
feed and the UI: two Retrofit endpoints, Moshi DTOs, a Room cache, a release
event log, and two repository classes that the ViewModels and the background
poller talk to.

There is deliberately no data-source interface: one upstream exists today, so
an interface would be speculative. The repositories are the seam where a
feed-api Worker would be added later.

## Interface

- `PlayFinderRepository` — `@Singleton`, injected with `LcsdApi`, `SlotDao`
  and `ReleaseEventDao`
  - `observeSlots(sport: String): Flow<List<SlotEntity>>`
  - `suspend refreshSport(sport: String)`
  - `suspend fetchAndCache(sport: String): List<SlotEntity>` — fetch, diff,
    cache, and record release events
  - `suspend pendingReleaseEvents(limit: Int): List<ReleaseEventEntity>`
  - `suspend clearReleaseEvents(ids: List<String>)`
  - `suspend pruneReleaseEvents(olderThanMillis: Long)`
  - `suspend currentAvailability(e: ReleaseEventEntity): Int?`
- `ActivityRepository` — `@Singleton`, injected with `LcsdApi` + `ActivityDao`
  - `observe(district: String, type: String, from: String, to: String): Flow<List<ActivityEntity>>`
  - `observeAll(): Flow<List<ActivityEntity>>`
  - `suspend refresh()`
- Subdirectories:
  - [local/](./local/README.md) — Room database, DAOs, entities
  - [remote/](./remote/README.md) — Retrofit service and Moshi DTOs

## Invariants

- `fetchAndCache` throws `IllegalStateException` on a non-2xx status and on a
  null body, so the UI can tell "offline" apart from "no sessions".
- `refresh` throws the same way for the activity feed.
- Rows without a usable `date` + `startTime` are dropped before persistence.
- Activity rows without a non-blank `ACTIVITY_NO` are dropped.
- Every upstream string is trimmed and every null becomes an empty string, so
  no entity field is nullable.
- `available` falls back to `0`, `lat`/`lon` to `0.0`, `fee`/`quota`/`placesLeft`
  to `0` when the upstream value is missing or unparsable.
- A release event is recorded only when the previous snapshot for that sport
  was non-empty, so the first snapshot never produces a flood of events.
- Release events are keyed by the session identity and inserted with
  `OnConflictStrategy.REPLACE`, so a session that gains courts twice keeps the
  latest count instead of a stale one.
- The data package performs no DataStore, notification, or WorkManager work.

## Side Effects

- HTTP GET `{name}/file` and `activity-prog/file` against
  `https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/`.
- OkHttp BASIC-level logging of every call in debug builds only.
- Room writes: `replaceSport` deletes every row for one sport and re-inserts
  the snapshot in one transaction; `replaceAll` clears and re-inserts the
  whole activities table in one transaction.
- Room writes: release events are inserted with `OnConflictStrategy.IGNORE`,
  so the same session is never recorded twice.
- Room deletes: `deleteBySport`, `clearAll`, `deleteStale(cutoff)`.
- Opening the SQLite file `playfinder.db` (destructive migration on schema
  change).

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
- Covers: DTO/Moshi parsing (`app/src/test/java/com/playfinder/app/data/`),
  including null-tolerant upstream columns, and the release-detection rules
  (`core/ReleaseDetectorTest`).
- No automated test yet for the Room schema, the DAOs, or the repositories
  themselves.
