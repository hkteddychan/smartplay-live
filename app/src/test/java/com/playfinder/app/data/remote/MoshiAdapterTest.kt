package com.playfinder.app.data.remote

import com.playfinder.app.data.remote.dto.LcsdActivity
import com.playfinder.app.data.remote.dto.LcsdRecord
import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import org.junit.Assert.assertEquals
import org.junit.Test

class MoshiAdapterTest {

    private val moshi = Moshi.Builder().build()
    private val slotType = Types.newParameterizedType(List::class.java, LcsdRecord::class.java)
    private val actType = Types.newParameterizedType(List::class.java, LcsdActivity::class.java)

    @Test
    fun `LcsdRecord parses LCSD column names`() {
        val json = """
            [{"Venue_Name_TC":"香港公園體育館","Venue_Name_EN":"HK Park","District_Name_TC":"中西區",
              "Facility_Type_Name_TC":"羽毛球場 (空調)(市區)","Facility_Location_Name_TC":"主場",
              "Available_Date":"2026-11-27","Session_Start_Time":"07:00","Session_End_Time":"08:00",
              "Available_Courts":"6","Venue_Latitude":"22.277","Venue_Longitude":"114.159"}]
        """.trimIndent()
        val list = moshi.adapter<List<LcsdRecord>>(slotType).fromJson(json)!!
        assertEquals(1, list.size)
        val r = list[0]
        assertEquals("香港公園體育館", r.venueNameTc)
        assertEquals("中西區", r.districtNameTc)
        assertEquals("2026-11-27", r.date)
        assertEquals("07:00", r.startTime)
        assertEquals("08:00", r.endTime)
        assertEquals("6", r.available)
        assertEquals("主場", r.locationNameTc)
    }

    @Test
    fun `LcsdActivity parses programme columns`() {
        val json = """
            [{"ACTIVITY_NO":"EN260058OTR","TC_PGM_NAME":"家庭定向尋寶樂","TC_ACT_TYPE_NAME":"野外定向",
              "TC_DISTRICT":"東區","PGM_START_DATE":"2026-11-14","PGM_END_DATE":"2026-11-14",
              "TC_DAY":"逢星期六","PGM_START_TIME":"14:00","PGM_END_TIME":"15:30","TC_VENUE":"愛秩序灣海濱花園",
              "TC_TARGET_GRP":"一般人士","FEE":0.0,"QUOTA":200,"PLACES_LEFT":200,"ENROL_METHOD":"WALKIN",
              "TC_URL":"https://www.smartplay.lcsd.gov.hk/programme/detail?activityNo=EN260058OTR&&lang=tc"}]
        """.trimIndent()
        val list = moshi.adapter<List<LcsdActivity>>(actType).fromJson(json)!!
        assertEquals(1, list.size)
        assertEquals("家庭定向尋寶樂", list[0].nameTc)
        assertEquals("東區", list[0].districtTc)
        assertEquals(200, list[0].placesLeft)
    }
}
