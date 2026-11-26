package com.playfinder.app.data.remote.dto

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class LcsdRecord(
    @Json(name = "Venue_Name_TC") val venueNameTc: String = "",
    @Json(name = "Venue_Name_EN") val venueNameEn: String = "",
    @Json(name = "District_Name_TC") val districtNameTc: String = "",
    @Json(name = "Facility_Type_Name_TC") val facilityNameTc: String = "",
    @Json(name = "Facility_Type_Name_EN") val facilityNameEn: String = "",
    @Json(name = "Date") val date: String = "",
    @Json(name = "Session_Start_Time") val startTime: String = "",
    @Json(name = "Session_End_Time") val endTime: String = "",
    @Json(name = "Available") val available: String = ""
)