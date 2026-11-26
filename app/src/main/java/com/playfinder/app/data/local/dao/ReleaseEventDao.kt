package com.playfinder.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.playfinder.app.data.local.entity.ReleaseEventEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ReleaseEventDao {
    /**
     * REPLACE, not IGNORE: a session can gain courts twice. The newer row
     * replaces the older one so the notification always carries the latest
     * count instead of a stale one.
     */
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(events: List<ReleaseEventEntity>)

    /** Newest first, so a fresh release is never starved by older rows. */
    @Query("SELECT * FROM release_events ORDER BY detectedAt DESC LIMIT :limit")
    suspend fun pending(limit: Int): List<ReleaseEventEntity>

    @Query("DELETE FROM release_events WHERE id IN (:ids)")
    suspend fun deleteByIds(ids: List<String>)

    @Query("DELETE FROM release_events WHERE detectedAt < :cutoff")
    suspend fun deleteOlderThan(cutoff: Long): Int

    @Query("SELECT COUNT(*) FROM release_events")
    fun observeCount(): Flow<Int>
}
