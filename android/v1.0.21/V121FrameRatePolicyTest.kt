package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V121FrameRatePolicyTest {
    private fun mode(id: Int, hz: Float, width: Int = 3840, height: Int = 2160) = V121DisplayMode(id, width, height, hz)
    private val sixty = mode(1, 60f)

    @Test fun moviesUseAWholeFrameCadenceInsteadOfSixtyHzPulldown() {
        val modes = listOf(sixty, mode(2, 24f), mode(3, 50f))
        assertEquals(2, V121FrameRatePolicy.matchingMode(sixty, modes, 24f)?.id)
        assertEquals(3, V121FrameRatePolicy.matchingMode(sixty, modes, 25f)?.id)
    }

    @Test fun fractionalRatesAreNotRoundedToIntegerRates() {
        val modes = listOf(sixty, mode(2, 24f), mode(3, 24000f / 1001f), mode(4, 60000f / 1001f))
        assertEquals(3, V121FrameRatePolicy.matchingMode(sixty, modes, 24000f / 1001f)?.id)
        assertEquals(4, V121FrameRatePolicy.matchingMode(sixty, modes, 30000f / 1001f)?.id)
        assertEquals(2, V121FrameRatePolicy.matchingMode(sixty, modes, 24f)?.id)
    }

    @Test fun alreadyCompatibleDisplayDoesNotSwitch() {
        assertEquals(sixty, V121FrameRatePolicy.matchingMode(sixty, listOf(sixty, mode(2, 30f)), 30f))
        val high = mode(3, 120f)
        assertEquals(high, V121FrameRatePolicy.matchingMode(high, listOf(high, mode(4, 24f)), 24f))
    }

    @Test fun neverChangesResolutionToFindAMatchingRate() {
        assertNull(V121FrameRatePolicy.matchingMode(sixty, listOf(sixty, mode(2, 24f, 1920, 1080)), 24f))
    }

    @Test fun unknownOrImpossibleMetadataLeavesTheDisplayAlone() {
        for (fps in listOf(-1f, 0f, Float.NaN, Float.POSITIVE_INFINITY, 1f, 500f)) {
            assertNull(V121FrameRatePolicy.matchingMode(sixty, listOf(sixty, mode(2, 24f)), fps))
        }
        assertNull(V121FrameRatePolicy.matchingMode(sixty, listOf(sixty), 25f))
    }

    @Test fun slowDisplayIsNotMistakenForAMultipleOfHighFrameRate() {
        assertNull(V121FrameRatePolicy.matchingMode(mode(1, 24f), listOf(mode(1, 24f)), 60f))
    }
}
