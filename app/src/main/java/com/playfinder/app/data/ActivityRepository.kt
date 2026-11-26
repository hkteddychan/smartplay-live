package com.playfinder.app.data

import com.playfinder.app.data.local.dao.ActivityDao
import com.playfinder.app.data.local.entity.ActivityEntity
import kotlinx.coroutines.flow.Flow
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ActivityRepository @Inject constructor(
    private val dao: ActivityDao
) {
    fun observe(sport: String, district: String, from: String): Flow<List<ActivityEntity>> =
        dao.observe(sport, district, from)
}