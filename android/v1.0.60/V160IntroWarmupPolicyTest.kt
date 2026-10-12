package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V160IntroWarmupPolicyTest {
    @Test fun onlyApprovedActiveIntroCanWarmMetadata() {
        assertTrue(V160IntroWarmupPolicy.allowed(true, true, true, true, true))
        assertFalse(V160IntroWarmupPolicy.allowed(false, true, true, true, true))
        assertFalse(V160IntroWarmupPolicy.allowed(true, false, true, true, true))
        assertFalse(V160IntroWarmupPolicy.allowed(true, true, false, true, true))
        assertFalse(V160IntroWarmupPolicy.allowed(true, true, true, false, true))
        assertFalse(V160IntroWarmupPolicy.allowed(true, true, true, true, false))
    }
    @Test fun denialNeverOverriddenByIntroTime() {
        for (paired in listOf(true, false)) {
            assertFalse(V160IntroWarmupPolicy.allowed(true, paired, true, false, true))
        }
    }
}
