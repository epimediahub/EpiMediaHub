package de.epimediahub.app.ui

import android.content.Context
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V129KidsPolicyTest {
    private fun video(id: String, live: Boolean = false) = V100SmartTubeVideo(id, "Kinderfilm", "", "", "", 120000, live)
    @Test fun onlyReturnedKidsVideoIdsAreAllowedInPlayerAndSuggestions() {
        val returned = video("aaaaaaaaaaa")
        val catalogue = V129KidsCatalogue(listOf(V100SmartTubeRow("Lernen", listOf(returned, returned, video("bbbbbbbbbbb", true), video("invalid")))))
        assertEquals(listOf(returned), catalogue.videos)
        assertTrue(catalogue.allows(returned))
        assertFalse(catalogue.allows(video("ccccccccccc")))
        assertFalse(catalogue.allows(returned.copy(live = true)))
        assertFalse(V129KidsCatalogue(emptyList()).allows(returned))
    }
    @Test fun kidsModePersistsAcrossProcessRecreationAndOnlyExplicitExitClearsIt() {
        val app = RuntimeEnvironment.getApplication()
        app.getSharedPreferences("epi_smarttube_kids_v129", Context.MODE_PRIVATE).edit().clear().commit()
        val first = V129KidsStore(app)
        assertFalse(first.active())
        first.enter()
        assertTrue(V129KidsStore(app).active())
        V129KidsStore(app).leave()
        assertFalse(first.active())
    }
}
