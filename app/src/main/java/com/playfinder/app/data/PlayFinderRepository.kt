package com.playfinder.app.data

import com.playfinder.app.core.ReleaseDetector
import com.playfinder.app.data.local.dao.ReleaseEventDao
import com.playfinder.app.data.local.dao.SlotDao
import com.playfinder.app.data.local.entity.ReleaseEventEntity
import com.playfinder.app.data.local.entity.SlotEntity
import com.playfinder.app.data.remote.LcsdApi
import com.playfinder.app.data.remote.dto.LcsdRecord
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class PlayFinderRepository @Inject constructor(
    private val api: LcsdApi,
    private val slotDao: SlotDao,
    private val releaseEventDao: ReleaseEventDao
) {
    fun observeSlots(sport: String): Flow<List<SlotEntity>> = slotDao.observeBySport(sport)

    /**
     * Fetches a full snapshot for [sport], swaps it into the cache and returns
     * the rows. Throws on HTTP/parse failures so callers can distinguish
     * "offline" from "no sessions available" instead of silently showing an
     * empty list.
     */
    suspend fun fetchAndCache(sport: String): List<SlotEntity> {
        val previous = slotDao.getBySport(sport)
        val res = api.getDataset(sport)
        if (!res.isSuccessful) error("HTTP ${res.code()} for $sport")
        val body = res.body() ?: error("Empty response for $sport")
        val rows = body
            .filter { !it.date.isNullOrBlank() && !it.startTime.isNullOrBlank() }
            .map { it.toEntity(sport) }

        // A release is a session whose available court count went up compared
        // with the previous snapshot. The first snapshot of a sport only
        // establishes the baseline: there is nothing to compare against, so no
        // release events are recorded.
        if (previous.isNotEmpty()) {
            val releases = ReleaseDetector.detect(previous, rows).map { it.toReleaseEvent(sport) }
            if (releases.isNotEmpty()) {
                releaseEventDao.insertAll(releases)
            }
        }

        slotDao.replaceSport(sport, rows)
        // Evict rows for sports that were not refreshed recently.
        slotDao.deleteStale(System.currentTimeMillis() - STALE_AFTER_MS)
        return rows
    }

    suspend fun refreshSport(sport: String) {
        fetchAndCache(sport)
    }

    /** Pending release events, newest first. */
    suspend fun pendingReleaseEvents(limit: Int): List<ReleaseEventEntity> =
        releaseEventDao.pending(limit)

    suspend fun clearReleaseEvents(ids: List<String>) {
        if (ids.isNotEmpty()) releaseEventDao.deleteByIds(ids)
    }

    /** Housekeeping: drops events nobody will ever be notified about. */
    suspend fun pruneReleaseEvents(olderThanMillis: Long) {
        releaseEventDao.deleteOlderThan(System.currentTimeMillis() - olderThanMillis)
    }

    /**
     * The availability of a session right now, or `null` when the session is no
     * longer in the cache. Used to skip a release that was booked again
     * before the notification went out.
     */
    suspend fun currentAvailability(e: ReleaseEventEntity): Int? =
        slotDao.getByKey(e.sport, e.venue, e.facility, e.location, e.date, e.startTime)?.available

    private fun SlotEntity.toReleaseEvent(sport: String) = ReleaseEventEntity(
        id = "$sport|$venue|$facility|$location|$date|$startTime",
        sport = sport,
        venue = venue,
        facility = facility,
        location = location,
        district = district,
        date = date,
        startTime = startTime,
        endTime = endTime,
        available = available
    )

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

    private companion object {
        const val STALE_AFTER_MS = 7L * 24 * 3600 * 1000
    }
}