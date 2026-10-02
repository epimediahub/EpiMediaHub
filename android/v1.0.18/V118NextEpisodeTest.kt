package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V118NextEpisodeTest {
    @Test fun startsFortySecondsBeforeTheActualEnd() {
        assertEquals(V118NextWindow(2_360_000L), v118NextWindow(2_400_000L))
        assertEquals(V118NextWindow(0), v118NextWindow(25_000L))
    }
    @Test fun unknownRuntimeDoesNotGuessWhenToAdvance() {
        assertNull(v118NextWindow(0)); assertNull(v118NextWindow(-1))
    }
    @Test fun countdownGivesTenSecondsButNeverExceedsTheActualEnd() {
        assertEquals(2_370_000L, v118NextTarget(2_360_000L, 2_400_000L))
        assertEquals(2_400_000L, v118NextTarget(2_395_000L, 2_400_000L))
    }
}
