package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test

class V191SportIndexTest {
    private fun live(id: String, name: String, profile: String = "best", category: String = "live") =
        MediaEntry(id, name, MediaKind.LIVE, categoryId = category, sourceProfileId = profile)

    @Test fun crossCategoryOnlySameStreamIdentityAndProvider() {
        val selected = live("1", "IT: SKY CALCIO 1 UHD")
        val fhd = live("2", "IT: SKY CALCIO 1 FHD", category = "fhd")
        val other = live("3", "IT: SKY CALCIO 2 FHD")
        val fromDifferentProvider = live("4", "IT: SKY CALCIO 1 HD", profile = "other")
        val rows = mapOf(
            "uhd" to listOf(selected),
            "fhd" to listOf(fhd, other, fromDifferentProvider),
            "__all__" to listOf(selected, fhd))
        val index = V191SportIndex.build("best", rows)
        assertEquals(listOf("1", "2"), index.groupFor(selected).map { it.id })
        assertEquals(listOf("4"), index.groupFor(fromDifferentProvider).map { it.id })
        assertEquals(listOf("3"), index.groupFor(other).map { it.id })
    }

    @Test fun noNetworkOrUnknownGuessingAndNonPlayableHeaderExcluded() {
        val chosen = live("a", "DE: DB LIGA 1 4K")
        val header = live("separator", "--- SKY SPORT ---")
        val alt = live("b", "DE: SKY SPORT BUNDESLIGA 1 FHD", category = "sport")
        val index = V191SportIndex.build("best", mapOf("a" to listOf(chosen, header),
            "b" to listOf(alt)))
        assertEquals(listOf("a", "b"), index.groupFor(chosen).map { it.id })
        assertEquals(listOf("separator"), index.groupFor(header).map { it.id })
    }
}
