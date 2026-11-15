package de.epimediahub.app.data

import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.launch
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test

class V125SkipPresenceTest {
    @Test fun olderServerDoesNotReceiveAnExtraHeartbeatWhenPlaybackEnds() {
        val capabilities = V125PresenceCapabilities()
        capabilities.recorded("old-server", false)
        assertFalse(capabilities.release("old-server"))
    }

    @Test fun releaseRequiresAnAcknowledgedSessionAndIsSentOnlyOnce() {
        val capabilities = V125PresenceCapabilities()
        capabilities.recorded("current", true)
        assertFalse(capabilities.release("previous"))
        assertTrue(capabilities.release("current"))
        assertFalse(capabilities.release("current"))
    }

    @Test fun cancellingPlaybackImmediatelyReleasesItsLease() = runBlocking {
        val recorded = CompletableDeferred<Unit>()
        val events = mutableListOf<Boolean>()
        val job = launch { v125KeepSkipPresence { events += it; if (it) recorded.complete(Unit) } }
        recorded.await()
        job.cancelAndJoin()
        assertEquals(listOf(true, false), events)
    }

    @Test fun centralCorrectionReplacesThePreviousCentralMarkAndRetainsOtherProviders() {
        val old = V115Segment(V115SegmentKind.INTRO, 20_000, 60_000, "EpiMediaHub · geprüft", true, 1.0)
        val publicOutro = V115Segment(V115SegmentKind.OUTRO, 2_100_000, 2_200_000, "SkipDB", true, 1.0)
        val corrected = old.copy(startMs = 23_000)
        val result = v125MergeCentral(listOf(old, publicOutro), V116SkipResult(listOf(corrected), ""))
        assertEquals(listOf(publicOutro, corrected), result)
    }

    @Test fun centralRevocationAndExplicitDisableRemoveOldMarkers() {
        val old = V115Segment(V115SegmentKind.INTRO, 20_000, 60_000, "EpiMediaHub · geprüft", true, 1.0)
        assertTrue(v125MergeCentral(listOf(old), V116SkipResult(emptyList(), "")).isEmpty())
        assertTrue(v125MergeCentral(listOf(old.copy(source = "SkipDB")),
            V116SkipResult(emptyList(), "", setOf(V115SegmentKind.INTRO))).isEmpty())
    }
}
