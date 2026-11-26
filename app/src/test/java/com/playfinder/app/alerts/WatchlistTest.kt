package com.playfinder.app.alerts

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class WatchlistTest {

    @Test
    fun `push is active only while expiry is in the future`() {
        val now = 1_800_000_000_000L
        val active = Watchlist(pushEnabled = true, pushUntilEpoch = now + 1_000)
        val expired = Watchlist(pushEnabled = true, pushUntilEpoch = now - 1_000)
        val disabled = Watchlist(pushEnabled = false, pushUntilEpoch = now + 1_000)

        assertTrue(active.pushActive(now))
        assertFalse(expired.pushActive(now))
        assertFalse(disabled.pushActive(now))
    }

    @Test
    fun `epoch millis survive as long beyond Int range`() {
        val now = 1_800_000_000_000L
        val wl = Watchlist(pushEnabled = true, pushUntilEpoch = now + 7L * 24 * 3600 * 1000)
        // Regression: the v1.0 build stored this as Int and wrapped negative.
        assertTrue(wl.pushUntilEpoch > Int.MAX_VALUE)
        assertTrue(wl.pushActive(now))
    }
}
