package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test

class V188SportCatalogTest {
    private fun live(id: String, title: String, profile: String = "the-best", category: String = "main") =
        MediaEntry(id, title, MediaKind.LIVE, categoryId = category, sourceProfileId = profile)

    @Test fun italianSkyCalcioCanUseKnown50FromAnotherCategory() {
        val current = live("4k", "IT: SKY CALCIO 1 UHD", category = "sport-4k")
        val fullHd = live("fhd", "IT: SKY CALCIO 1 FHD", category = "sport-fhd")
        val hevc = live("hevc", "IT: SKY CALCIO 1 HEVC", category = "sport-other")
        val categoryRows = mapOf(
            "sport-4k" to listOf(current),
            "sport-fhd" to listOf(fullHd),
            "sport-other" to listOf(hevc)
        )
        val candidates = V188SportCatalog.samePlaylist(current, listOf(current), categoryRows, "the-best")
        assertEquals(3, candidates.size)
        val fps = mapOf("4k" to 25, "fhd" to 50, "hevc" to 25)
        val alt = V187SportMode.alternatives(current, candidates, "the-best") { _, id -> fps[id] ?: 0 }
        assertEquals(listOf("fhd"), alt.map { it.id })
    }

    @Test fun multipleCrossCategoryVariantsAreRankedWithoutDuplicates() {
        val current = live("4k", "DAZN 1 4K", category = "uhd")
        val fhd = live("fhd", "DAZN 1 FHD", category = "fhd")
        val hd = live("hd", "DAZN 1 HD", category = "hd")
        val catalog = mapOf(
            "uhd" to listOf(current),
            "fhd" to listOf(fhd),
            "hd" to listOf(hd),
            "__all__" to listOf(current, fhd, hd)
        )
        val merged = V188SportCatalog.samePlaylist(current, listOf(current), catalog, "the-best")
        assertEquals(listOf("4k","fhd","hd"), merged.map { it.id })
        val fps = mapOf("4k" to 25, "fhd" to 50, "hd" to 50)
        val alt = V187SportMode.alternatives(current, merged, "the-best") { _, id -> fps[id] ?: 0 }
        assertEquals(listOf("fhd","hd"), alt.map { it.id })
    }

    @Test fun neverCrossesProviderOrConflatesNumberedAndLanguageChannels() {
        val current = live("it4k", "IT: SKY CALCIO 1 4K", profile = "italia", category = "4k")
        val otherProvider = live("other", "IT: SKY CALCIO 1 FHD", profile = "germany", category = "fhd")
        val differentChannel = live("two", "IT: SKY CALCIO 2 FHD", profile = "italia", category = "fhd")
        val germanChannel = live("de", "DE: SKY CALCIO 1 FHD", profile = "italia", category = "fhd")
        val merged = V188SportCatalog.samePlaylist(current, listOf(current),
            mapOf("4k" to listOf(current),"fhd" to listOf(otherProvider,differentChannel,germanChannel)), "italia")
        assertFalse(merged.any { it.id == "other" })
        assertTrue(merged.any { it.id == "two" })
        assertTrue(merged.any { it.id == "de" })
        val alt = V187SportMode.alternatives(current, merged, "italia") { _, id ->
            if (id == "two" || id == "de") 50 else 25
        }
        assertTrue(alt.isEmpty())
    }

    @Test fun unknownRateCanBeLearnedOnlyWhenUserAcceptsSportMode() {
        val current = live("4k", "DAZN 1 UHD")
        val unknown = live("fhd", "DAZN 1 FULL HD",category="fhd")
        val merged = V188SportCatalog.samePlaylist(current, listOf(current),
            mapOf("4k" to listOf(current), "fhd" to listOf(unknown)), "the-best")
        val alt = V187SportMode.alternatives(current, merged, "the-best") { _, id ->
            if (id == "4k") 25 else 0
        }
        assertEquals(listOf("fhd"), alt.map { it.id })
        val ruledOut = V187SportMode.alternatives(current, merged, "the-best") { _, _ -> 25 }
        assertTrue(ruledOut.isEmpty())
    }
}
