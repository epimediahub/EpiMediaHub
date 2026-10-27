package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V191LiveHeadersTest {
    @Test fun separatorRowsAreNotWatchable() {
        for (name in listOf("--- INTRATTENIMENTO BACKUP ---",
            "---- SKY CALCIO SATELLITE ----", "*** SKY SPORT ***", "=== Cinema ==="))
            assertTrue(name, V191LiveHeaders.isNonPlayableName(name))
    }

    @Test fun actualChannelsAndShortDecorationsAreKept() {
        for (name in listOf("SKY UNO HD", "SKY SPORT F1 4K",
            "- SPORT 1 -", "3SAT HD", "-----", "SKY - BUNDESLIGA 1 HD"))
            assertFalse(name, V191LiveHeaders.isNonPlayableName(name))
    }
}
