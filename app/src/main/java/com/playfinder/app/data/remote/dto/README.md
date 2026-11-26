# Feed DTOs

## Overview

Moshi models for the two LCSD feeds. The JSON keys are the upstream column
names, so the mapping is one-to-one and easy to verify against a live
response.

## Interface

### `LcsdRecord` ([LcsdRecord.kt](./LcsdRecord.kt))
One bookable session. All fields are nullable `String?`:
`Venue_Name_TC`, `Venue_Name_EN`, `District_Name_TC`, `Facility_Type_Name_TC`,
`Facility_Type_Name_EN`, `Facility_Location_Name_TC`, `Available_Date`,
`Session_Start_Time`, `Session_End_Time`, `Available_Courts`,
`Venue_Latitude`, `Venue_Longitude`.

### `LcsdActivity` ([LcsdActivity.kt](./LcsdActivity.kt))
One programme activity. All fields are nullable:
`ACTIVITY_NO`, `TC_PGM_NAME`, `EN_PGM_NAME`, `TC_ACT_TYPE_NAME`,
`EN_ACT_TYPE_NAME`, `TC_DISTRICT`, `EN_DISTRICT`, `PGM_START_DATE`,
`PGM_END_DATE`, `TC_DAY`, `PGM_START_TIME`, `PGM_END_TIME`, `TC_VENUE`,
`TC_TARGET_GRP`, `FEE: Double?`, `QUOTA: Int?`, `PLACES_LEFT: Int?`,
`ENROL_START_DATE`, `ENROL_END_DATE`, `ENROL_METHOD`, `TC_URL`.

## Invariants

- Every field is nullable on purpose: the feed occasionally emits JSON `null`,
  and a non-null Kotlin type makes Moshi abort the entire response
  (see the KDoc on both classes).
- `generateAdapter = true` — the adapters are code-generated at build time by
  the Moshi KSP processor, so a missing `@Json` mapping is a compile error, not
  a runtime surprise.
- Numbers stay nullable in the DTO and are defaulted to `0` only when the
  entity is built.

## Side Effects

- None. Pure data classes.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
- `MoshiAdapterTest` parses a realistic slot payload and a realistic activity
  payload, including a payload with null optional columns.
