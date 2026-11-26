package com.playfinder.app.data

import com.playfinder.app.data.remote.dto.LcsdRecord
import org.junit.Assert.assertEquals
import org.junit.Test

class LcsdRecordTest {
    @Test
    fun `available parses to int`() {
        val r = LcsdRecord(available = "12")
        assertEquals(12, r.available.toInt())
    }

    @Test
    fun `empty available defaults to zero`() {
        val r = LcsdRecord(available = "")
        assertEquals(0, r.available.toIntOrNull() ?: 0)
    }
}