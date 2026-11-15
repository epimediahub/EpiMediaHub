package de.epimediahub.app.data

import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class RadioModelsTest {
    private fun api(extra: String = ""): JsonObject = radioJson.parseToJsonElement("""{
        "stationuuid":"abc-123", "name":"Radio Epi", "url":"http://radio.example/old.pls",
        "url_resolved":"https://radio.example/live", "countrycode":"IT", "language":"italian,english",
        "tags":"rock,news", "codec":"MP3", "bitrate":128, "lastcheckok":1 $extra
    }""").jsonObject

    @Test fun resolvedStreamAndStableUuidAreUsed() {
        val station = radioStationFromApi(api())!!
        assertEquals("https://radio.example/live", station.streamUrl)
        assertEquals("abc-123", station.uuid)
        assertEquals("Italien", station.country)
        assertTrue(station.description.contains("Italienisch / Englisch"))
    }
    @Test fun brokenEntriesMissingIdsAndUnsafeSchemesAreExcluded() {
        for ((key, value) in listOf("lastcheckok" to JsonPrimitive(0), "name" to JsonPrimitive(""), "stationuuid" to JsonPrimitive(""))) {
            assertNull(radioStationFromApi(JsonObject(api().toMutableMap().apply { this[key] = value })))
        }
        assertFalse(radioHttpUrl("file:///tmp/audio"))
        assertFalse(radioHttpUrl("https://user:password@radio.example/audio"))
        assertFalse(radioHttpUrl("javascript:alert(1)"))
        assertTrue(radioHttpUrl("http://radio.example:8000/live"))
    }
    @Test fun countryAndLanguageCanBeCombinedIndependently() {
        val station = radioStationFromApi(api())!!
        assertTrue(RadioQuery(countryCode = "IT", language = "english", categoryId = "rock").accepts(station))
        assertFalse(RadioQuery(countryCode = "DE").accepts(station))
        assertFalse(RadioQuery(language = "german").accepts(station))
        assertTrue(RadioQuery(name = "RADIO ÉPI").accepts(station))
    }
    @Test fun combinedQueryIsEscapedAndPaginationIsBounded() {
        val path = RadioQuery("A & B", "it", "english", "hiphop").path("hip hop", 20, 10_000)
        for (part in listOf("name=A+%26+B", "countrycode=IT", "language=english", "tag=hip+hop", "offset=20", "limit=60", "hidebroken=true")) assertTrue(path.contains(part))
        assertFalse(path.contains("tagList"))
    }
    @Test fun duplicateStreamsAndUuidsCollapseWhileDifferentStationsRemain() {
        val a = radioStationFromApi(api())!!
        val values = listOf(a.copy(clicks = 100), a.copy(uuid = "other", clicks = 5), a.copy(streamUrl = "https://radio.example/alternate"),
            a.copy(uuid = "different", name = "Other", streamUrl = "https://different.example/live"))
        assertEquals(listOf("abc-123", "different"), radioUniqueStations(values).map { it.uuid })
    }
    @Test fun boundedPlayerQueueContainsTheSelectionAndItsNeighbors() {
        val stations = (0..499).map { RadioStation("id-$it", "Station $it", "https://radio.example/$it") }
        val queue = radioPlaybackQueue(stations, stations[450])
        assertEquals(200, queue.size)
        assertEquals("id-449", queue[queue.indexOf(stations[450]) - 1].uuid)
        assertEquals("id-451", queue[queue.indexOf(stations[450]) + 1].uuid)
        val missing = RadioStation("new", "New", "https://new.example/live")
        assertTrue(radioPlaybackQueue(stations, missing).contains(missing))
    }
}
