# Theme

## Overview

The Material 3 colour schemes and the theme entry point. One file, one
responsibility.

## Interface

- `PlayFinderTheme(darkTheme: Boolean = isSystemInDarkTheme(), dynamicColor: Boolean = true, content: @Composable () -> Unit)`

## Invariants

- Dynamic colour is used only on API 31+ when `dynamicColor` is true; below
  that the static light and dark schemes apply.
- The static schemes are a teal primary (`#00696E` light, `#4FD8D8` dark) with
  an amber tertiary used by the prime-time badge, plus matching container and
  `on*` pairs so contrast holds in both modes.
- `MaterialTheme(colorScheme = scheme)` is always set, so no screen falls back
  to the default light scheme.
- The XML theme has a `values-night` variant so the window background matches
  the system dark mode before Compose draws the first frame.

## Side Effects

- None beyond reading the system dark-mode and wallpaper-colour settings.

## Verification

- Run: `.\gradlew.bat assembleDebug` and toggle the system dark mode on a
  device.
