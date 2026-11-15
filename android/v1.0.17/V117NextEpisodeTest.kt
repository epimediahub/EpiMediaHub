package de.epimediahub.app.ui

import de.epimediahub.app.data.V115Segment
import de.epimediahub.app.data.V115SegmentKind
import org.junit.Assert.*
import org.junit.Test

class V117NextEpisodeTest {
    private val duration = 2_400_000L
    private val credits = V115Segment(V115SegmentKind.OUTRO, 2_300_000, duration, "reviewed", true, 1.0)

    @Test fun verifiedTerminalCreditsStartTheWindowBeforeTheEpisodeEnds() {
        assertEquals(V117NextWindow(2_300_000, true), v117NextWindow(duration, listOf(credits)))
    }

    @Test fun unknownCreditsOnlyStartInTheFinalTenSeconds() {
        assertEquals(V117NextWindow(2_390_000, false), v117NextWindow(duration, emptyList()))
    }

    @Test fun aSceneAfterCreditsIsPreservedInsteadOfAutomaticallySkipped() {
        assertFalse(v117NextWindow(duration, listOf(credits.copy(endMs = duration - 30_000)))!!.credits)
    }

    @Test fun uncertainOrInvalidMarkersCannotTriggerAnEarlyEpisodeChange() {
        for (bad in listOf(credits.copy(durationMatched = false), credits.copy(confidence = .7),
            credits.copy(kind = V115SegmentKind.INTRO), credits.copy(startMs = -1),
            credits.copy(endMs = duration + 1), credits.copy(startMs = duration - 1_000))) {
            assertEquals(V117NextWindow(2_390_000, false), v117NextWindow(duration, listOf(bad)))
        }
    }

    @Test fun anUnknownRuntimeHasNoEstimatedCreditWindow() {
        assertNull(v117NextWindow(0, listOf(credits)))
        assertNull(v117NextWindow(-1, listOf(credits)))
        assertEquals(V117NextWindow(0, false), v117NextWindow(8_000, emptyList()))
    }
}
