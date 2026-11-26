package com.playfinder.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.playfinder.app.data.local.entity.ReleaseEventEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ReleaseEventDao {
    @Insert(onConflict = OnConflictStrategy.IGNORE)
    suspend fun insertAll(events: List<ReleaseEventEntity>)

    @Query("SELECT * FROM release_events ORDER BY detectedAt LIMIT :limit")
    suspend fun pending(limit: Int): List<ReleaseEventEntity>

    @Query("DELETE FROM release_events WHERE id IN (:ids)")
    suspend fun deleteByIds(ids: List<String>)

    @Query("DELETE FROM release_events WHERE detectedAt < :cutoff")
    suspend fun deleteOlderThan(cutoff: Long): Int

    @Query("SELECT COUNT(*) FROM release_events")
    fun observeCount(): Flow<Int>
}
