package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V188SportContextTest {
    private fun offer(
        name: String, category: String, programme: String = "", description: String = "",
        fps: Int = 25, known50: Boolean = true
    ) = V188SportContext.automaticOfferAllowed(
        name, category, programme, description, fps, known50
    )

    @Test fun generalFilmNewsAndEntertainmentDoNotAutoOfferSportMode() {
        assertFalse(offer("Sky Cinema 1 4K", "IT | FILM"))
        assertFalse(offer("RAI 1", "Generale"))
        assertFalse(offer("ARD HD", "DE | TV"))
        assertFalse(offer("BBC One HD", "UK | TV", "Tagesschau"))
        assertFalse(offer("Sky Cinema 4K", "FILM", "Film: Der große Sport"))
    }

    @Test fun explicitLiveSportEpgWorksEvenOnOrdinaryChannels() {
        assertTrue(offer("RAI 1", "IT | Generale", "Serie A: Juventus - Inter"))
        assertTrue(offer("ZDF HD", "DE Allgemein", "Fußball Bundesliga live"))
        assertTrue(offer("RTL", "TV", "Formel 1 Grand Prix"))
        assertTrue(offer("BBC One", "TV", "Wimbledon Tennis"))
        assertEquals(V188SportContext.Confidence.CONFIRMED,
            V188SportContext.confidence("RAI 1", "General", "UEFA Champions League", ""))
    }

    @Test fun genericSportsBrandCanOfferWithoutEpgButNotIfItIsShowingADocumentary() {
        assertTrue(offer("DAZN 1 4K", "IT"))
        assertTrue(offer("IT: Sky Calcio 1 UHD", "IT SPORT"))
        assertTrue(offer("EUROSPORT 1 FHD", "TV"))
        assertFalse(offer("Sky Calcio 1 UHD", "SPORT", "Documentario: le grandi storie del calcio"))
        assertFalse(offer("DAZN 1", "Sport", "Football Highlights"))
        assertFalse(offer("Sky Sport 1", "Sport", "Notizie Sport"))
    }

    @Test fun sportCategoryAloneIsInsufficient() {
        assertFalse(offer("RAI 1 4K", "SPORT"))
        assertTrue(offer("SPORT LIVE", "IT SPORT"))
        assertFalse(offer("MOVIE SPORTS", "FILM"))
    }

    @Test fun mustProveTwentyFiveFpsAndKnownFiftyFpsSibling() {
        assertFalse(offer("Sky Calcio 1", "IT Sport", fps = 50))
        assertFalse(offer("Sky Calcio 1", "IT Sport", fps = 0))
        assertFalse(offer("Sky Calcio 1", "IT Sport", known50 = false))
        assertFalse(offer("ZDF HD", "TV", "Fußball live", known50 = false))
        assertTrue(offer("ZDF HD", "TV", "Fußball live", fps = 25, known50 = true))
    }
}
