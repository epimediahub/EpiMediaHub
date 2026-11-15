@file:OptIn(androidx.media3.common.util.UnstableApi::class)

package de.epimediahub.app.ui

import android.content.Context
import androidx.media3.exoplayer.DefaultRenderersFactory

/** One ExoPlayer clock and network connection for video plus decoded PCM audio.
 * Only the FFmpeg AUDIO extension is packaged. There is no software video renderer,
 * so the proven MediaCodec video path and its frame-rate/surface policy stay intact.
 * Prefer PCM decoding for supported, unencrypted audio to also avoid false HDMI
 * passthrough support; Android handles audio outside the extension's capabilities.
 */
internal class V123AudioRenderers(context: Context) : DefaultRenderersFactory(context) {
    init {
        setEnableDecoderFallback(true)
        setExtensionRendererMode(EXTENSION_RENDERER_MODE_PREFER)
    }
}
