package de.epimediahub.app.ui

import de.epimediahub.app.data.V161SmartEpg
import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test

class V161PoliciesTest {
    private fun channel(id: String, name: String, epgId: String = "") =
        MediaEntry(id = id, name = name, kind = MediaKind.LIVE, epgId = epgId)

    @Test fun hdAnd4kReuseExistingGuide() {
        val channels = listOf(channel("1", "DE | RTL HD"), channel("2", "DE | RTL FHD"),
            channel("3", "DE | RTL 4K HEVC"))
        val guide = listOf(EpgItem("Film", "", 1234L, 2345L))
        val result = V161SmartEpg.enrich(channels, mapOf("1" to guide))
        assertEquals(guide, result["2"])
        assertEquals(guide, result["3"])
    }

    @Test fun countryAndTimeshiftRemainDistinct() {
        val channels = listOf(channel("1","RTL DE HD"),channel("2","RTL AT 4K"),
            channel("3","RTL DE +1 HD"),channel("4","RTL CH SD"))
        val result = V161SmartEpg.enrich(channels,
            mapOf("1" to listOf(EpgItem("Program", "", 1L, 2L))))
        assertFalse(result.containsKey("2"))
        assertFalse(result.containsKey("3"))
        assertFalse(result.containsKey("4"))
    }

    @Test fun disagreeingEpgIdsDoNotShare() {
        val channels = listOf(channel("1","RTL HD","rtl.de"),channel("2","RTL UHD","rtl.ch"))
        val result = V161SmartEpg.enrich(channels,
            mapOf("1" to listOf(EpgItem("News","",1L,2L))))
        assertFalse(result.containsKey("2"))
    }

    @Test fun neverMergeConflictingSchedules() {
        val a = listOf(EpgItem("A","",1L,2L))
        val b = listOf(EpgItem("B","",1L,2L))
        val channels = listOf(channel("1","RTL HD"),channel("2","RTL 4K"), channel("3","RTL FHD"))
        val result = V161SmartEpg.enrich(channels,mapOf("1" to a,"2" to b))
        assertFalse(result.containsKey("3"))
    }

    @Test fun vodBoundAndProviderBlock() {
        assertTrue(V161PlaybackRetryPolicy.shouldTryNext(MediaKind.MOVIE,null,1,6))
        assertFalse(V161PlaybackRetryPolicy.shouldTryNext(MediaKind.MOVIE,null,2,6))
        assertFalse(V161PlaybackRetryPolicy.shouldTryNext(MediaKind.EPISODE,429,1,6))
        assertFalse(V161PlaybackRetryPolicy.shouldTryNext(MediaKind.LIVE,403,1,6))
        assertTrue(V161PlaybackRetryPolicy.shouldTryNext(MediaKind.LIVE,null,2,6))
        assertTrue(V161PlaybackRetryPolicy.message(MediaKind.MOVIE,429,"HTTP 429").contains("429"))
    }
}
