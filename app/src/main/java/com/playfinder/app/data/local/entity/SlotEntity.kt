package com.playfinder.app.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "slots")
data class SlotEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sport: String,
    val venue: String,
    val facility: String,
    val date: String,
    val startTime: String,
    val endTime: String,
    val available: Int,
    val fetchedAt: Long = System.currentTimeMillis()
)