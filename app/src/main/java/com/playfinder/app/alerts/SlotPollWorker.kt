package com.playfinder.app.alerts

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.playfinder.app.core.FilterEngine
import com.playfinder.app.data.PlayFinderRepository
import com.playfinder.app.data.local.entity.ReleaseEventEntity
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.flow.first
import java.io.IOException
import java.time.LocalDate
import java.time.LocalTime

/**
 * Refreshes the LCSD open-data snapshot every 15 minutes while a push grant is
 * active, and posts a notification for every session whose availability went
 * up since the previous snapshot.
 *
 * The release detection lives in the repository (it compares the snapshot
 * before and after the fetch), so a session is announced exactly once even
 * when the user-facing screen refreshed the cache first.
 */
@HiltWorker
class SlotPollWorker @AssistedInject constructor(
    @Assisted ctx: Context,
    @Assisted params: WorkerParameters,
    private val repo: PlayFinderRepository
) : CoroutineWorker(ctx, params) {

    override suspend fun doWork(): Result {
        val wl = WatchlistStore.observe(applicationContext).first()

        // Grant expired: stop polling instead of running forever.
        if (!wl.pushActive()) {
            WorkManager.getInstance(applicationContext).cancelUniqueWork(WatchlistStore.WORK_NAME)
            return Result.success()
        }

        val sports = wl.sports.ifEmpty { setOf("badminton") }
        var networkFailure = false

        for (sport in sports) {
            try {
                // The poll also refreshes the offline cache, so the app shows
                // fresh rows even when nobody opens a screen.
                repo.fetchAndCache(sport)
            } catch (e: IOException) {
                networkFailure = true
            } catch (e: Exception) {
                // A malformed response is not worth retrying.
                android.util.Log.w("SlotPollWorker", "poll failed for $sport", e)
            }
        }

        val events = repo.pendingReleaseEvents(MAX_EVENTS)
            .filter { matches(wl, it) }

        // During quiet hours the events stay pending, so the alert is still
        // delivered once the quiet window ends.
        if (!events.isEmpty() && !(wl.quietHoursEnabled && inQuietWindow(wl))) {
            events.forEach { e ->
                AlertNotifier.notifyRelease(
                    applicationContext,
                    // Stable per-session id: two different sessions must not
                    // overwrite each other's notification.
                    e.id.hashCode(),
                    "放場通知 · ${sportLabel(e.sport)}",
                    "${e.venue} ${e.date} ${e.startTime}-${e.endTime} · 餘 ${e.available} 位"
                )
            }
            repo.clearReleaseEvents(events.map { it.id })
        }

        return if (networkFailure) Result.retry() else Result.success()
    }

    private fun matches(wl: Watchlist, e: ReleaseEventEntity): Boolean {
        if (e.sport !in wl.sports && wl.sports.isNotEmpty()) return false
        if (wl.districts.isNotEmpty() && e.district !in wl.districts) return false
        if (wl.venues.isNotEmpty() && e.venue !in wl.venues) return false

        if (wl.weekdays.isNotEmpty()) {
            val date = runCatching { LocalDate.parse(e.date) }.getOrNull() ?: return false
            if (date.dayOfWeek.value !in wl.weekdays) return false
        }

        val minute = FilterEngine.minuteOf(e.startTime)
        if (minute < 0) return false
        return minute >= wl.fromMinute && minute < wl.toMinute
    }

    private fun inQuietWindow(wl: Watchlist): Boolean {
        val now = LocalTime.now()
        val current = now.hour * 60 + now.minute
        val start = wl.quietStartMinute
        val end = wl.quietEndMinute
        return if (start <= end) {
            current in start until end
        } else {
            // Window wraps past midnight.
            current >= start || current < end
        }
    }

    private fun sportLabel(sport: String) = when (sport) {
        "badminton" -> "羽毛球"
        "basketball" -> "籃球"
        "volleyball" -> "排球"
        "tennis" -> "網球"
        "turf-soccer-pitch" -> "足球場"
        else -> sport
    }

    private companion object {
        const val MAX_EVENTS = 20
    }
}
