package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V188WorldwideSportChannelsTest {
    @Test fun detectsConfirmedSportNetworksAcrossContinents() {
        val worldwide = listOf(
            "DE: SKY SPORT BUNDESLIGA 1 UHD 25 FPS",
            "DE: DB LIGA 1 FULL HD HEVC",
            "DE | DAZN 2 FHD 50FPS",
            "IT: SKY SPORT CALCIO 4K",
            "IT: SUPERTENNIS HD",
            "UK: SKY SPORTS MAIN EVENT UHD",
            "UK: TNT SPORTS 3",
            "PT: SPORT TV 3 FHD",
            "ES: LALIGA TV HYPERMOTION 2",
            "ES | M LIGA DE CAMPEONES 2 FHD",
            "FR: RMC SPORT 1",
            "NL: ZIGGO SPORT RACING",
            "RO: DIGI SPORT 4 HD",
            "RO: PRIMA SPORT 1 HEVC",
            "PL: POLSAT SPORT PREMIUM 2",
            "RS: ARENA SPORT 1",
            "HR | SPORTKLUB 1 HD",
            "GR: COSMOTE SPORT 3",
            "TR: TRT SPOR YILDIZ",
            "TR: TIVIBU SPOR 4",
            "MENA: BEIN SPORTS XTRA 2",
            "SA: SSC 1 UHD",
            "AE: ABU DHABI SPORTS 2",
            "AE: DUBAI SPORTS 1",
            "MA: ARRYADIA",
            "EG: ON TIME SPORTS 1",
            "ZA: SUPERSPORT PREMIER LEAGUE HD",
            "ZA: SS GRANDSTAND",
            "TZ: AZAM SPORTS 2",
            "IN: STAR SPORTS 1",
            "IN: SONY SPORTS TEN 2",
            "PK: PTV SPORTS",
            "IN: SPORTS18 1",
            "MY: ASTRO PREMIER LEAGUE 1",
            "MY: ASTRO ARENA 2",
            "JP: J SPORTS 3",
            "JP: GAORA SPORTS",
            "CN: CCTV5+",
            "KR: SBS SPORTS",
            "PH: ONE SPORTS",
            "TH: TRUE PREMIER FOOTBALL 2",
            "US: ESPN2",
            "US: FOX SPORTS 1",
            "US: CBS SPORTS NETWORK",
            "US: NFL NETWORK",
            "US: NBA TV",
            "US: WILLOW CRICKET",
            "CA: TSN 4",
            "CA: RDS2",
            "BR: SPORTV 2 HD",
            "BR: PREMIERE FC 3",
            "AR: TYC SPORTS 1",
            "AR: TNT SPORTS",
            "CO: WIN SPORTS 2",
            "MX: TUDN 1",
            "LATAM: DIRECTV SPORTS 2",
            "AU: FOX FOOTY",
            "AU: FOX LEAGUE",
            "AU: FOX CRICKET",
            "NZ: SKY SPORT 4"
        )
        worldwide.forEach {
            assertTrue("Missed worldwide sports channel: " + it,
                V188WorldwideSportChannels.isKnownSport(it))
        }
        assertTrue(V188WorldwideSportChannels.families.size >= 110)
    }

    @Test fun protectsMoviesNewsAndOrdinaryStationsFromFalseSportMatches() {
        val nonSport = listOf(
            "DE: SKY CINEMA BUNDESLIGA DOKU HD", "UK: SKY NEWS",
            "UK: SKY ATLANTIC HD", "IT: SKY CINEMA UNO FHD",
            "ES: MOVISTAR SERIES", "ES: DAZN MOVIES", "UK: BEIN MOVIES 1",
            "US: FOX NEWS", "US: CBS HD", "US: NBC",
            "DE: RTL HD", "DE: ARD", "DE: ZDF UHD", "IT: RAI 1",
            "ES: LALIGA DOCU CHANNEL", "IN: STAR MOVIES",
            "US: ESPN KIDS", "BR: GLOBO NEWS",
            "AU: FOX CLASSICS", "DE: DB KULTUR"
        )
        nonSport.forEach { name ->
            assertFalse("False sport family: " + name,
                V188WorldwideSportChannels.isKnownSport(name))
        }
    }

    @Test fun qualitySuffixesAndIPTVPrefixAreIgnoredForSportFamily() {
        assertEquals("SKY SPORT BUNDESLIGA 1",
            V188WorldwideSportChannels.clean("DE: SKY SPORT BUNDESLIGA 1 FHD WEB BHAEVC 50 FPS"))
        assertEquals("DAZN 1",
            V188WorldwideSportChannels.clean("IT | DAZN 1 HEVC UHD 25FPS"))
        assertEquals("SKY SPORT CALCIO",
            V188WorldwideSportChannels.clean("IT: SKY SPORT CALCIO 4K HEVC"))
    }

    @Test fun maskedDbLigaAndOfficialBundesligaMatchSameNumberButNotOther() {
        assertEquals(
            V188WorldwideSportChannels.canonicalSportIdentity("DE: SKY SPORT BUNDESLIGA 1 UHD"),
            V188WorldwideSportChannels.canonicalSportIdentity("DE: DB LIGA 1 FHD"))
        assertNotEquals(
            V188WorldwideSportChannels.canonicalSportIdentity("DE: SKY SPORT BUNDESLIGA 1"),
            V188WorldwideSportChannels.canonicalSportIdentity("DE: DB LIGA 2"))
        assertNotEquals(
            V188WorldwideSportChannels.canonicalSportIdentity("DE: DB LIGA 1"),
            V188WorldwideSportChannels.canonicalSportIdentity("IT: DB LIGA 1"))
    }

    @Test fun sportIdentityNeverConflatesDifferentNumberedOrLanguageChannels() {
        assertNotEquals(
            V188WorldwideSportChannels.canonicalSportIdentity("IT: SKY CALCIO 1"),
            V188WorldwideSportChannels.canonicalSportIdentity("IT: SKY CALCIO 2"))
        assertEquals(
            V188WorldwideSportChannels.canonicalSportIdentity("IT: SKY SPORT CALCIO 1 UHD"),
            V188WorldwideSportChannels.canonicalSportIdentity("IT: SKY CALCIO 1 FHD"))
        assertNotEquals(
            V188WorldwideSportChannels.canonicalSportIdentity("IT: DAZN 1 UHD"),
            V188WorldwideSportChannels.canonicalSportIdentity("DE: DAZN 1 FHD"))
    }

    @Test fun sportsClassifierCanWorkWithoutEpgButStillRequiresVerifiedAlternate() {
        assertEquals(V188SportContext.Confidence.PROBABLE,
            V188SportContext.confidence("DE: DB LIGA 1 UHD", "DE TV", "", ""))
        assertEquals(V188SportContext.Confidence.PROBABLE,
            V188SportContext.confidence("IT: SKY SPORT CALCIO 1", "IT", "", ""))
        assertFalse(V188SportContext.automaticOfferAllowed(
            "DE: DB LIGA 1 UHD", "TV", "", "", 25, false))
        assertTrue(V188SportContext.automaticOfferAllowed(
            "DE: DB LIGA 1 UHD", "TV", "", "", 25, true))
    }

    @Test fun maskedDbLigaCanFindKnown50InOtherCategory() {
        val current = V187SportMode.Candidate("orig", "DE: DB LIGA 1 4K", "provider", 25)
        val alt = V187SportMode.Candidate("fhd", "DE: SKY SPORT BUNDESLIGA 1 FHD", "provider", 50)
        val otherNumber = V187SportMode.Candidate("other", "DE: SKY SPORT BUNDESLIGA 2 FHD", "provider", 50)
        assertEquals(listOf(1),V187SportMode.rankedIndices(0,listOf(current,alt,otherNumber)))
    }
}
