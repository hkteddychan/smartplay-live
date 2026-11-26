package com.playfinder.app.data.remote.dto

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class LcsdMetadata(
    @Json(name = "generated_utc") val generatedUtc: String = "",
    @Json(name = "count") val count: Int = 0
)