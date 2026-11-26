package com.playfinder.app.data.local.entity

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "activities")
data class ActivityEntity(
    @PrimaryKey val id: String,
    val name: String,
    val type: String,
    val district: String,
    val startDate: String,
    val endDate: String,
    val venue: String,
    val available: Int,
    val fetchedAt: Long = System.currentTimeMillis()
)