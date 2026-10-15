package de.epimediahub.app.vpn

import org.junit.Assert.*
import org.junit.Test

class V176GalaBoxMtuPilotTest {
    @Test fun onlyGalaBoxHardwareMatches() {
        assertTrue(V176GalaBoxMtuPilot.matchesGalaBox("GALABOX", "ELITE"))
        assertTrue(V176GalaBoxMtuPilot.matchesGalaBox("Generic", "GalaBox Elite"))
        assertFalse(V176GalaBoxMtuPilot.matchesGalaBox("Amazon", "Fire TV Stick 4K Max"))
        assertFalse(V176GalaBoxMtuPilot.matchesGalaBox("Samsung", "Galaxy S24"))
        assertFalse(V176GalaBoxMtuPilot.matchesGalaBox("Unknown", "Android Box"))
    }
    @Test fun selectionCycleHasSafeDefault() {
        assertEquals(1360, V176GalaBoxMtuPilot.next(0))
        assertEquals(1280, V176GalaBoxMtuPilot.next(1360))
        assertEquals(1420, V176GalaBoxMtuPilot.next(1280))
        assertEquals(0, V176GalaBoxMtuPilot.next(1420))
        assertEquals(0, V176GalaBoxMtuPilot.next(-1))
    }
}
