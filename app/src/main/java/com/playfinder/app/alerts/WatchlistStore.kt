package com.playfinder.app.alerts

import android.content.Context
import androidx.datastore.preferences.core.booleanPreferencesKey
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.intPreferencesKey
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
    val pushEnabled: Boolean = false,
    val pushUntilEpoch: Long = 0L
)

object WatchlistStore {
    private val SPORTS = stringSetPreferencesKey("sports")
    private val DISTRICTS = stringSetPreferencesKey("districts")
    private val PUSH_ENABLED = booleanPreferencesKey("push_enabled")
    private val PUSH_UNTIL = intPreferencesKey("push_until")

    fun observe(ctx: Context): Flow<Watchlist> = ctx.dataStore.data.map { p ->
        Watchlist(
            sports = p[SPORTS] ?: emptySet(),
            districts = p[DISTRICTS] ?: emptySet(),
            pushEnabled = p[PUSH_ENABLED] ?: false,
            pushUntilEpoch = (p[PUSH_UNTIL] ?: 0).toLong()
        )
    }

    suspend fun setSports(ctx: Context, sports: Set<String>) {
        ctx.dataStore.edit { it[SPORTS] = sports }
    }

    suspend fun grantPush(ctx: Context, weeks: Int = 1) {
        ctx.dataStore.edit {
            it[PUSH_ENABLED] = true
            it[PUSH_UNTIL] = (System.currentTimeMillis() + weeks * 7L * 24 * 3600 * 1000).toInt()
        }
        val req = PeriodicWorkRequestBuilder<NtfyPollWorker>(15, TimeUnit.MINUTES).build()
        WorkManager.getInstance(ctx).enqueueUniquePeriodicWork(
            "ntfy-poll", ExistingPeriodicWorkPolicy.KEEP, req
        )
    }
}