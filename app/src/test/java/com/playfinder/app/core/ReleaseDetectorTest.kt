package com.playfinder.app.core

import com.playfinder.app.data.local.entity.SlotEntity
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ReleaseDetectorTest {

    private fun slot(
        venue: String = "香港公園體育館",
        date: String = "2026-11-27",
        start: String = "20:00",
        available: Int = 0
    ) = SlotEntity(
        sport = "badminton", venue = venue, district = "中西區", facility = "羽毛球場",
        location = "主場", date = date, startTime = start, endTime = "21:00",
        available = available, lat = 22.27, lon = 114.15
    )

    @Test
    fun `first snapshot only establishes a baseline`() {
        val current = listOf(slot(available = 4))
        assertTrue(ReleaseDetector.detect(emptyList(), current).isEmpty())
    }

    @Test
    fun `a session that goes from full to available is a release`() {
        val previous = listOf(slot(available = 0))
        val current = listOf(slot(available = 4))
        val releases = ReleaseDetector.detect(previous, current)
        assertEquals(1, releases.size)
        assertEquals(4, releases[0].available)
    }

    @Test
    fun `a session that gains more courts is a release`() {
        val previous = listOf(slot(available = 2))
        val current = listOf(slot(available = 4))
        assertEquals(1, ReleaseDetector.detect(previous, current).size)
    }

    @Test
    fun `a session that loses courts is not a release`() {
        val previous = listOf(slot(available = 4))
        val current = listOf(slot(available = 1))
        assertTrue(ReleaseDetector.detect(previous, current).isEmpty())
    }

    @Test
    fun `an unchanged session is not a release`() {
        val previous = listOf(slot(available = 4))
        val current = listOf(slot(available = 4))
        assertTrue(ReleaseDetector.detect(previous, current).isEmpty())
    }

    @Test
    fun `a brand new session counts as a release`() {
        val previous = listOf(slot(venue = "A", available = 0))
        val current = listOf(slot(venue = "A", available = 0), slot(venue = "B", available = 2))
        val releases = ReleaseDetector.detect(previous, current)
        assertEquals(1, releases.size)
        assertEquals("B", releases[0].venue)
    }
}
