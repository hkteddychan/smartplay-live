# Dependency Injection

## Overview

Hilt modules. They build the two singletons the app needs (the Room database
and the Retrofit stack) and expose the DAOs.

## Interface

### `DatabaseModule` ([DatabaseModule.kt](./DatabaseModule.kt))
- `@Provides @Singleton fun provideDatabase(ctx: Context): PlayFinderDatabase`
- `@Provides fun provideSlotDao(db: PlayFinderDatabase): SlotDao`
- `@Provides fun provideActivityDao(db: PlayFinderDatabase): ActivityDao`
- `@Provides fun provideReleaseEventDao(db: PlayFinderDatabase): ReleaseEventDao`

### `NetworkModule` ([NetworkModule.kt](./NetworkModule.kt))
- `@Provides @Singleton fun provideMoshi(): Moshi`
- `@Provides @Singleton fun provideOkHttp(): OkHttpClient`
- `@Provides @Singleton fun provideRetrofit(client, moshi): Retrofit`
- `@Provides @Singleton fun provideLcsdApi(retrofit): LcsdApi`

## Invariants

- The database uses `fallbackToDestructiveMigration()`, so a schema version
  change drops cached rows instead of migrating them. The schema is at
  version 4.
- The Retrofit base URL is
  `https://data.smartplay.lcsd.gov.hk/rest/cms/api/v1/publ/contents/open-data/`.
- The database, Moshi, OkHttp client, Retrofit and the API are `@Singleton`.
  The three DAO providers are unscoped, so every injection point gets its own
  DAO instance — harmless, because Room DAOs are thin wrappers over the
  singleton database.
- The OkHttp logging interceptor is installed in every build but only logs at
  BASIC level when `BuildConfig.DEBUG` is set; release builds use
  `Level.NONE`.

## Side Effects

- Creates or opens the SQLite file `playfinder.db`.
- Installs an OkHttp logging interceptor at BASIC level, which logs every
  request.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
