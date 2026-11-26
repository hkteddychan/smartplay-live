# Ads

## Overview

The value-exchange monetisation hook: one rewarded ad buys one week of push
alerts. This package contains only the ad call; the reward gate (the
three-minute in-app countdown) and the DataStore write live in the UI and in
[../alerts/](../alerts/README.md).

## Interface

### `RewardedAdManager` ([RewardedAdManager.kt](./RewardedAdManager.kt))
- `suspend fun showAndReward(activity: Activity): Boolean`

Returns `true` only when the user earned the reward (watched to completion).

## Invariants

- The function always completes. Load failure, show failure and dismissal
  without a reward all resolve `false`; the continuation is resumed at most
  once.
- Coroutine cancellation is treated as "not earned".
- The unit id in the source is Google's **public test** rewarded unit id. It
  must be replaced with the real one before release, otherwise the build
  violates AdMob policy. There is no runtime guard for this.

## Side Effects

- Loads and shows a Google AdMob rewarded ad on the supplied `Activity`.

## Verification

- Run: `.\gradlew.bat testDebugUnitTest`
- No automated coverage: the ad SDK needs a device. Manual check: open
  [../ui/AlertsScreen.kt](../ui/AlertsScreen.kt) and confirm the button never
  stays on "載入廣告中…".
