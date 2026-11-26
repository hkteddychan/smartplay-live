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

    /**
     * Fetches a full snapshot for [sport] and swaps it into the cache.
     * Throws on HTTP/parse failures so the UI can distinguish "offline" from
     * "no sessions available" instead of silently showing an empty list.
     */
    suspend fun refreshSport(sport: String) {
        val res = api.getDataset(sport)
        if (!res.isSuccessful) error("HTTP ${res.code()} for $sport")
        val body = res.body() ?: error("Empty response for $sport")
        val rows = body
            .filter { !it.date.isNullOrBlank() && !it.startTime.isNullOrBlank() }
            .map { it.toEntity(sport) }
        slotDao.replaceSport(sport, rows)
    }

    private fun LcsdRecord.toEntity(sport: String) = SlotEntity(
        sport = sport,
        venue = venueNameTc?.trim().orEmpty(),
        district = districtNameTc?.trim().orEmpty(),
        facility = facilityNameTc?.trim().orEmpty(),
        location = locationNameTc?.trim().orEmpty(),
        date = date?.trim().orEmpty(),
        startTime = startTime?.trim().orEmpty(),
        endTime = endTime?.trim().orEmpty(),
        available = available?.toIntOrNull() ?: 0,
        lat = lat?.toDoubleOrNull() ?: 0.0,
        lon = lon?.toDoubleOrNull() ?: 0.0
    )
}
