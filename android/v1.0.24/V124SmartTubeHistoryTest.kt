package de.epimediahub.app.ui

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import org.json.JSONArray
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V124SmartTubeHistoryTest {
    @Test fun remoteWatchedIdsPersistWithoutLeakingToAnotherAccount() {
        val context=ApplicationProvider.getApplicationContext<Context>()
        val account="v124-history-test"
        assertTrue(V112SmartTubeWatchHistory.mergeWatched(context,account,setOf("one","two","")))
        assertEquals(setOf("one","two"),V112SmartTubeWatchHistory.watched(context,account))
        assertFalse(V112SmartTubeWatchHistory.mergeWatched(context,account,setOf("one")))
        assertTrue(V112SmartTubeWatchHistory.watched(context,"v124-other-account").isEmpty())
        val saved=JSONArray(context.getSharedPreferences("smarttube_watched_v112",Context.MODE_PRIVATE).getString(account,"[]"))
        assertEquals(2,saved.length())
    }
}
