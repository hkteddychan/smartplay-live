package com.playfinder.app.alerts

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.playfinder.app.data.remote.LcsdApi
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.flow.first

@HiltWorker
class NtfyPollWorker @AssistedInject constructor(
    @Assisted ctx: Context,
    @Assisted params: WorkerParameters,
    private val api: LcsdApi
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val wl = WatchlistStore.observe(applicationContext).first()
        if (!wl.pushEnabled || wl.pushUntilEpoch < System.currentTimeMillis()) return Result.success()

        val sports = wl.sports.ifEmpty { setOf("badminton") }
        for (sport in sports) {
            runCatching {
                val body = api.getDataset(sport).body().orEmpty()
                val released = body.filter { (it.available.toIntOrNull() ?: 0) > 0 }
                if (released.isNotEmpty()) {
                    AlertNotifier.notifyRelease(
                        applicationContext,
                        sport.hashCode(),
                        "放場通知 · $sport",
                        "${released.size} 個時段有餘額"
                    )
                }
            }
        }
        return Result.success()
    }
}