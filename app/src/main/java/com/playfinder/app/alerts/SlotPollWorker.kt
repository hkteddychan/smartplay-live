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

        // Housekeeping: an event nobody matched is dropped after a day so the
        // table cannot grow without bound.
        repo.pruneReleaseEvents(EVENT_TTL_MS)

        val events = repo.pendingReleaseEvents(MAX_CANDIDATES)
            .filter { matches(wl, it) }
            .take(MAX_NOTIFICATIONS)

        // During quiet hours the events stay pending, so the alert is still
        // delivered once the quiet window closes.
        if (events.isNotEmpty() && !(wl.quietHoursEnabled && inQuietWindow(wl))) {
            val delivered = mutableListOf<String>()
            val dropped = mutableListOf<String>()
            for (e in events) {
                val current = repo.currentAvailability(e)
                when {
                    current == null || current <= 0 ->
                        // The session was booked again before the notification
                        // went out: drop it instead of announcing a full court.
                        dropped += e.id
                    AlertNotifier.notifyRelease(
                        applicationContext,
                        // Stable per-session id: two different sessions must not
                        // overwrite each other's notification.
                        e.id.hashCode(),
                        "放場通知 · ${sportLabel(e.sport)}",
                        "${e.venue} ${e.date} ${e.startTime}-${e.endTime} · 餘 $current 位"
                    ) -> delivered += e.id
                    else -> {
                        // The notification could not be posted (no permission):
                        // keep the event so it can be delivered later.
                    }
                }
            }
            repo.clearReleaseEvents(delivered + dropped)
        }

        // A permanently offline device must not turn into an endless retry
        // loop; WorkManager's backoff would replace the 15-minute cadence.
        return if (networkFailure && runAttemptCount < MAX_ATTEMPTS) {
            Result.retry()
        } else {
            Result.success()
        }
    }

    private fun matches(wl: Watchlist, e: ReleaseEventEntity): Boolean {
        if (wl.sports.isNotEmpty() && e.sport !in wl.sports) return false
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
        /** How many pending events are inspected per poll before filtering. */
        const val MAX_CANDIDATES = 200

        /** How many notifications one poll may post. */
        const val MAX_NOTIFICATIONS = 20

        /** How many times a failing poll is retried before it is given up on. */
        const val MAX_ATTEMPTS = 3

        /** Unmatched events are dropped after this long. */
        const val EVENT_TTL_MS = 24L * 3600 * 1000
    }
}
