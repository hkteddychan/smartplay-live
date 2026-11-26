package com.playfinder.app.di

import android.content.Context
import androidx.room.Room
import com.playfinder.app.data.local.PlayFinderDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext ctx: Context): PlayFinderDatabase =
        Room.databaseBuilder(ctx, PlayFinderDatabase::class.java, "playfinder.db")
            .fallbackToDestructiveMigration()
            .build()

    @Provides
    fun provideSlotDao(db: PlayFinderDatabase) = db.slotDao()

    @Provides
    fun provideActivityDao(db: PlayFinderDatabase) = db.activityDao()
}