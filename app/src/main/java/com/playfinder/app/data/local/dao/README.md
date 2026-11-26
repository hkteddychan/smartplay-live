# Room DAOs

## Overview

The three Room query interfaces. They are the only place that speaks SQL, and
they are deliberately narrow: one table each, plus transactional snapshot
replaces that keep the cache from accumulating duplicates.

## Interface

### `SlotDao` ([SlotDao.kt](./SlotDao.kt))
- `suspend insertAll(slots: List<SlotEntity>)` — `@Insert(onConflict = REPLACE)`
- `fun observeBySport(sport: String): Flow<List<SlotEntity>>` — ordered by date, startTime
- `suspend getBySport(sport: String): List<SlotEntity>` — the previous snapshot, used for release detection
- `suspend getByKey(sport, venue, facility, location, date, startTime): SlotEntity?` — the current state of one session
- `suspend deleteBySport(sport: String)`
- `suspend clearAll(): Int`
- `suspend deleteStale(cutoff: Long): Int`
- `fun observeCount(): Flow<Int>`
- `@Transaction suspend replaceSport(sport: String, slots: List<SlotEntity>)`

### `ActivityDao` ([ActivityDao.kt](./ActivityDao.kt))
- `suspend insertAll(activities: List<ActivityEntity>)` — `@Insert(onConflict = REPLACE)`
- `fun observe(district: String, type: String, from: String, to: String): Flow<List<ActivityEntity>>`
- `fun observeAll(): Flow<List<ActivityEntity>>`
- `suspend deleteStale(cutoff: Long): Int`
- `suspend clearAll(): Int`
- `fun observeCount(): Flow<Int>`
- `@Transaction suspend replaceAll(activities: List<ActivityEntity>)`

### `ReleaseEventDao` ([ReleaseEventDao.kt](./ReleaseEventDao.kt))
- `suspend insertAll(events: List<ReleaseEventEntity>)` — `OnConflictStrategy.REPLACE`
- `suspend pending(limit: Int): List<ReleaseEventEntity>` — newest first
- `suspend deleteByIds(ids: List<String>)`
- `suspend deleteOlderThan(cutoff: Long): Int`
- `fun observeCount(): Flow<Int>`

## Invariants

- `replaceSport` deletes all rows for the sport and re-inserts the snapshot
  atomically; an empty snapshot clears the sport rather than being a no-op.
- `replaceAll` clears the whole activities table and re-inserts atomically.
- `OnConflictStrategy.REPLACE` means a row with the same primary key or the
  same unique slot-identity index is overwritten, never duplicated.
- Slot identity for conflict resolution is the unique composite index
  `(sport, venue, facility, location, date, startTime)`, not the
  auto-generated primary key
  ([../entity/SlotEntity.kt](../entity/SlotEntity.kt)).
- An empty `district` or `type` argument means "no filter" in
  `ActivityDao.observe`; `startDate BETWEEN from AND to` is always applied.
- Staleness is measured with the `fetchedAt` epoch-millis column.
- Release events are keyed by the session identity, so the same session is
  recorded once and delivered once.

## Side Effects

- Inserts, updates and deletes rows in the `slots`, `activities` and
  `release_events` tables.
- `replaceSport` and `replaceAll` run inside a Room transaction.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
- No automated test yet for these DAOs.
