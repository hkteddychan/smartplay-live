# LCSD API Client

## Overview

The Retrofit service that talks to the LCSD open-data feed. Two endpoints
cover everything the app needs: a per-sport availability snapshot and the
programme activity feed.

## Interface

### `LcsdApi` ([LcsdApi.kt](./LcsdApi.kt))
- `@GET("{name}/file") suspend fun getDataset(@Path("name") name: String): Response<List<LcsdRecord>>`
- `@GET("activity-prog/file") suspend fun getActivities(): Response<List<LcsdActivity>>`

Base URL and OkHttp/Moshi wiring: [../../di/NetworkModule.kt](../../di/NetworkModule.kt)
(`https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/`).

Subdirectories:
- [dto/](./dto/README.md) — Moshi models for the two feeds

## Invariants

- Responses are returned as `Response<T>`, not bare bodies, so the caller can
  see the HTTP status and decide between "error" and "empty".
- The Retrofit instance is provided by Hilt with Moshi and a logging
  interceptor that is silent in release builds.

## Side Effects

- One HTTP GET per call: `{name}/file` or `activity-prog/file`.
- Every request is logged at BASIC level in debug builds; the interceptor is
  set to `Level.NONE` in release builds.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
