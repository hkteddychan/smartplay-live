package com.playfinder.app.alerts

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.playfinder.app.data.remote.LcsdApi
import com.playfinder.app.data.remote.dto.LcsdRecord
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.flow.first

/**
 * Polls the LCSD open-data snapshot every 15 minutes while a push grant is
 * active. Only sessions that are new since the last poll (and that match the
 * user's watched sports/districts/venues) trigger a notification, so the same
 * slot is never announced twice.
 */
@HiltWorker
class SlotPollWorker @AssistedInject constructor(
    @Assisted ctx: Context,
    @Assisted params: WorkerParameters,
    private val api: LcsdApi
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val wl = WatchlistStore.observe(applicationContext).first()

        // Grant expired: stop polling instead of running forever.
        if (!wl.pushActive()) {
            WorkManager.getInstance(applicationContext).cancelUniqueWork(WatchlistStore.WORK_NAME)
            return Result.success()
        }

        val sports = wl.sports.ifEmpty { setOf("badminton") }
        val seen = wl.seenSlots
        val newKeys = mutableSetOf<String>()

        for (sport in sports) {
            runCatching {
                val res = api.getDataset(sport)
                if (!res.isSuccessful) return@runCatching
                val rows = res.body().orEmpty()

                val fresh = rows
                    .filter { (it.available?.toIntOrNull() ?: 0) > 0 }
                    .filter { matches(wl, it) }
                    .filter { keyOf(sport, it) !in seen }

                if (fresh.isNotEmpty()) {
                    fresh.forEach { newKeys += keyOf(sport, it) }
                    val sample = fresh.first()
                    AlertNotifier.notifyRelease(
                        applicationContext,
                        sport.hashCode(),
                        "放場通知 · ${sportLabel(sport)}",
                        "${fresh.size} 個新時段有餘額，例如 ${sample.venueNameTc} ${sample.date} ${sample.startTime}"
                    )
                }
            }
        }

        WatchlistStore.setSeenSlots(applicationContext, newKeys)
        return Result.success()
    }

    private fun matches(wl: Watchlist, r: LcsdRecord): Boolean {
        val district = r.districtNameTc.orEmpty()
        val venue = r.venueNameTc.orEmpty()
        val districtOk = wl.districts.isEmpty() || district in wl.districts
        val venueOk = wl.venues.isEmpty() || venue in wl.venues
        return districtOk && venueOk
    }

    private fun keyOf(sport: String, r: LcsdRecord): String = buildString {
        append(sport).append('|')
        append(r.venueNameTc.orEmpty()).append('|')
        append(r.facilityNameTc.orEmpty()).append('|')
        append(r.locationNameTc.orEmpty()).append('|')
        append(r.date.orEmpty()).append('|')
        append(r.startTime.orEmpty())
    }

    private fun sportLabel(sport: String) = when (sport) {
        "badminton" -> "羽毛球"
        "basketball" -> "籃球"
        "volleyball" -> "排球"
        "tennis" -> "網球"
        "turf-soccer-pitch" -> "足球場"
        else -> sport
    }
}
