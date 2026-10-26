package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V186SportPriorityTest {
    private fun v(id: String, name: String, profile: String = "the-best", fps: Int = 0) =
        V186SportPriority.Variant(id, name, profile, fps)

    @Test fun daznSixVersionsPrefersLearnedFullHdOver25Fps4k() {
        val list = listOf(
            v("hdplus", "DE: DAZN 1 HD+", fps = 25),
            v("4k", "DE: DAZN 1 4K", fps = 25),
            v("fhd", "DE: DAZN 1 Full HD", fps = 50),
            v("hd", "DE: DAZN 1 HD", fps = 25),
            v("web", "DE: DAZN 1 HD WEB", fps = 25),
            v("hevc", "DE: DAZN 1 BHAEVC", fps = 25)
        )
        assertEquals(2, V186SportPriority.bestIndex(1, list))
        assertEquals(2, V186SportPriority.bestIndex(0, list))
        assertEquals(2, V186SportPriority.bestIndex(3, list))
        assertEquals(2, V186SportPriority.bestIndex(4, list))
        assertEquals(2, V186SportPriority.bestIndex(5, list))
        assertEquals(2, V186SportPriority.bestIndex(2, list))
    }

    @Test fun twoVerified50FpsCandidatesNoLongerBlockAutomaticSwitch() {
        val list = listOf(
            v("4k", "DAZN 1 4K", fps = 25),
            v("hd", "DAZN 1 HD+", fps = 50),
            v("fhd", "DAZN 1 Full HD", fps = 50),
            v("web", "DAZN 1 WEB", fps = 25)
        )
        assertEquals(2, V186SportPriority.bestIndex(0, list))
    }

    @Test fun highestQualityActually50WinsEvenIf4k25() {
        assertEquals(1, V186SportPriority.bestIndex(0, listOf(
            v("4k", "DAZN 1 UHD", fps = 25),
            v("fhd", "DAZN 1 FHD", fps = 50),
            v("hd", "DAZN 1 HD", fps = 50)
        )))
        assertEquals(2, V186SportPriority.bestIndex(0, listOf(
            v("sd", "DAZN 1 SD", fps = 25),
            v("fhd", "DAZN 1 FHD", fps = 50),
            v("uhd", "DAZN 1 4K", fps = 50)
        )))
    }

    @Test fun measurementWinsOverUnverified50Label() {
        assertEquals(2, V186SportPriority.bestIndex(0, listOf(
            v("4k", "DAZN 1 4K", fps = 25),
            v("50label", "DAZN 1 4K 50 FPS"),
            v("fhd", "DAZN 1 FHD", fps = 50)
        )))
        assertEquals(0, V186SportPriority.bestIndex(0, listOf(
            v("4k", "DAZN 1 4K 50 FPS", fps = 50),
            v("fhd", "DAZN 1 FHD 50 FPS", fps = 25)
        )))
    }

    @Test fun noGuessFromResolutionUntilFpsKnown() {
        assertEquals(0, V186SportPriority.bestIndex(0, listOf(
            v("4k", "DAZN 1 4K", fps = 25),
            v("fhd", "DAZN 1 FHD")
        )))
    }

    @Test fun neverMixesProvidersChannelsRegionsLanguages() {
        assertEquals(0, V186SportPriority.bestIndex(0, listOf(
            v("a", "DAZN 1 DE 4K", "provider1", 25),
            v("b", "DAZN 1 DE FHD", "provider2", 50)
        )))
        assertEquals(0, V186SportPriority.bestIndex(0, listOf(
            v("a", "DAZN 1 DE HD", fps = 25),
            v("b", "DAZN 1 IT FHD", fps = 50)
        )))
        assertEquals(0, V186SportPriority.bestIndex(0, listOf(
            v("a", "DAZN 1 HD", fps = 25),
            v("b", "DAZN 2 FHD", fps = 50)
        )))
        assertEquals(0, V186SportPriority.bestIndex(0, listOf(
            v("a", "Sky Bundesliga 1 4K", fps = 25),
            v("b", "Sky Bundesliga 2 FHD", fps = 50)
        )))
    }

    @Test fun canonicalHandlesQualityAndCodecButNotChannelIdentity() {
        assertEquals("DE DAZN 1", V186SportPriority.canonical("DE: DAZN 1 HD WEB"))
        assertEquals("DE DAZN 1", V186SportPriority.canonical("DE: DAZN 1 Full HD"))
        assertEquals("DE DAZN 1", V186SportPriority.canonical("DE: DAZN 1 BHAEVC"))
        assertEquals("DE DAZN 1", V186SportPriority.canonical("DE: DAZN 1 4K"))
        assertNotEquals(V186SportPriority.canonical("DAZN 1 FHD"),
            V186SportPriority.canonical("DAZN 2 FHD"))
    }

    @Test fun ptsWinsOverMisleadingMetadataAndFormatCanFallback() {
        assertEquals(25, V186SportPriority.observedRate(25f, 50f, 50f))
        assertEquals(50, V186SportPriority.observedRate(50f, 25f, 25f))
        assertEquals(50, V186SportPriority.observedRate(0f, 50f, -1f))
        assertEquals(50, V186SportPriority.observedRate(0f, -1f, 50f))
        assertEquals(0, V186SportPriority.observedRate(0f, -1f, 0f))
    }
}
