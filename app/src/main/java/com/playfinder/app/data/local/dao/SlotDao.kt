package com.playfinder.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import com.playfinder.app.data.local.entity.SlotEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface SlotDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(slots: List<SlotEntity>)

    @Query("SELECT * FROM slots WHERE sport = :sport ORDER BY date, startTime")
    fun observeBySport(sport: String): Flow<List<SlotEntity>>

    @Query("SELECT * FROM slots WHERE sport = :sport")
    suspend fun getBySport(sport: String): List<SlotEntity>

    @Query("DELETE FROM slots WHERE sport = :sport")
    suspend fun deleteBySport(sport: String)

    @Query("DELETE FROM slots")
    suspend fun clearAll(): Int

    @Query("DELETE FROM slots WHERE fetchedAt < :cutoff")
    suspend fun deleteStale(cutoff: Long): Int

    @Query("SELECT COUNT(*) FROM slots")
    fun observeCount(): Flow<Int>

    /**
     * Replaces the cached snapshot for one sport. The upstream feed is a full
     * snapshot, so inserting without deleting would leak rows for sessions that
     * were booked in the meantime.
     */
    @Transaction
    suspend fun replaceSport(sport: String, slots: List<SlotEntity>) {
        deleteBySport(sport)
        if (slots.isNotEmpty()) insertAll(slots)
    }
}
