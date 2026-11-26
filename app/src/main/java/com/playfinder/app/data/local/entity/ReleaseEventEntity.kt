package com.playfinder.app.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

/**
 * A release event: a session whose available court count went up compared with
 * the previous snapshot. The event log lets the background poller notify about
 * a release exactly once, even when the user-facing screen refreshed the cache
 * first.
 */
@Entity(tableName = "release_events", indices = [Index("detectedAt")])
data class ReleaseEventEntity(
    @PrimaryKey val id: String,
    val sport: String,
    val venue: String,
    val district: String,
    val date: String,
    val startTime: String,
    val endTime: String,
    val available: Int,
    val detectedAt: Long = System.currentTimeMillis()
)
