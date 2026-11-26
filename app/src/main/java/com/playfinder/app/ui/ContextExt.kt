package com.playfinder.app.ui

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper

/** Finds the hosting Activity from any Context (needed to show ads). */
tailrec fun Context.findActivity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> baseContext.findActivity()
    else -> null
}
