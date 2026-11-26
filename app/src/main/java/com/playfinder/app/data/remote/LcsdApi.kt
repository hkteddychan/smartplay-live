package com.playfinder.app.data.remote

import com.playfinder.app.data.remote.dto.LcsdActivity
import com.playfinder.app.data.remote.dto.LcsdMetadata
import com.playfinder.app.data.remote.dto.LcsdRecord
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Path

interface LcsdApi {
    @GET("{name}/file")
    suspend fun getDataset(@Path("name") name: String): Response<List<LcsdRecord>>

    @GET("activity-prog/file")
    suspend fun getActivities(): Response<List<LcsdActivity>>

    @GET("{name}")
    suspend fun getMetadata(@Path("name") name: String): Response<LcsdMetadata>
}