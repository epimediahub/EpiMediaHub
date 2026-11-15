package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V169CinemaModePolicyTest {
    private fun mode(id: Int, hz: Float, w: Int = 3840, h: Int = 2160) =
        V121DisplayMode(id, w, h, hz)
    private val base = mode(1, 50f)

    @Test fun sameResolutionWinsOver1080p() {
        val modes = listOf(base, mode(2, 24000f/1001f),
            mode(3, 24000f/1001f, 1920, 1080))
        assertEquals(2, V169CinemaModePolicy.matchingMode(base, modes, 24000f/1001f, true)?.id)
    }

    @Test fun fallsBackTo1080pFor24fpsButNotTo60hz() {
        val modes = listOf(base, mode(2, 60f), mode(3, 24f, 1920, 1080))
        assertEquals(3, V169CinemaModePolicy.matchingMode(base, modes, 24000f/1001f, true)?.id)
        assertNull(V169CinemaModePolicy.matchingMode(base, modes, 24000f/1001f, false))
    }

    @Test fun useExact23976OverApproximate24() {
        val modes = listOf(base, mode(2, 24f), mode(3, 24000f/1001f))
        assertEquals(3, V169CinemaModePolicy.matchingMode(base, modes, 24000f/1001f, true)?.id)
    }

    @Test fun twentyFiveFpsKeepsFiftyHertz() {
        assertEquals(base, V169CinemaModePolicy.matchingMode(base, listOf(base), 25f, true))
    }

    @Test fun unsupportedModesAndUnknownRateFailClosed() {
        assertNull(V169CinemaModePolicy.matchingMode(base, listOf(base), 24000f/1001f, true))
        assertNull(V169CinemaModePolicy.matchingMode(base, listOf(base), 0f, true))
        assertNull(V169CinemaModePolicy.matchingMode(base, listOf(base), Float.NaN, true))
    }

    @Test fun neverUpscalesOrSelectsUnrelatedResolution() {
        val current = mode(1, 50f, 1280, 720)
        val only1080 = mode(2, 24f, 1920, 1080)
        assertNull(V169CinemaModePolicy.matchingMode(current, listOf(current, only1080), 24f, true))
    }
}
