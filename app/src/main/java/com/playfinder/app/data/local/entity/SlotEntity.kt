package com.playfinder.app.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(
    tableName = "slots",
    indices = [
        Index("sport"),
        Index("date"),
        Index("district"),
        // One row per bookable session; prevents duplicates accumulating on every refresh.
        Index(
            value = ["sport", "venue", "facility", "location", "date", "startTime"],
            unique = true
        )
    ]
)
data class SlotEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sport: String,
    val venue: String,
    val district: String,
    val facility: String,
    val location: String,
    val date: String,
    val startTime: String,
    val endTime: String,
    val available: Int,
    val lat: Double,
    val lon: Double,
    val fetchedAt: Long = System.currentTimeMillis()
)
