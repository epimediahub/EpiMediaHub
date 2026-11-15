package de.epimediahub.app.vpn

import org.junit.Assert.*
import org.junit.Test

class V173GalaBoxKeyCompatTest {
    @Test fun amazonFireTvNeverEligibleForPilot() {
        assertTrue(V173GalaBoxKeyCompat.isAmazon("Amazon", "AFT"))
        assertTrue(V173GalaBoxKeyCompat.isAmazon("unknown", "amazon"))
        assertTrue(V173GalaBoxKeyCompat.isAmazon("AMAZON", "amazon"))
        assertFalse(V173GalaBoxKeyCompat.isAmazon("Rockchip", "Generic"))
    }

    @Test fun independentEncryptedFileVersionAndPurposeSpecificAliases() {
        assertEquals(2, V173GalaBoxKeyCompat.VERSION.toInt())
        assertNotEquals(V173GalaBoxKeyCompat.IDENTITY_ALIAS, V173GalaBoxKeyCompat.PROFILE_ALIAS)
        assertTrue(V173GalaBoxKeyCompat.IDENTITY_ALIAS.contains("galabox"))
        assertTrue(V173GalaBoxKeyCompat.PROFILE_ALIAS.contains("galabox"))
    }
}
