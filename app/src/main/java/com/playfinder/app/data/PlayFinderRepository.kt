package com.playfinder.app.data

import com.playfinder.app.data.local.dao.SlotDao
import com.playfinder.app.data.local.entity.SlotEntity
import com.playfinder.app.data.remote.LcsdApi
import com.playfinder.app.data.remote.dto.LcsdRecord
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PlayFinderRepository @Inject constructor(
    private val api: LcsdApi,
    private val slotDao: SlotDao
) {
    fun observeSlots(sport: String): Flow<List<SlotEntity>> = slotDao.observeBySport(sport)

    suspend fun refreshSport(sport: String) {
        val res = api.getDataset(sport)
        if (res.isSuccessful) {
            val body = res.body().orEmpty()
            slotDao.insertAll(body.map { it.toEntity(sport) })
            slotDao.deleteStale(System.currentTimeMillis() - 7L * 24 * 3600 * 1000)
        }
    }

    private fun LcsdRecord.toEntity(sport: String) = SlotEntity(
        sport = sport,
        venue = venueNameTc,
        facility = facilityNameTc,
        date = date,
        startTime = startTime,
        endTime = endTime,
        available = available.toIntOrNull() ?: 0
    )
}