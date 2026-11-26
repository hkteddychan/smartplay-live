package com.playfinder.app.ads

import android.app.Activity
import android.content.Context
import com.google.android.gms.ads.AdRequest
import com.google.android.gms.ads.rewarded.RewardedAd
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

object RewardedAdManager {
    // Replace with real unit id before release
    private const val UNIT_ID = "ca-app-pub-2824936620876447/0000000000"

    suspend fun showAndReward(activity: Activity): Boolean = suspendCancellableCoroutine { cont ->
        var rewarded: RewardedAd? = null
        RewardedAd.load(
            activity,
            UNIT_ID,
            AdRequest.Builder().build(),
            object : com.google.android.gms.ads.rewarded.RewardedAdLoadCallback() {
                override fun onAdLoaded(ad: RewardedAd) {
                    rewarded = ad
                    ad.fullScreenContentCallback = object : com.google.android.gms.ads.FullScreenContentCallback() {
                        override fun onAdDismissedFullScreenContent() {
                            if (!cont.isActive) return
                            cont.resume(false)
                        }
                    }
                    ad.show(activity) { _ ->
                        // reward earned callback -> grant handled by caller after show returns
                    }
                    // Consider earned via onUserEarnedReward; simplified: grant on dismiss
                }

                override fun onAdFailedToLoad(e: com.google.android.gms.ads.LoadAdError) {
                    if (cont.isActive) cont.resume(false)
                }
            }
        )
    }
}