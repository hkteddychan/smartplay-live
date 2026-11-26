package com.playfinder.app.ui

import android.content.Intent
import androidx.core.net.toUri

object DeepLink {
    private const val BOOKING_BASE = "https://www.lcsd.gov.hk/smartplay"
    fun openInBrowser(context: android.content.Context) {
        val i = Intent(Intent.ACTION_VIEW, BOOKING_BASE.toUri()).apply {
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(i)
    }
}