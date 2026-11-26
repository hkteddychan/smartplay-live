package com.playfinder.app.data.local

import androidx.room.Database
import androidx.room.RoomDatabase
import com.playfinder.app.data.local.dao.ActivityDao
import com.playfinder.app.data.local.dao.ReleaseEventDao
import com.playfinder.app.data.local.dao.SlotDao
import com.playfinder.app.data.local.entity.ActivityEntity
import com.playfinder.app.data.local.entity.ReleaseEventEntity
import com.playfinder.app.data.local.entity.SlotEntity

@Database(
    entities = [SlotEntity::class, ActivityEntity::class, ReleaseEventEntity::class],
    version = 4,
    exportSchema = false
)
abstract class PlayFinderDatabase : RoomDatabase() {
    abstract fun slotDao(): SlotDao
    abstract fun activityDao(): ActivityDao
    abstract fun releaseEventDao(): ReleaseEventDao
}
