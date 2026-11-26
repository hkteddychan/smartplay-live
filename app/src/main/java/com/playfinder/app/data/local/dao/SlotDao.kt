package com.playfinder.app.data.local.dao

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import com.playfinder.app.data.local.entity.SlotEntity
import kotlinx.coroutines.flow.Flow

@Dao
interface SlotDao {
    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertAll(slots: List<SlotEntity>)

    @Query("SELECT * FROM slots WHERE sport = :sport ORDER BY date, startTime")
    fun observeBySport(sport: String): Flow<List<SlotEntity>>

    @Query("SELECT * FROM slots WHERE sport = :sport AND date BETWEEN :from AND :to ORDER BY date, startTime")
    fun observeBySportAndDate(sport: String, from: String, to: String): Flow<List<SlotEntity>>

    @Query("DELETE FROM slots WHERE fetchedAt < :cutoff")
    suspend fun deleteStale(cutoff: Long): Int
}