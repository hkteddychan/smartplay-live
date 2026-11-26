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
    fun observe(district: String, type: String, from: String): Flow<List<ActivityEntity>> =
        dao.observe(district, type, from)

    suspend fun refresh() {
        val res = api.getActivities()
        if (res.isSuccessful) {
            dao.insertAll(res.body().orEmpty().map { it.toEntity() })
            dao.deleteStale(System.currentTimeMillis() - 14L * 24 * 3600 * 1000)
        }
    }

    private fun LcsdActivity.toEntity() = ActivityEntity(
        id = activityNo,
        name = nameTc.trim(),
        type = typeTc.trim(),
        district = districtTc.trim(),
        startDate = startDate,
        endDate = endDate,
        day = dayTc.trim(),
        startTime = startTime,
        endTime = endTime,
        venue = venueTc.trim(),
        targetGroup = targetGroup.trim(),
        fee = fee,
        quota = quota,
        placesLeft = placesLeft,
        enrolMethod = enrolMethod,
        url = url
    )
}