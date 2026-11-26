package com.playfinder.app.alerts

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.util.concurrent.TimeUnit

private val Context.dataStore by preferencesDataStore(name = "playfinder_prefs")

/**
 * The user's push configuration. Everything is device-local: the app has no
 * account and nothing here is sent anywhere.
 *
 * [weekdays] uses ISO day numbers (1 = Monday … 7 = Sunday). An empty set
 * means "every day".
 */
data class Watchlist(
    val sports: Set<String> = emptySet(),
    val districts: Set<String> = emptySet(),
    val venues: Set<String> = emptySet(),
    val weekdays: Set<Int> = emptySet(),
    val fromMinute: Int = 0,
    val toMinute: Int = 24 * 60,
    val quietStartMinute: Int = -1,
    val quietEndMinute: Int = -1,
    val pushEnabled: Boolean = false,
    val pushUntilEpoch: Long = 0L
) {
    fun pushActive(now: Long = System.currentTimeMillis()): Boolean =
        pushEnabled && pushUntilEpoch > now

    val quietHoursEnabled: Boolean get() = quietStartMinute >= 0 && quietEndMinute >= 0
}

object WatchlistStore {
    const val WORK_NAME = "slot-poll"

    /** The spec caps a watchlist at five venues. */
    const val MAX_VENUES = 5

    private const val WEEK_MS = 7L * 24 * 3600 * 1000

    private val SPORTS = stringSetPreferencesKey("sports")
    private val DISTRICTS = stringSetPreferencesKey("districts")
    private val VENUES = stringSetPreferencesKey("venues")
    private val WEEKDAYS = stringSetPreferencesKey("weekdays")
    private val FROM_MINUTE = intPreferencesKey("from_minute")
    private val TO_MINUTE = intPreferencesKey("to_minute")
    private val QUIET_START = intPreferencesKey("quiet_start")
    private val QUIET_END = intPreferencesKey("quiet_end")
    private val PUSH_ENABLED = booleanPreferencesKey("push_enabled")

    // Long, not Int: epoch millis overflowed Int in v1.0, which made every
    // expiry check fail and silently disabled push forever.
    private val PUSH_UNTIL = longPreferencesKey("push_until_epoch")

    fun observe(ctx: Context): Flow<Watchlist> = ctx.dataStore.data.map { p ->
        Watchlist(
            sports = p[SPORTS] ?: emptySet(),
            districts = p[DISTRICTS] ?: emptySet(),
            venues = p[VENUES] ?: emptySet(),
            weekdays = p[WEEKDAYS]
                ?.mapNotNull { it.toIntOrNull() }
                ?.filter { it in 1..7 }
                ?.toSet()
                .orEmpty(),
            fromMinute = p[FROM_MINUTE] ?: 0,
            toMinute = p[TO_MINUTE] ?: (24 * 60),
            quietStartMinute = p[QUIET_START] ?: -1,
            quietEndMinute = p[QUIET_END] ?: -1,
            pushEnabled = p[PUSH_ENABLED] ?: false,
            pushUntilEpoch = p[PUSH_UNTIL] ?: 0L
        )
    }

    suspend fun setSports(ctx: Context, sports: Set<String>) {
        ctx.dataStore.edit { it[SPORTS] = sports }
    }

    suspend fun toggleSport(ctx: Context, sport: String) {
        ctx.dataStore.edit {
            val current = it[SPORTS] ?: emptySet()
            it[SPORTS] = if (sport in current) current - sport else current + sport
        }
    }

    suspend fun addSport(ctx: Context, sport: String) {
        ctx.dataStore.edit { it[SPORTS] = (it[SPORTS] ?: emptySet()) + sport }
    }

    suspend fun setDistricts(ctx: Context, districts: Set<String>) {
        ctx.dataStore.edit { it[DISTRICTS] = districts }
    }

    suspend fun addDistrict(ctx: Context, district: String) {
        ctx.dataStore.edit { it[DISTRICTS] = (it[DISTRICTS] ?: emptySet()) + district }
    }

    suspend fun toggleDistrict(ctx: Context, district: String) {
        ctx.dataStore.edit {
            val current = it[DISTRICTS] ?: emptySet()
            it[DISTRICTS] = if (district in current) current - district else current + district
        }
    }

    /** Adds a venue, respecting [MAX_VENUES]. Returns false when the cap is hit. */
    suspend fun addVenue(ctx: Context, venue: String): Boolean {
        var accepted = false
        ctx.dataStore.edit {
            val current = it[VENUES] ?: emptySet()
            if (venue in current || current.size < MAX_VENUES) {
                it[VENUES] = current + venue
                accepted = true
            }
        }
        return accepted
    }

    suspend fun removeVenue(ctx: Context, venue: String) {
        ctx.dataStore.edit {
            it[VENUES] = (it[VENUES] ?: emptySet()) - venue
        }
    }

    suspend fun setWeekdays(ctx: Context, weekdays: Set<Int>) {
        ctx.dataStore.edit { it[WEEKDAYS] = weekdays.map(Int::toString).toSet() }
    }

    suspend fun toggleWeekday(ctx: Context, weekday: Int) {
        ctx.dataStore.edit {
            val current = (it[WEEKDAYS] ?: emptySet())
                .mapNotNull { d -> d.toIntOrNull() }
                .filter { d -> d in 1..7 }
                .toSet()
            it[WEEKDAYS] = (
                if (weekday in current) current - weekday else current + weekday
                ).map(Int::toString).toSet()
        }
    }

    suspend fun setTimeRange(ctx: Context, fromMinute: Int, toMinute: Int) {
        ctx.dataStore.edit {
            it[FROM_MINUTE] = fromMinute.coerceIn(0, 24 * 60)
            it[TO_MINUTE] = toMinute.coerceIn(0, 24 * 60)
        }
    }

    /** Quiet hours are stored as minutes from midnight; [-1, -1] disables them. */
    suspend fun setQuietHours(ctx: Context, startMinute: Int, endMinute: Int) {
        ctx.dataStore.edit {
            it[QUIET_START] = startMinute
            it[QUIET_END] = endMinute
        }
    }

    suspend fun grantPush(ctx: Context, weeks: Int = 1) {
        ctx.dataStore.edit {
            it[PUSH_ENABLED] = true
            it[PUSH_UNTIL] = System.currentTimeMillis() + weeks * WEEK_MS
        }
        enqueuePoll(ctx)
    }

    suspend fun revokePush(ctx: Context) {
        ctx.dataStore.edit {
            it[PUSH_ENABLED] = false
            it[PUSH_UNTIL] = 0L
        }
        WorkManager.getInstance(ctx).cancelUniqueWork(WORK_NAME)
    }

    fun enqueuePoll(ctx: Context) {
        val req = PeriodicWorkRequestBuilder<SlotPollWorker>(15, TimeUnit.MINUTES).build()
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            req
        )
    }
}
