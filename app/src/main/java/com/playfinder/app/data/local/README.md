# Local Cache (Room)

## Overview

The offline cache. Three tables — bookable court sessions, programme
activities, and the release event log — plus the Room database that owns them.
The cache is a snapshot mirror of the upstream feed, not an event log: every
refresh replaces the rows for the affected scope.

## Interface

- `PlayFinderDatabase` — `@Database(entities = [SlotEntity, ActivityEntity, ReleaseEventEntity], version = 4, exportSchema = false)`
  - `abstract fun slotDao(): SlotDao`
  - `abstract fun activityDao(): ActivityDao`
  - `abstract fun releaseEventDao(): ReleaseEventDao`
- Subdirectories:
  - [dao/](./dao/README.md) — query and write interfaces
  - [entity/](./entity/README.md) — table definitions

## Invariants

- The database is at version 4 and the DI builder uses
  `fallbackToDestructiveMigration()`, so a schema change drops cached rows
  instead of migrating them ([../../di/DatabaseModule.kt](../../di/DatabaseModule.kt)).
- `exportSchema = false`, so no schema JSON is checked in.

## Side Effects

- Creates or opens the `playfinder.db` SQLite file on the device.
- Destructive migration drops all rows when the version changes.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
- No automated test yet for the schema or the DAOs.
