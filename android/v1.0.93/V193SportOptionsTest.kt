package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test

class V193SportOptionsTest {
    private fun live(id: String, name: String, profile: String = "best", category: String = "sport") =
        MediaEntry(id, name, MediaKind.LIVE, categoryId = category, sourceProfileId = profile)

    private val selected = live("4k", "DE: DB LIGA 1 4K", category = "uhd")
    private val fullHd = live("fhd", "DE: SKY SPORT BUNDESLIGA 1 FHD", category = "fhd")
    private val web = live("web", "DE: SKY SPORT BUNDESLIGA 1 HD WEB", category = "web")
    private val unrelated = live("other", "DE: DAZN 2 FHD", category = "fhd")
    private val providerOther = live("different", "DE: SKY SPORT BUNDESLIGA 1 FHD", "other")

    private fun fps(known: Map<String, Int>) =
        { _: String, _: String, id: String -> known[id] ?: 0 }

    @Test fun unverifiedAlternativeIsOfferedAsCandidateNotVerified() {
        val rows = listOf(selected, fullHd, web)
        assertEquals(V193SportOptions.Tier.UNVERIFIED,
            V193SportOptions.tier(selected, rows, "best", fps(mapOf("4k" to 25))))
        assertEquals(listOf("fhd", "web"),
            V193SportOptions.candidates(selected, rows, "best", fps(mapOf("4k" to 25))).map { it.id })
    }

    @Test fun measured50TakesPriorityAndMeasured25IsExcluded() {
        val rows = listOf(selected, fullHd, web)
        val known = mapOf("4k" to 25, "fhd" to 25, "web" to 50)
        assertEquals(V193SportOptions.Tier.VERIFIED_50,
            V193SportOptions.tier(selected, rows, "best", fps(known)))
        assertEquals(listOf("web"),
            V193SportOptions.candidates(selected, rows, "best", fps(known)).map { it.id })
    }

    @Test fun sameProviderAndSameCanonicalStationOnly() {
        val rows = listOf(selected, unrelated, providerOther, fullHd)
        assertEquals(listOf("fhd"),
            V193SportOptions.candidates(selected, rows, "best", fps(emptyMap())).map { it.id })
        assertEquals(V193SportOptions.Tier.NONE,
            V193SportOptions.tier(selected, listOf(selected, unrelated, providerOther),
                "best", fps(emptyMap())))
    }

    @Test fun neverAutoPromptForFilmsOrUnmeasuredCurrentRate() {
        assertTrue(V193SportOptions.automaticOfferAllowed(
            "DE: SKY SPORT BUNDESLIGA 1 4K", "Sport", "", "", 25,
            V193SportOptions.Tier.UNVERIFIED))
        assertFalse(V193SportOptions.automaticOfferAllowed(
            "DE: SKY SPORT BUNDESLIGA 1 4K", "Sport", "", "", 0,
            V193SportOptions.Tier.VERIFIED_50))
        assertFalse(V193SportOptions.automaticOfferAllowed(
            "Sky Cinema 4K", "Film", "", "", 25,
            V193SportOptions.Tier.UNVERIFIED))
        assertFalse(V193SportOptions.automaticOfferAllowed(
            "DAZN 1 4K", "Sport", "Football Highlights", "", 25,
            V193SportOptions.Tier.UNVERIFIED))
    }

    @Test fun cannotInventOptionsWithoutMatchingKnownCategoryEntries() {
        assertEquals(V193SportOptions.Tier.NONE,
            V193SportOptions.tier(selected, listOf(selected), "best", fps(emptyMap())))
        assertTrue(V193SportOptions.candidates(selected, listOf(selected),
            "best", fps(emptyMap())).isEmpty())
    }
}
