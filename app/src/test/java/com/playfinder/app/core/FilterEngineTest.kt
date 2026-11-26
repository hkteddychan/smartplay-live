package com.playfinder.app.core

import com.playfinder.app.data.local.entity.SlotEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class FilterEngineTest {

    private fun slot(
        district: String = "中西區",
        date: String = "2026-11-27",
        start: String = "20:00",
        available: Int = 4,
        venue: String = "香港公園體育館",
        lat: Double = 22.2773,
        lon: Double = 114.1593
    ) = SlotEntity(
        sport = "badminton", venue = venue, district = district, facility = "羽毛球場",
        location = "主場", date = date, startTime = start, endTime = "21:00",
        available = available, lat = lat, lon = lon
    )

    @Test
    fun `filter by district`() {
        val slots = listOf(slot(), slot(district = "沙田區"))
        val r = FilterEngine.apply(slots, SlotFilter(district = "沙田區"))
        assertEquals(1, r.size)
        assertEquals("沙田區", r[0].district)
    }

    @Test
    fun `filter by time range excludes outside slots`() {
        val slots = listOf(slot(start = "08:00"), slot(start = "20:00"))
        val r = FilterEngine.apply(slots, SlotFilter(fromMinute = 19 * 60, toMinute = 22 * 60))
        assertEquals(1, r.size)
        assertEquals("20:00", r[0].startTime)
    }

    @Test
    fun `filter only available`() {
        val slots = listOf(slot(available = 0), slot(available = 3))
        assertEquals(1, FilterEngine.apply(slots, SlotFilter(onlyAvailable = true)).size)
    }

    @Test
    fun `sort by availability descending`() {
        val slots = listOf(slot(available = 1), slot(available = 9))
        assertEquals(9, FilterEngine.sort(slots, SortMode.AVAILABILITY, null, null)[0].available)
    }

    @Test
    fun `prime time is weekday 19-22`() {
        assertTrue(FilterEngine.isPrimeTime("2026-11-27", "20:00"))
        assertFalse(FilterEngine.isPrimeTime("2026-11-28", "20:00")) // Saturday
        assertFalse(FilterEngine.isPrimeTime("2026-11-27", "18:00"))
    }

    @Test
    fun `heatmap counts available slots per hour`() {
        val slots = listOf(slot(start = "07:00", available = 2), slot(start = "07:30", available = 3), slot(start = "20:00", available = 0))
        val h = FilterEngine.heatmap(slots)
        assertEquals(2, h[7])
        assertEquals(0, h[20])
    }

    @Test
    fun `distance increases with separation`() {
        val near = FilterEngine.distanceMeters(22.2773, 114.1593, 22.28, 114.16)
        val far = FilterEngine.distanceMeters(22.2773, 114.1593, 22.50, 114.50)
        assertTrue(far > near)
    }

    @Test
    fun `malformed time is excluded by any time filter`() {
        val bad = slot(start = "not-a-time")
        assertEquals(0, FilterEngine.apply(listOf(bad), SlotFilter()).size)
    }

    @Test
    fun `heatmap ignores malformed times instead of crashing`() {
        val h = FilterEngine.heatmap(listOf(slot(start = "??", available = 3)))
        assertEquals(0, h.sum())
    }
}