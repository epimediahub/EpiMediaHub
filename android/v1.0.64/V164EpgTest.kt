package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import kotlinx.coroutines.*
import org.junit.Assert.*
import org.junit.Test

class V164EpgTest {
    @Test fun acceptsEpochSecondsAndProviderMilliseconds() {
        assertEquals(1_800_000_000L, V164Epg.seconds(1_800_000_000L))
        assertEquals(1_800_000_000L, V164Epg.seconds(1_800_000_000_123L))
        assertEquals(0L, V164Epg.seconds(0L))
    }

    @Test fun playingGuideRetriesWithoutReopeningWhileBrowsingKeepsItsCooldown() = runBlocking<Unit> {
        var clock = 0L
        var attempts = 0
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val queue = V163EpgQueue(scope, clock = { clock })
            assertTrue(queue.submit("playing", true) { attempts++; false })
            clock = 1_499L
            assertFalse(queue.submit("playing", true) { error("Premature retry") })
            clock = 1_600L
            assertTrue(queue.submit("playing", true) { attempts++; true })
            assertEquals(2, attempts)
            assertTrue(queue.submit("browsing", false) { false })
            clock += 2_000L
            assertFalse(queue.submit("browsing", false) { error("Background retry flood") })
        } finally { scope.cancel() }
    }

    @Test fun missingQualityVariantUsesValidatedStationSiblingAndRespectsDirectData() = runBlocking<Unit> {
        val now = EpgItem("Aktuelle Sendung", "Beschreibung", 100L, 200L)
        val calls = mutableListOf<String>()
        val guide = V164Epg.load("4k", peers = { listOf("hd", "sd") }, cached = { emptyList() },
            fetch = { id -> calls.add(id); if (id == "hd") listOf(now) else emptyList() },
            publish = { _, _ -> }, now = { 150L })
        assertEquals(listOf("4k", "hd"), calls)
        assertEquals(listOf(now), guide)
        calls.clear()
        val direct = V164Epg.load("4k", peers = { error("Direct guide must be authoritative") },
            cached = { listOf(now) }, fetch = { calls.add(it); emptyList() }, publish = { _, _ -> }, now = { 150L })
        assertEquals(listOf(now), direct)
        assertTrue(calls.isEmpty())
    }

    @Test fun missingStationFallbackIsBoundedAndRejectsExpiredGuides() = runBlocking<Unit> {
        val expired = EpgItem("Alt", "", 0L, 100L)
        val calls = mutableListOf<String>()
        val guide = V164Epg.load("a", peers = { listOf("a", "b", "b", "c", "d") },
            cached = { listOf(expired) }, fetch = { calls.add(it); emptyList() },
            publish = { _, _ -> }, now = { 150L })
        assertTrue(guide.isEmpty())
        assertEquals(listOf("a", "b", "c"), calls)
    }
}
