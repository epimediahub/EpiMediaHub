package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V170LiveCadencePolicyTest {
    private fun mode(id: Int, hz: Float, w: Int = 3840, h: Int = 2160) =
        V121DisplayMode(id, w, h, hz)
    private val sixty = mode(1, 60f)
    private val fifty = mode(2, 50f)
    private val modes = listOf(sixty, fifty, mode(3, 25f),
        mode(4, 24f), mode(5, 24000f/1001f), mode(6, 60000f/1001f))

    @Test fun europeanLive25Uses50Not25() {
        assertEquals(2, V170LiveCadencePolicy.matchingMode(sixty, modes, 25f)?.id)
        assertEquals(fifty, V170LiveCadencePolicy.matchingMode(fifty, modes, 25f))
    }

    @Test fun fiftyFpsLiveStaysAtFifty() {
        assertEquals(fifty, V170LiveCadencePolicy.matchingMode(fifty, modes, 50f))
        assertEquals(2, V170LiveCadencePolicy.matchingMode(sixty, modes, 50f)?.id)
    }

    @Test fun live30Uses60AndFractional30Uses5994() {
        assertEquals(sixty, V170LiveCadencePolicy.matchingMode(fifty, modes, 30f))
        assertEquals(6, V170LiveCadencePolicy.matchingMode(fifty, modes, 30000f/1001f)?.id)
    }

    @Test fun cinemaContentUsesExact23976WhenEncounteredOnLive() {
        assertEquals(5, V170LiveCadencePolicy.matchingMode(sixty, modes, 24000f/1001f)?.id)
        assertEquals(4, V170LiveCadencePolicy.matchingMode(sixty, modes, 24f)?.id)
    }

    @Test fun doNotChangeVideoResolutionWhileZapping() {
        val fallback = mode(7, 50f, 1920, 1080)
        assertNull(V170LiveCadencePolicy.matchingMode(sixty, listOf(sixty, fallback), 25f))
    }

    @Test fun noUnstableGuessForUnknownStreamRate() {
        for (fps in listOf(0f, -1f, 26f, 48f, Float.NaN)) {
            assertNull(V170LiveCadencePolicy.matchingMode(sixty, modes, fps))
        }
    }

    @Test fun noRedundantSwitchWhenCurrentModeIsCorrect() {
        assertEquals(fifty, V170LiveCadencePolicy.matchingMode(fifty, modes, 25f))
    }
}
