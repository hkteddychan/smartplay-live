# Room Entities

## Overview

The three cached tables. Each entity mirrors one upstream record or one
derived event, with every value normalised to a non-null Kotlin type so the UI
never has to null-check.

## Interface

### `SlotEntity` ([SlotEntity.kt](./SlotEntity.kt))
Table `slots`. Fields: `id` (auto-generated `Long` primary key), `sport`,
`venue`, `district`, `facility`, `location`, `date`, `startTime`, `endTime`,
`available: Int`, `lat: Double`, `lon: Double`, `fetchedAt: Long`.

Indices: `sport`, `date`, `district`, plus a unique composite index on
`(sport, venue, facility, location, date, startTime)`.

### `ActivityEntity` ([ActivityEntity.kt](./ActivityEntity.kt))
Table `activities`. Fields: `id` (String primary key from the upstream
`ACTIVITY_NO`), `name`, `type`, `district`, `startDate`, `endDate`, `day`,
`startTime`, `endTime`, `venue`, `targetGroup`, `fee: Double`, `quota: Int`,
`placesLeft: Int`, `enrolMethod`, `enrolStartDate`, `enrolEndDate`, `url`,
`fetchedAt: Long`.

Indices: `district`, `type`, `startDate`.

### `ReleaseEventEntity` ([ReleaseEventEntity.kt](./ReleaseEventEntity.kt))
Table `release_events`. Fields: `id` (String primary key, the session
identity), `sport`, `venue`, `district`, `date`, `startTime`, `endTime`,
`available: Int`, `detectedAt: Long`. Index: `detectedAt`.

## Invariants

- One row per bookable session per sport, enforced by the unique composite
  index; a refresh can never accumulate duplicates.
- `SlotEntity.id` is a surrogate key. The natural identity of a session is
  the composite index, so `id` may change across refreshes.
- `ActivityEntity.id` is the upstream activity number, so upserts are keyed by
  the activity, not by rowid.
- `ReleaseEventEntity.id` is the session identity, so a session that gains
  courts twice is still one event.
- `fetchedAt` defaults to `System.currentTimeMillis()` at construction and is
  the basis of every staleness check.

## Side Effects

- None. Entities are plain data holders.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
