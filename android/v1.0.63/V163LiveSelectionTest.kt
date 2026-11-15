package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test

class V163LiveSelectionTest {
    private fun channel(id: String, category: String = "sport", profile: String = "a") =
        MediaEntry(id, "Sender $id", MediaKind.LIVE, categoryId = category, sourceProfileId = profile)

    @Test fun allChannelsCategoryIsPreservedAndZappedChannelBecomesSelected() {
        val channels = listOf(channel("1"), channel("2"), channel("3"))
        val selected = V163LiveSelection.resolve(channels[2], "__all__",
            mapOf("sport" to channels, "__all__" to listOf(channel("0", "news")) + channels), channels)
        assertEquals("__all__", selected.categoryId)
        assertEquals(3, selected.index)
    }

    @Test fun searchAndFavoritesReturnToActualCategoryInsteadOfUnrelatedRememberedList() {
        val sports = listOf(channel("1"), channel("2"))
        val news = listOf(channel("2", "news", "other"))
        val selected = V163LiveSelection.resolve(sports[1], "news", mapOf("news" to news, "sport" to sports), listOf(sports[1]))
        assertEquals("sport", selected.categoryId)
        assertEquals(1, selected.index)
    }
}
