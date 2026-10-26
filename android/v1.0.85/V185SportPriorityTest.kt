package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V185SportPriorityTest {
    private fun v(id: String, name: String, profile: String = "the-best", measured: Int = 0) =
        V185SportPriority.Variant(id, name, profile, measured)

    @Test fun prioritizesExplicitFiftyFpsWithinSamePlaylist() {
        val options = listOf(v("1", "DAZN 1 4K 25 FPS"), v("2", "DAZN 1 FHD 50FPS"))
        assertEquals(1, V185SportPriority.bestIndex(0, options))
        assertEquals(1, V185SportPriority.bestIndex(1, options))
    }

    @Test fun neverSwitchesBetweenProvidersOrLanguageVariants() {
        assertEquals(0, V185SportPriority.bestIndex(0, listOf(
            v("1", "DAZN 1 DE 25FPS", "4k"),
            v("2", "DAZN 1 DE 50FPS", "the-best"))))
        assertEquals(0, V185SportPriority.bestIndex(0, listOf(
            v("1", "Sky Bundesliga DE 25FPS"),
            v("2", "Sky Bundesliga IT 50FPS"))))
    }

    @Test fun trustsObservedFpsOverUnverifiedLabel() {
        assertEquals(0, V185SportPriority.bestIndex(0, listOf(
            v("1", "DAZN 1 HD 50 FPS", measured = 50),
            v("2", "DAZN 1 4K 50 FPS", measured = 25))))
        assertEquals(1, V185SportPriority.bestIndex(0, listOf(
            v("1", "DAZN 1 UHD", measured = 25),
            v("2", "DAZN 1 FHD", measured = 50))))
    }

    @Test fun neverGuessesWhenMultipleFiftyFpsMatchesExist() {
        val options = listOf(v("1","DAZN 1 25FPS"), v("2","DAZN 1 50FPS"),
            v("3","DAZN 1 FHD 50FPS"))
        assertEquals(0, V185SportPriority.bestIndex(0, options))
    }

    @Test fun preservesUnknownAndDifferentContentNames() {
        assertEquals(0, V185SportPriority.bestIndex(0, listOf(
            v("1", "Sky Bundesliga 1"), v("2", "Sky Bundesliga 2 50FPS"))))
        assertEquals(0, V185SportPriority.bestIndex(0, listOf(
            v("1", "DAZN 1 UHD"), v("2", "DAZN 1 HD"))))
        assertEquals(0, V185SportPriority.bestIndex(0, listOf(
            v("1", "DAZN 1 UHD", profile = ""),
            v("2", "DAZN 1 50FPS", profile = ""))))
    }

    @Test fun daznSixTypicalQualityVariantsCollapseToOneChannel() {
        val variants = listOf(
            v("hdplus", "DAZN 1 HD+", measured = 25),
            v("4k", "DAZN 1 4K", measured = 25),
            v("fhd", "DAZN 1 Full HD", measured = 50),
            v("hd", "DAZN 1 HD", measured = 25),
            v("web", "DAZN 1 HD WEB", measured = 25),
            v("hevc", "DAZN 1 BHAEVC", measured = 25)
        )
        assertEquals(2, V185SportPriority.bestIndex(1, variants))
        assertEquals(2, V185SportPriority.bestIndex(4, variants))
        assertEquals(2, V185SportPriority.bestIndex(5, variants))
        assertEquals("DAZN 1", V185SportPriority.canonical("DAZN 1 HD+"))
        assertEquals("DAZN 1", V185SportPriority.canonical("DAZN 1 HD WEB"))
        assertEquals("DAZN 1", V185SportPriority.canonical("DAZN 1 BHAEVC"))
    }

    @Test fun noBlindFhdSelectionBeforePlaybackMeasurement() {
        // A filename alone does NOT establish that FHD has 50 distinct fps.
        val options = listOf(v("4k", "DAZN 1 4K", measured = 25),
            v("fhd", "DAZN 1 FHD"))
        assertEquals(0, V185SportPriority.bestIndex(0, options))
    }

    @Test fun similarLookingDifferentNumberedChannelsNeverMix() {
        assertEquals(0, V185SportPriority.bestIndex(0, listOf(
            v("1", "DAZN 1 HD", measured = 25),
            v("2", "DAZN 2 FHD", measured = 50))))
    }

    @Test fun classifiesOnlyReliableObservedFrames() {
        assertEquals(25, V185SportPriority.classify(25.0f))
        assertEquals(50, V185SportPriority.classify(49.99f))
        assertEquals(0, V185SportPriority.classify(24.0f))
        assertEquals(0, V185SportPriority.classify(-1.0f))
    }
}
