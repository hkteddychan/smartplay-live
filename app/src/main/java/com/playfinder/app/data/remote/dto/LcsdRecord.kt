package com.playfinder.app.data.remote.dto

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

/**
 * One bookable session from the LCSD open-data feed.
 * Every field is nullable: the upstream feed occasionally emits JSON nulls,
 * and a single null must not abort the whole refresh.
 */
@JsonClass(generateAdapter = true)
data class LcsdRecord(
    @Json(name = "Venue_Name_TC") val venueNameTc: String? = null,
    @Json(name = "Venue_Name_EN") val venueNameEn: String? = null,
    @Json(name = "District_Name_TC") val districtNameTc: String? = null,
    @Json(name = "Facility_Type_Name_TC") val facilityNameTc: String? = null,
    @Json(name = "Facility_Type_Name_EN") val facilityNameEn: String? = null,
    @Json(name = "Facility_Location_Name_TC") val locationNameTc: String? = null,
    @Json(name = "Available_Date") val date: String? = null,
    @Json(name = "Session_Start_Time") val startTime: String? = null,
    @Json(name = "Session_End_Time") val endTime: String? = null,
    @Json(name = "Available_Courts") val available: String? = null,
    @Json(name = "Venue_Latitude") val lat: String? = null,
    @Json(name = "Venue_Longitude") val lon: String? = null
)
