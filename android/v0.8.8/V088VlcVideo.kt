package de.epimediahub.app.ui

import android.net.Uri
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.key
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import org.videolan.libvlc.LibVLC
import org.videolan.libvlc.Media
import org.videolan.libvlc.MediaPlayer
import org.videolan.libvlc.util.VLCVideoLayout

/** One native session per stream request. Both the surface and owner are replaced together. */
@Composable
internal fun V088VlcVideo(
    url: String,
    userAgent: String,
    referer: String,
    modifier: Modifier = Modifier,
    onError: (String) -> Unit
) {
    key(url, userAgent, referer) {
        val context = LocalContext.current
        val reportError = rememberUpdatedState(onError)
        val libVlc = remember {
            LibVLC(context, arrayListOf(
                "--network-caching=1800",
                // Keep audio in the packaged software decoders. Enabling hardware
                // VIDEO must not send MP2/AC3/etc. back to Android audio decoders.
                "--no-mediacodec-audio",
                "--audio-replay-gain-mode=none"
                // Use VLC's normal clock/jitter correction for network streams.
            ))
        }
        val player = remember(libVlc) { MediaPlayer(libVlc) }

        AndroidView(
            factory = { viewContext ->
                VLCVideoLayout(viewContext).also { layout ->
                    // Attach before play; LibVLC waits for the SurfaceView to be ready.
                    player.attachViews(layout, null, false, false)
                }
            },
            modifier = modifier
        )

        DisposableEffect(player) {
            val handler = Handler(Looper.getMainLooper())
            var closed = false
            fun error(message: String) {
                handler.post { if (!closed) reportError.value(message) }
            }
            player.setEventListener { event ->
                if (event.type == MediaPlayer.Event.EncounteredError) {
                    error("Live-Stream konnte nicht wiedergegeben werden. Mit der Menü-Taste zum Standardplayer wechseln.")
                }
            }
            reportError.value("")
            runCatching {
                check(url.isNotBlank()) { "Leere Stream-Adresse" }
                // Keep LibVLC's device-selected audio output. It specifically uses
                // OpenSL ES on Fire OS to avoid AudioTrack playback-clock issues.
                // Digital output is disabled by default in this MediaPlayer.
                val media = Media(libVlc, Uri.parse(url))
                try {
                    media.addOption(":network-caching=1800")
                    media.setHWDecoderEnabled(true, false)
                    // VLC's own decoding-only mode: hardware video decoding with
                    // a normal display path, avoiding fragile opaque/direct surfaces.
                    media.addOption(":no-mediacodec-dr")
                    media.addOption(":no-mediacodec-audio")
                    media.addOption(":http-user-agent=" + userAgent.ifBlank { "VLC/3.0.21 LibVLC/3.0.21" })
                    if (referer.isNotBlank()) media.addOption(":http-referrer=" + referer)
                    player.media = media
                } finally {
                    media.release()
                }
                player.play()
            }.onFailure {
                error("Kompatibilitätsplayer konnte den Live-Stream nicht starten.")
            }

            onDispose {
                closed = true
                handler.removeCallbacksAndMessages(null)
                player.setEventListener(null)
                // Exactly one release path, including a stream change or MENU switch.
                runCatching { player.stop() }
                runCatching { player.detachViews() }
                runCatching { player.release() }
                runCatching { libVlc.release() }
            }
        }
    }
}
