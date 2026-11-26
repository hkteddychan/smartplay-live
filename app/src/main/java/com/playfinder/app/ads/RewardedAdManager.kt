package com.playfinder.app.ads

import android.app.Activity
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.FullScreenContentCallback
import com.google.android.gms.ads.LoadAdError
import com.google.android.gms.ads.rewarded.RewardedAd
import com.google.android.gms.ads.rewarded.RewardedAdLoadCallback
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

object RewardedAdManager {
    // Google test rewarded unit id — replace with the real one before release.
    private const val UNIT_ID = "ca-app-pub-3940256099942544/5224354917"

    /**
     * Shows a rewarded ad and returns true only when the user earned the reward
     * (i.e. watched to completion). Dismissal without earning returns false.
     */
    suspend fun showAndReward(activity: Activity): Boolean = suspendCancellableCoroutine { cont ->
        var rewarded = false
        var finished = false

        fun finish(value: Boolean) {
            if (!finished) {
                finished = true
                if (cont.isActive) cont.resume(value)
            }
        }

        RewardedAd.load(
            activity,
            UNIT_ID,
            AdRequest.Builder().build(),
            object : RewardedAdLoadCallback() {
                override fun onAdLoaded(ad: RewardedAd) {
                    ad.fullScreenContentCallback = object : FullScreenContentCallback() {
                        override fun onAdDismissedFullScreenContent() {
                            finish(rewarded)
                        }
                    }
                    ad.show(activity) { _ -> rewarded = true }
                }

                override fun onAdFailedToLoad(e: LoadAdError) {
                    finish(false)
                }
            }
        )
    }
}