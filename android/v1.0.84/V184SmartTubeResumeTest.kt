package de.epimediahub.app.ui

import androidx.test.core.app.ApplicationProvider
import android.content.Context
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class V184SmartTubeResumeTest {
    private val context: Context get() = ApplicationProvider.getApplicationContext()
    @Test fun progressResumesPerAccountAndVideoAndSurvivesAnotherRead() {
        V184SmartTubeResume.clear(context, "guest", "video-a")
        V184SmartTubeResume.clear(context, "user-1", "video-a")
        V184SmartTubeResume.save(context, "guest", "video-a", 96_000L, 600_000L)
        assertEquals(96_000L, V184SmartTubeResume.read(context, "guest", "video-a"))
        assertEquals(0L, V184SmartTubeResume.read(context, "user-1", "video-a"))
        assertEquals(0L, V184SmartTubeResume.read(context, "guest", "video-b"))
    }
    @Test fun completedVideoDoesNotResumeInCredits() {
        V184SmartTubeResume.save(context, "guest", "finished", 80_000L, 120_000L)
        V184SmartTubeResume.save(context, "guest", "finished", 109_000L, 120_000L)
        assertEquals(0L, V184SmartTubeResume.read(context, "guest", "finished"))
        V184SmartTubeResume.save(context, "guest", "finished", 70_000L, 120_000L)
        V184SmartTubeResume.clear(context, "guest", "finished")
        assertEquals(0L, V184SmartTubeResume.read(context, "guest", "finished"))
    }
    @Test fun heldRemoteRepeatsUseThirtySecondSteps() {
        assertEquals(-10_000L, V184SmartTubeSeekPolicy.deltaMs(-1, 0))
        assertEquals(10_000L, V184SmartTubeSeekPolicy.deltaMs(1, 0))
        assertEquals(-30_000L, V184SmartTubeSeekPolicy.deltaMs(-1, 1))
        assertEquals(30_000L, V184SmartTubeSeekPolicy.deltaMs(1, 7))
    }
}
