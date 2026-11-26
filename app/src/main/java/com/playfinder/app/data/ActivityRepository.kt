package com.playfinder.app.data

import com.playfinder.app.data.local.dao.ActivityDao
import com.playfinder.app.data.local.entity.ActivityEntity
import com.playfinder.app.data.remote.LcsdApi
import com.playfinder.app.data.remote.dto.LcsdActivity
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ActivityRepository @Inject constructor(
    private val api: LcsdApi,
    private val dao: ActivityDao
) {
    fun observe(district: String, type: String, from: String, to: String): Flow<List<ActivityEntity>> =
        dao.observe(district, type, from, to)

    fun observeAll(): Flow<List<ActivityEntity>> = dao.observeAll()

    suspend fun refresh() {
        val res = api.getActivities()
        if (!res.isSuccessful) error("HTTP ${res.code()} for activity-prog")
        val body = res.body() ?: error("Empty response for activity-prog")
        val rows = body
            .filter { !it.activityNo.isNullOrBlank() }
            .map { it.toEntity() }
        dao.replaceAll(rows)
    }

    private fun LcsdActivity.toEntity() = ActivityEntity(
        id = activityNo?.trim().orEmpty(),
        name = nameTc?.trim().orEmpty(),
        type = typeTc?.trim().orEmpty(),
        district = districtTc?.trim().orEmpty(),
        startDate = startDate?.trim().orEmpty(),
        endDate = endDate?.trim().orEmpty(),
        day = dayTc?.trim().orEmpty(),
        startTime = startTime?.trim().orEmpty(),
        endTime = endTime?.trim().orEmpty(),
        venue = venueTc?.trim().orEmpty(),
        targetGroup = targetGroup?.trim().orEmpty(),
        fee = fee ?: 0.0,
        quota = quota ?: 0,
        placesLeft = placesLeft ?: 0,
        enrolMethod = enrolMethod?.trim().orEmpty(),
        enrolStartDate = enrolStartDate?.trim().orEmpty(),
        enrolEndDate = enrolEndDate?.trim().orEmpty(),
        url = url?.trim().orEmpty()
    )
}
