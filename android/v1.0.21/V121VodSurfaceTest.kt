@file:OptIn(androidx.media3.common.util.UnstableApi::class)

package de.epimediahub.app.ui

import android.app.Activity
import android.view.SurfaceView
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.AspectRatioFrameLayout
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@LooperMode(LooperMode.Mode.PAUSED)
class V121VodSurfaceTest {
    @Test fun progressUpdatesAndEpisodeReplacementKeepTheSameSurfaceView() {
        val activity = Robolectric.buildActivity(Activity::class.java).setup().get()
        val first = ExoPlayer.Builder(activity).build()
        val second = ExoPlayer.Builder(activity).build()
        val view = V121VideoView(activity)
        try {
            view.bind(first, true)
            val surface = view.videoSurfaceView
            assertTrue(surface is SurfaceView)
            repeat(100) { view.bind(first, true) }
            assertSame(surface, view.videoSurfaceView)
            assertSame(first, view.player)
            view.bind(second, true)
            assertSame(surface, view.videoSurfaceView)
            assertSame(second, view.player)
            assertEquals(AspectRatioFrameLayout.RESIZE_MODE_FIT, view.resizeMode)
            view.close()
            assertNull(view.player)
        } finally {
            view.close(); first.release(); second.release(); activity.finish()
        }
    }
}
