package com.playfinder.app.core

import com.playfinder.app.data.local.entity.SlotEntity

/**
 * Detects "release" events: sessions whose available court count went up
 * compared with the previous snapshot.
 *
 * Pure logic, so it can be unit tested without a database. The first snapshot
 * of a sport only establishes the baseline — there is nothing to compare
 * against, so it never reports a release.
 */
object ReleaseDetector {

    fun key(s: SlotEntity): String =
        "${s.venue}|${s.facility}|${s.location}|${s.date}|${s.startTime}"

    fun detect(previous: List<SlotEntity>, current: List<SlotEntity>): List<SlotEntity> {
        // No baseline yet: everything would look like a release.
        if (previous.isEmpty()) return emptyList()
        val before = previous.associateBy { key(it) }
        return current.filter { it.available > (before[key(it)]?.available ?: 0) }
    }
}
