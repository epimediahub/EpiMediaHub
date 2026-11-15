package de.epimediahub.app.data

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test

class V158RecentlyAddedTest {
    private fun film(id: String, added: Long) = MediaEntry(
        id = id, name = "Movie $id", kind = MediaKind.MOVIE,
        streamUrl = "https://example.org/$id.mp4", addedAt = added
    )

    @Test fun onlyGenuineProviderDatesAppear() {
        val items = listOf(film("old", 0L), film("new", 90L), film("invalid", -1L), film("newer", 120L))
        assertEquals(listOf("newer", "new"), V158RecentlyAdded.select(items).map { it.id })
    }

    @Test fun undatedProviderDoesNotInventNewMovies() {
        assertTrue(V158RecentlyAdded.select(listOf(film("old1", 0), film("old2", 0))).isEmpty())
    }

    @Test fun limitAndEmptyAreRespected() {
        assertEquals(listOf("b"), V158RecentlyAdded.select(listOf(film("a", 1), film("b", 2)), 1).map { it.id })
        assertTrue(V158RecentlyAdded.select(listOf(film("b", 2)), 0).isEmpty())
        assertTrue(V158RecentlyAdded.select(emptyList()).isEmpty())
    }
}
