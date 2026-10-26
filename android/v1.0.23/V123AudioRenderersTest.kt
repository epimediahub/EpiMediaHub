@file:OptIn(androidx.media3.common.util.UnstableApi::class)

package de.epimediahub.app.ui

import android.content.Context
import androidx.media3.common.C
import androidx.media3.exoplayer.ExoPlayer
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [30])
class V123AudioRenderersTest {
    @Test fun softwareAudioIsPreferredWithoutReplacingHardwareVideo() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val player = ExoPlayer.Builder(context, V123AudioRenderers(context)).build()
        try {
            val video = (0 until player.rendererCount).filter { player.getRendererType(it) == C.TRACK_TYPE_VIDEO }
                .map { player.getRenderer(it).javaClass.name }
            val audio = (0 until player.rendererCount).filter { player.getRendererType(it) == C.TRACK_TYPE_AUDIO }
                .map { player.getRenderer(it).javaClass.name }
            assertEquals(listOf("androidx.media3.exoplayer.video.MediaCodecVideoRenderer"), video)
            assertEquals("androidx.media3.decoder.ffmpeg.FfmpegAudioRenderer", audio.first())
            assertTrue(audio.contains("androidx.media3.exoplayer.audio.MediaCodecAudioRenderer"))
        } finally { player.release() }
    }
}
