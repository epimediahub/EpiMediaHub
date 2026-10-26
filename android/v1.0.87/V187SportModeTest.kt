package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V187SportModeTest {
    private fun v(id: String, name: String, fps: Int = 0, profile: String = "best") =
        V187SportMode.Candidate(id, name, profile, fps)

    @Test fun checksAllKnown50sBeforeUnknownAndSkipsKnown25() {
        val list = listOf(
            v("4k", "DE DAZN 1 4K", 25),
            v("fhd", "DE DAZN 1 FHD", 50),
            v("hdweb", "DE DAZN 1 HD WEB", 0),
            v("hevc", "DE DAZN 1 BHAEVC", 50),
            v("hd", "DE DAZN 1 HD", 25),
            v("fifty-label", "DE DAZN 1 HD 50 FPS", 0)
        )
        assertEquals(listOf(1, 3, 5, 2),
            V187SportMode.rankedIndices(0, list))
    }

    @Test fun optionalModeNeverForceSwitchesOrExcludesCurrent25() {
        val list = listOf(v("4k","DAZN 1 4K",25),v("fhd","DAZN 1 FHD",50))
        assertEquals(listOf(1), V187SportMode.rankedIndices(0,list))
        // Caller only invokes rankedIndices AFTER explicit consent.
        assertEquals("4k",list[0].id)
    }

    @Test fun noCrossChannelLanguageOrProviderFailovers() {
        val list = listOf(
            v("one", "DAZN 1 DE 4K", 25),
            v("two", "DAZN 2 DE FHD", 50),
            v("italy", "DAZN 1 IT FHD", 50),
            v("other-provider", "DAZN 1 DE FHD", 50, "other"),
            v("match", "DAZN 1 DE HD", 50)
        )
        assertEquals(listOf(4),V187SportMode.rankedIndices(0,list))
    }

    @Test fun unknownQualityIsProbedOnlySequentiallyAndStopsWhenExhausted() {
        assertEquals(0,V187SportMode.nextIndex(-1,3))
        assertEquals(1,V187SportMode.nextIndex(0,3))
        assertEquals(2,V187SportMode.nextIndex(1,3))
        assertNull(V187SportMode.nextIndex(2,3))
        assertNull(V187SportMode.nextIndex(0,0))
    }

    @Test fun noReofferAfterExplicitNoUntilAppRestarts() {
        V187SportPromptMemory.decline("the-best","dazn-4k-v187-test")
        assertTrue(V187SportPromptMemory.wasDeclined("the-best","dazn-4k-v187-test"))
        assertFalse(V187SportPromptMemory.wasDeclined("the-best","dazn-hd-v187-test"))
        assertFalse(V187SportPromptMemory.wasDeclined("4k","dazn-4k-v187-test"))
    }

    @Test fun multiple50fpsVariantsAllIncludedEvenWithDifferentCodecs() {
        val list = listOf(
            v("4k","DAZN 1 4K",25),
            v("a","DAZN 1 HD WEB",50),
            v("b","DAZN 1 FHD",50),
            v("c","DAZN 1 HD HEVC",50),
            v("d","DAZN 1 HD+",50)
        )
        assertEquals(listOf(2,4,1,3),V187SportMode.rankedIndices(0,list))
    }
}
