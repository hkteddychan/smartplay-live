package com.playfinder.app.data.remote.dto

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

/**
 * One programme activity. Nullable on purpose: optional columns such as
 * TC_TARGET_GRP / TC_URL are sometimes null in the feed, and a non-null
 * Kotlin type makes Moshi throw for the entire response.
 */
@JsonClass(generateAdapter = true)
data class LcsdActivity(
    @Json(name = "ACTIVITY_NO") val activityNo: String? = null,
    @Json(name = "TC_PGM_NAME") val nameTc: String? = null,
    @Json(name = "EN_PGM_NAME") val nameEn: String? = null,
    @Json(name = "TC_ACT_TYPE_NAME") val typeTc: String? = null,
    @Json(name = "EN_ACT_TYPE_NAME") val typeEn: String? = null,
    @Json(name = "TC_DISTRICT") val districtTc: String? = null,
    @Json(name = "EN_DISTRICT") val districtEn: String? = null,
    @Json(name = "PGM_START_DATE") val startDate: String? = null,
    @Json(name = "PGM_END_DATE") val endDate: String? = null,
    @Json(name = "TC_DAY") val dayTc: String? = null,
    @Json(name = "PGM_START_TIME") val startTime: String? = null,
    @Json(name = "PGM_END_TIME") val endTime: String? = null,
    @Json(name = "TC_VENUE") val venueTc: String? = null,
    @Json(name = "TC_TARGET_GRP") val targetGroup: String? = null,
    @Json(name = "FEE") val fee: Double? = 0.0,
    @Json(name = "QUOTA") val quota: Int? = 0,
    @Json(name = "PLACES_LEFT") val placesLeft: Int? = 0,
    @Json(name = "ENROL_METHOD") val enrolMethod: String? = null,
    @Json(name = "TC_URL") val url: String? = null
)
