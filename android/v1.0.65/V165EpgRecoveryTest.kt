package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

/** Protect the now/next split against the v164 guide fallback regression. */
class V165EpgRecoveryTest {
    @Test fun unorderedProviderEventsShowCurrentAndFutureSeparately() {
        val entries = listOf(
            EpgItem("Danach", "Nächstes Programm", 200L, 300L),
            EpgItem("Jetzt", "Aktuelle Sendung", 100L, 200L)
        )
        assertEquals("Jetzt", V163Epg.current(entries, 150L)?.title)
        assertEquals("Danach", V163Epg.next(entries, 150L)?.title)
        assertEquals("Aktuelle Sendung", V163Epg.current(entries, 150L)?.description)
    }

    @Test fun futureProgrammeMustNotPretendToBeCurrent() {
        val entries = listOf(EpgItem("Erst später", "", 200L, 300L))
        assertNull(V163Epg.current(entries, 150L))
        assertEquals("Erst später", V163Epg.next(entries, 150L)?.title)
    }

    @Test fun priorityFailureGetsOneBoundedRetryButBackgroundRetainsCooldown() = runBlocking {
        var clock = 0L
        var tries = 0
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val queue = V163EpgQueue(scope, clock = { clock })
            assertTrue(queue.submit("selected", true) { tries++; false })
            assertEquals(1, tries)
            clock = 5_999L
            assertFalse(queue.submit("selected", true) { error("Too early") })
            clock = 6_000L
            assertTrue(queue.submit("selected", true) { tries++; true })
            assertEquals(2, tries)
            assertTrue(queue.submit("background", false) { false })
            clock = 12_000L
            assertFalse(queue.submit("background", false) { error("Too many fetches") })
        } finally {
            scope.cancel()
        }
    }
}
