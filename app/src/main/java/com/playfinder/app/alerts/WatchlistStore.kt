package com.playfinder.app.alerts

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.longPreferencesKey
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.core.stringSetPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import java.util.concurrent.TimeUnit

private val Context.dataStore by preferencesDataStore(name = "playfinder_prefs")

data class Watchlist(
    val sports: Set<String> = emptySet(),
    val districts: Set<String> = emptySet(),
    val venues: Set<String> = emptySet(),
    val pushEnabled: Boolean = false,
    val pushUntilEpoch: Long = 0L,
    val seenSlots: Set<String> = emptySet()
) {
    fun pushActive(now: Long = System.currentTimeMillis()): Boolean =
        pushEnabled && pushUntilEpoch > now
}

object WatchlistStore {
    const val WORK_NAME = "slot-poll"

    private const val WEEK_MS = 7L * 24 * 3600 * 1000
    private const val MAX_SEEN = 800

    private val SPORTS = stringSetPreferencesKey("sports")
    private val DISTRICTS = stringSetPreferencesKey("districts")
    private val VENUES = stringSetPreferencesKey("venues")
    private val PUSH_ENABLED = booleanPreferencesKey("push_enabled")

    // Long, not Int: epoch millis overflowed Int in v1.0, which made every
    // expiry check fail and silently disabled push forever.
    private val PUSH_UNTIL = longPreferencesKey("push_until_epoch")

    private val SEEN_SLOTS = stringPreferencesKey("seen_slots_v2")

    fun observe(ctx: Context): Flow<Watchlist> = ctx.dataStore.data.map { p ->
        Watchlist(
            sports = p[SPORTS] ?: emptySet(),
            districts = p[DISTRICTS] ?: emptySet(),
            venues = p[VENUES] ?: emptySet(),
            pushEnabled = p[PUSH_ENABLED] ?: false,
            pushUntilEpoch = p[PUSH_UNTIL] ?: 0L,
            seenSlots = p[SEEN_SLOTS]
                ?.split('\n')
                ?.filter { it.isNotBlank() }
                ?.toSet()
                .orEmpty()
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

    suspend fun setVenues(ctx: Context, venues: Set<String>) {
        ctx.dataStore.edit { it[VENUES] = venues }
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

    /** Remembers which sessions were already announced so we never re-alert. */
    suspend fun setSeenSlots(ctx: Context, keys: Set<String>) {
        if (keys.isEmpty()) return
        ctx.dataStore.edit { prefs ->
            val existing = prefs[SEEN_SLOTS]
                ?.split('\n')
                ?.filter { it.isNotBlank() }
                .orEmpty()
            // Insertion-ordered FIFO: a Set would drop arbitrary keys when trimmed.
            val merged = (existing + keys).distinct().takeLast(MAX_SEEN)
            prefs[SEEN_SLOTS] = merged.joinToString("\n")
        }
    }
}
