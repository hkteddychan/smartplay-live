package com.playfinder.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.playfinder.app.data.local.entity.ActivityEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface ActivityDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(activities: List<ActivityEntity>)

    @Query("SELECT * FROM activities WHERE (:sport = '' OR type = :sport) AND (:district = '' OR district = :district) AND startDate >= :from ORDER BY startDate")
    fun observe(sport: String, district: String, from: String): Flow<List<ActivityEntity>>

    @Query("DELETE FROM activities WHERE fetchedAt < :cutoff")
    suspend fun deleteStale(cutoff: Long)
}