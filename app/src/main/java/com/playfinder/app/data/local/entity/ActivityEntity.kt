package com.playfinder.app.data.local.entity

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "activities", indices = [Index("district"), Index("type"), Index("startDate")])
data class ActivityEntity(
    @PrimaryKey val id: String,
    val name: String,
    val type: String,
    val district: String,
    val startDate: String,
    val endDate: String,
    val day: String,
    val startTime: String,
    val endTime: String,
    val venue: String,
    val targetGroup: String,
    val fee: Double,
    val quota: Int,
    val placesLeft: Int,
    val enrolMethod: String,
    val url: String,
    val fetchedAt: Long = System.currentTimeMillis()
)