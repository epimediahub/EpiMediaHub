package de.epimediahub.app.data

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test

class V157RecentlyAddedTest {
    private fun film(id: String, added: Long) = MediaEntry(
        id = id, name = "Movie $id", kind = MediaKind.MOVIE,
        streamUrl = "https://example.org/$id.mp4", addedAt = added
    )

    @Test fun sortsProviderAddedTimestampsDescending() {
        val selected = V157RecentlyAdded.select(
            listOf(film("a", 10), film("b", 50), film("c", 30)), 2)
        assertEquals(listOf("b", "c"), selected.map { it.id })
    }

    @Test fun providerWithoutAddedFieldStillShowsRecentSection() {
        val selected = V157RecentlyAdded.select(
            listOf(film("a", 0), film("b", 0), film("c", 0)), 2)
        assertEquals(listOf("a", "b"), selected.map { it.id })
    }

    @Test fun honoursEmptyAndLimits() {
        assertTrue(V157RecentlyAdded.select(emptyList()).isEmpty())
        assertTrue(V157RecentlyAdded.select(listOf(film("x", 1)), 0).isEmpty())
    }
}
