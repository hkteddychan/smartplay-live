package com.playfinder.app

import android.app.Application
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import androidx.work.WorkManager
import com.google.android.gms.ads.MobileAds
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

@HiltAndroidApp
class PlayFinderApp : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder().setWorkerFactory(workerFactory).build()

    override fun onCreate() {
        super.onCreate()
        // WorkManager is initialised here, not by AndroidX Startup: the
        // default initializer runs before Hilt injects the worker factory, so
        // the HiltWorkerFactory would never be used and SlotPollWorker could
        // not be constructed. The default initializer is removed in the
        // manifest.
        WorkManager.initialize(this, workManagerConfiguration)
        // Without this the AdMob SDK never loads an ad and the rewarded
        // request always fails.
        MobileAds.initialize(this)
    }
}
