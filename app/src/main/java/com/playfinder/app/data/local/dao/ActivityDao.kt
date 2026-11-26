package com.playfinder.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import com.playfinder.app.data.local.entity.ActivityEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ActivityDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(activities: List<ActivityEntity>)

    /**
     * Activities that are running or start inside the window. A course with
     * `PGM_START_DATE` in the past and `PGM_END_DATE` in the future is still
     * running, so it must not be filtered out by the start date.
     */
    @Query("SELECT * FROM activities WHERE (:district = '' OR district = :district) AND (:type = '' OR type = :type) AND startDate <= :to AND (endDate = '' OR endDate >= :from) ORDER BY startDate, startTime")
    fun observe(district: String, type: String, from: String, to: String): Flow<List<ActivityEntity>>

    @Query("SELECT * FROM activities ORDER BY startDate, startTime")
    fun observeAll(): Flow<List<ActivityEntity>>

    @Query("DELETE FROM activities WHERE fetchedAt < :cutoff")
    suspend fun deleteStale(cutoff: Long): Int

    @Query("DELETE FROM activities")
    suspend fun clearAll(): Int

    @Query("SELECT COUNT(*) FROM activities")
    fun observeCount(): Flow<Int>

    @Transaction
    suspend fun replaceAll(activities: List<ActivityEntity>) {
        clearAll()
        if (activities.isNotEmpty()) insertAll(activities)
    }
}
