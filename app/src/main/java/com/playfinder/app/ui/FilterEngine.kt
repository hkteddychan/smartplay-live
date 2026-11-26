package com.playfinder.app.ui

import com.playfinder.app.data.local.entity.SlotEntity
import java.time.DayOfWeek
import java.time.LocalDate
import java.time.LocalTime
import kotlin.math.abs

enum class SortMode { TIME, AVAILABILITY, DISTANCE }

data class SlotFilter(
    val district: String = "",
    val date: String = "",
    val fromMinute: Int = 0,
    val toMinute: Int = 24 * 60,
    val onlyAvailable: Boolean = false,
    val search: String = ""
)

object FilterEngine {

    fun minuteOf(time: String): Int = runCatching {
        val parts = time.split(":")
        parts[0].toInt() * 60 + parts[1].toInt()
    }.getOrDefault(0)

    fun apply(slots: List<SlotEntity>, f: SlotFilter): List<SlotEntity> = slots.filter { s ->
        (f.district.isBlank() || s.district == f.district) &&
            (f.date.isBlank() || s.date == f.date) &&
            minuteOf(s.startTime) >= f.fromMinute &&
            minuteOf(s.startTime) < f.toMinute &&
            (!f.onlyAvailable || s.available > 0) &&
            (f.search.isBlank() || s.venue.contains(f.search, true) || s.facility.contains(f.search, true))
    }

    fun sort(slots: List<SlotEntity>, mode: SortMode, userLat: Double?, userLon: Double?): List<SlotEntity> =
        when (mode) {
            SortMode.TIME -> slots.sortedWith(compareBy({ it.date }, { minuteOf(it.startTime) }))
            SortMode.AVAILABILITY -> slots.sortedWith(
                compareByDescending<SlotEntity> { it.available }.thenBy { it.date }.thenBy { minuteOf(it.startTime) }
            )
            SortMode.DISTANCE -> {
                if (userLat == null || userLon == null) slots.sortedBy { it.venue }
                else slots.sortedBy { distanceMeters(it.lat, it.lon, userLat, userLon) }
            }
        }

    fun distanceMeters(lat1: Double, lon1: Double, lat2: Double, lon2: Double): Double {
        val r = 6371000.0
        val dLat = Math.toRadians(lat2 - lat1)
        val dLon = Math.toRadians(lon2 - lon1)
        val a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(Math.toRadians(lat1)) * Math.cos(Math.toRadians(lat2)) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2)
        return r * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
    }

    /** Mon-Fri 19:00-22:00 prime time (spec). */
    fun isPrimeTime(date: String, startTime: String): Boolean {
        val d = runCatching { LocalDate.parse(date) }.getOrNull() ?: return false
        if (d.dayOfWeek == DayOfWeek.SATURDAY || d.dayOfWeek == DayOfWeek.SUNDAY) return false
        val m = minuteOf(startTime)
        return m >= 19 * 60 && m < 22 * 60
    }

    /** 24 buckets: count of available slots per start hour. */
    fun heatmap(slots: List<SlotEntity>): IntArray {
        val out = IntArray(24)
        slots.forEach { if (it.available > 0) out[minuteOf(it.startTime) / 60]++ }
        return out
    }
}