package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V192LiveCadencePolicyTest {
    private val current60 = V121DisplayMode(1, 3840, 2160, 60f)
    private val mode50 = V121DisplayMode(2, 3840, 2160, 50f)
    private val mode5994 = V121DisplayMode(3, 3840, 2160, 60000f / 1001f)
    private val otherResolution50 = V121DisplayMode(4, 1920, 1080, 50f)

    @Test fun pal25And50Need50HzAtSameResolution() {
        val modes = listOf(current60, mode50, mode5994)
        assertEquals(mode50, V192LiveCadencePolicy.target(current60, modes, 25f))
        assertEquals(mode50, V192LiveCadencePolicy.target(current60, modes, 50f))
        assertEquals(mode50, V192LiveCadencePolicy.target(mode50, modes, 25f))
    }

    @Test fun noFallbackTo25HzAndNoResolutionChanges() {
        assertNull(V192LiveCadencePolicy.target(current60, listOf(current60, otherResolution50), 25f))
        assertNull(V192LiveCadencePolicy.target(current60,
            listOf(current60, V121DisplayMode(5, 3840, 2160, 25f)), 25f))
        assertNull(V192LiveCadencePolicy.target(current60, listOf(current60), 0f))
        assertNull(V192LiveCadencePolicy.target(current60, listOf(current60), 23.976f))
    }

    @Test fun nTscCadenceDoesNotGuess() {
        val modes = listOf(current60, mode50, mode5994)
        assertEquals(current60, V192LiveCadencePolicy.target(current60, modes, 30f))
        assertEquals(mode5994, V192LiveCadencePolicy.target(current60, modes, 29.97f))
        assertEquals(mode5994, V192LiveCadencePolicy.target(current60, modes, 59.94f))
    }
}
