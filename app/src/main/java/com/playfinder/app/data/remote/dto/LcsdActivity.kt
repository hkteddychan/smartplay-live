package com.playfinder.app.data.remote.dto

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class LcsdActivity(
    @Json(name = "ACTIVITY_NO") val activityNo: String = "",
    @Json(name = "TC_PGM_NAME") val nameTc: String = "",
    @Json(name = "EN_PGM_NAME") val nameEn: String = "",
    @Json(name = "TC_ACT_TYPE_NAME") val typeTc: String = "",
    @Json(name = "EN_ACT_TYPE_NAME") val typeEn: String = "",
    @Json(name = "TC_DISTRICT") val districtTc: String = "",
    @Json(name = "EN_DISTRICT") val districtEn: String = "",
    @Json(name = "PGM_START_DATE") val startDate: String = "",
    @Json(name = "PGM_END_DATE") val endDate: String = "",
    @Json(name = "TC_DAY") val dayTc: String = "",
    @Json(name = "PGM_START_TIME") val startTime: String = "",
    @Json(name = "PGM_END_TIME") val endTime: String = "",
    @Json(name = "TC_VENUE") val venueTc: String = "",
    @Json(name = "TC_TARGET_GRP") val targetGroup: String = "",
    @Json(name = "FEE") val fee: Double = 0.0,
    @Json(name = "QUOTA") val quota: Int = 0,
    @Json(name = "PLACES_LEFT") val placesLeft: Int = 0,
    @Json(name = "ENROL_METHOD") val enrolMethod: String = "",
    @Json(name = "TC_URL") val url: String = ""
)