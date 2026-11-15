@file:OptIn(androidx.media3.common.util.UnstableApi::class)

package de.epimediahub.app.ui

import android.app.Activity
import android.content.Context
import android.content.ContextWrapper
import android.content.SharedPreferences
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.Surface
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.ViewGroup
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.C
import androidx.media3.common.Format
import androidx.media3.common.PlaybackParameters
import androidx.media3.common.Player
import androidx.media3.exoplayer.DecoderReuseEvaluation
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.analytics.AnalyticsListener
import androidx.media3.exoplayer.video.VideoFrameMetadataListener
import androidx.media3.ui.AspectRatioFrameLayout
import androidx.media3.ui.PlayerView

private const val FRAME_RATE_KEY = "match_vod_frame_rate"
private fun frameRatePreferences(context: Context) =
    context.applicationContext.getSharedPreferences("epimediahub_video", Context.MODE_PRIVATE)

@Composable
internal fun V121FrameRateControl() {
    val context = LocalContext.current
    val prefs = remember(context.applicationContext) { frameRatePreferences(context) }
    var enabled by remember { mutableStateOf(prefs.getBoolean(FRAME_RATE_KEY, true)) }
    TextButton(onClick = {
        enabled = !enabled
        prefs.edit().putBoolean(FRAME_RATE_KEY, enabled).apply()
    }, modifier = Modifier.fillMaxWidth().v114FocusRing().testTag("vod-match-frame-rate")) {
        Text("TV-Bildrate an Video anpassen: " + if (enabled) "Automatisch" else "Aus",
            color = Color.White, fontSize = 17.sp)
    }
    Text("Beim Wechsel der Bildrate kann der Fernseher kurz schwarz werden.", color = Color.LightGray, fontSize = 12.sp)
}

@Composable
internal fun V121VodSurface(player: Player, isTv: Boolean, modifier: Modifier = Modifier) {
    AndroidView(factory = { context -> V121VideoView(context).apply { bind(player, isTv) } },
        update = { it.bind(player, isTv) }, modifier = modifier.testTag("vod-video-surface"),
        onRelease = { it.close() })
}

/** The view/surface survives progress ticks, subtitles, controls and episode changes. */
internal class V121VideoView(context: Context) : PlayerView(context) {
    private val displayLease = V121DisplayLease(context.activity())
    private var frameRate: V121FrameRateController? = null
    private var boundPlayer: Player? = null
    private var television = false

    init {
        useController = false
        controllerAutoShow = false
        resizeMode = AspectRatioFrameLayout.RESIZE_MODE_FIT
        setKeepContentOnPlayerReset(true)
        setEnableComposeSurfaceSyncWorkaround(true)
        isFocusable = false
        isFocusableInTouchMode = false
        descendantFocusability = ViewGroup.FOCUS_BLOCK_DESCENDANTS
        hideController()
    }

    fun bind(next: Player, isTv: Boolean) {
        if (boundPlayer === next && television == isTv) return
        frameRate?.close()
        boundPlayer = next
        television = isTv
        player = next
        // This view owns the flat video Surface and its metadata listener as one lifecycle.
        // Phones retain Media3's seamless policy; all engines expose diagnostics when available.
        frameRate = if (next is ExoPlayer) {
            (videoSurfaceView as? SurfaceView)?.let { V121FrameRateController(context, next, it, displayLease, isTv) }
        } else null
        if (frameRate != null) V122ActiveVideo.bind(this) else V122ActiveVideo.clear(this)
        if (!isTv) displayLease.restore()
    }

    fun playbackSnapshot(): V122PlaybackSnapshot? = frameRate?.snapshot()

    fun close() {
        V122ActiveVideo.clear(this)
        frameRate?.close()
        frameRate = null
        displayLease.restore()
        player = null
        boundPlayer = null
    }
}

private tailrec fun Context.activity(): Activity? = when (this) {
    is Activity -> this
    is ContextWrapper -> if (baseContext !== this) baseContext.activity() else null
    else -> null
}

/** Retained across episode/player replacement; restored only on exit or when disabled. */
private class V121DisplayLease(private val activity: Activity?) {
    private val originalMode = activity?.window?.attributes?.preferredDisplayModeId ?: 0
    private var requestedMode: Int? = null

    fun match(fps: Float, surface: SurfaceView): String {
        val host = activity ?: return "Kein TV-Fenster verfügbar"
        if (host.isFinishing || host.isDestroyed || host.isInMultiWindowMode) return "Fenster unterstützt keine Anpassung"
        val display = surface.display ?: return "TV-Ausgabe wird ermittelt"
        val current = display.mode.let { V121DisplayMode(it.modeId, it.physicalWidth, it.physicalHeight, it.refreshRate) }
        val available = display.supportedModes.map { V121DisplayMode(it.modeId, it.physicalWidth, it.physicalHeight, it.refreshRate) }
        val target = V121FrameRatePolicy.matchingMode(current, available, fps)
        if (target == null) { restore(); return "Kein passender TV-Modus bei dieser Auflösung gemeldet" }
        if (target.id == current.id) return "Aktuelle TV-Ausgabe passt zur Bildrate"
        if (requestedMode == target.id) return "${v122Number(target.hz)} Hz angefordert"
        val attributes = host.window.attributes
        attributes.preferredDisplayModeId = target.id
        host.window.attributes = attributes
        requestedMode = target.id
        Log.i("EpiMediaHubVideo", "TV cadence: $fps fps -> ${target.hz} Hz")
        return "${v122Number(target.hz)} Hz angefordert"
    }

    fun restore() {
        val ownMode = requestedMode ?: return
        requestedMode = null
        val host = activity ?: return
        if (host.isDestroyed) return
        val attributes = host.window.attributes
        if (attributes.preferredDisplayModeId == ownMode) {
            attributes.preferredDisplayModeId = originalMode
            host.window.attributes = attributes
        }
    }
}

private class V121FrameRateController(
    context: Context, private val player: ExoPlayer, private val view: SurfaceView,
    private val displayLease: V121DisplayLease, private val television: Boolean
) : SurfaceHolder.Callback {
    private val prefs = frameRatePreferences(context)
    private val handler = Handler(Looper.getMainLooper())
    private val oldStrategy = player.videoChangeFrameRateStrategy
    private var enabled = prefs.getBoolean(FRAME_RATE_KEY, true)
    @Volatile private var closed = false
    @Volatile private var sampleGeneration = 0
    private var measuredFps = 0f
    private var reportedFps = player.videoFormat?.frameRate ?: 0f
    private var decoder = ""
    private var request = "Bildrate wird ermittelt"
    private var lastDroppedCount = 0
    // Only the renderer thread touches these two fields.
    private val estimator = V122FrameRateEstimator()
    private var estimatorGeneration = -1
    private var lastApplied = 0f
    private var ownsHint = false
    private var rendererReady = false
    private var hintGeneration = 0
    private val apply = Runnable { applyFrameRate() }
    private val preferences = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
        if (key == FRAME_RATE_KEY) { enabled = prefs.getBoolean(FRAME_RATE_KEY, true); schedule() }
    }
    private val analytics = object : AnalyticsListener {
        override fun onVideoInputFormatChanged(eventTime: AnalyticsListener.EventTime, format: Format,
            decoderReuseEvaluation: DecoderReuseEvaluation?) {
            if (reportedFps != format.frameRate) { measuredFps = 0f; sampleGeneration++ }
            reportedFps = format.frameRate
            schedule()
        }
        override fun onVideoDecoderInitialized(eventTime: AnalyticsListener.EventTime, decoderName: String,
            initializedTimestampMs: Long, initializationDurationMs: Long) {
            decoder = decoderName
            lastDroppedCount = droppedCount()
            sampleGeneration++
        }
    }
    private val events = object : Player.Listener {
        override fun onPlaybackParametersChanged(playbackParameters: PlaybackParameters) { schedule() }
        override fun onPositionDiscontinuity(oldPosition: Player.PositionInfo, newPosition: Player.PositionInfo, reason: Int) {
            sampleGeneration++ // A seek restarts the sample, but keeps an already verified cadence.
        }
    }
    private val metadata = object : VideoFrameMetadataListener {
        override fun onVideoFrameAboutToBeRendered(presentationTimeUs: Long, releaseTimeNs: Long,
            format: Format, mediaFormat: android.media.MediaFormat?) {
            if (closed) return
            val generation = sampleGeneration
            if (estimatorGeneration != generation) { estimator.reset(); estimatorGeneration = generation }
            val candidate = estimator.sample(presentationTimeUs) ?: return
            // No UI/player access on the playback thread and no work per UI progress tick.
            handler.post {
                if (!closed && generation == sampleGeneration) {
                    val dropped = droppedCount()
                    // A decoder dropping every other frame must not produce a half-rate hint.
                    if (dropped == lastDroppedCount && kotlin.math.abs(candidate - measuredFps) > .002f) {
                        measuredFps = candidate
                        schedule()
                    }
                    lastDroppedCount = dropped
                }
            }
        }
    }

    init {
        prefs.registerOnSharedPreferenceChangeListener(preferences)
        player.addAnalyticsListener(analytics)
        player.addListener(events)
        player.setVideoFrameMetadataListener(metadata)
        view.holder.addCallback(this)
        schedule()
    }

    private fun schedule() {
        if (closed) return
        handler.removeCallbacks(apply)
        handler.postDelayed(apply, 350L) // Coalesce format changes, never adjust on progress ticks.
    }

    private fun applyFrameRate() {
        if (closed) return
        val fps = V122FrameRateEstimator.contentRate(player.videoFormat?.frameRate ?: reportedFps, measuredFps) * player.playbackParameters.speed
        if (!television || !enabled) {
            request = if (television) "Automatische Anpassung ausgeschaltet" else "Media3 steuert die Bildrate"
            clearHint()
            displayLease.restore()
            return
        }
        if (!V121FrameRatePolicy.valid(fps)) { request = "Bildrate wird aus Bildzeitstempeln ermittelt"; return }
        if (Build.VERSION.SDK_INT >= 31) {
            val surface = view.holder.surface
            if (!surface.isValid || kotlin.math.abs(lastApplied - fps) < .002f) return
            try {
                // Android honours the user's system Match Content Frame Rate preference.
                // Disable Media3's competing seamless-only hints only while we own this hint.
                if (!ownsHint) {
                    ownsHint = true
                    rendererReady = false
                    val generation = ++hintGeneration
                    player.videoChangeFrameRateStrategy = C.VIDEO_CHANGE_FRAME_RATE_STRATEGY_OFF
                    // Renderer messages run on the playback thread. Apply our hint only after
                    // its earlier rate updates and the OFF message have both been processed.
                    player.createMessage { _, _ ->
                        handler.post {
                            if (!closed && ownsHint && generation == hintGeneration) {
                                rendererReady = true
                                applyFrameRate()
                            }
                        }
                    }.send()
                    return
                }
                if (!rendererReady) return
                surface.setFrameRate(fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE, Surface.CHANGE_FRAME_RATE_ALWAYS)
                lastApplied = fps
                request = "${v122Number(fps)} fps beim System angefordert"
                Log.i("EpiMediaHubVideo", "Requested TV content frame rate: $fps fps")
            } catch (failure: RuntimeException) {
                clearHint()
                request = "System hat die Bildraten-Anforderung abgelehnt"
                Log.w("EpiMediaHubVideo", "Frame-rate hint unavailable; using normal playback", failure)
            }
        } else {
            // Android 7/Fire OS through Android 11: preserve resolution and require an exact cadence.
            runCatching { request = displayLease.match(fps, view) }
                .onFailure { request = "TV-Modus konnte nicht angefordert werden"; Log.w("EpiMediaHubVideo", "Display mode unchanged", it) }
        }
    }

    private fun droppedCount(): Int {
        val counters = player.videoDecoderCounters ?: return 0
        counters.ensureUpdated()
        return counters.droppedBufferCount
    }

    fun snapshot(): V122PlaybackSnapshot {
        val format = player.videoFormat
        val mode = view.display?.mode
        val counters = player.videoDecoderCounters
        counters?.ensureUpdated()
        return V122PlaybackSnapshot(metadataFps = format?.frameRate ?: 0f, measuredFps = measuredFps,
            contentFps = V122FrameRateEstimator.contentRate(format?.frameRate ?: reportedFps, measuredFps),
            speed = player.playbackParameters.speed, outputHz = mode?.refreshRate ?: 0f,
            outputWidth = mode?.physicalWidth ?: 0, outputHeight = mode?.physicalHeight ?: 0,
            videoWidth = format?.width?.coerceAtLeast(0) ?: 0, videoHeight = format?.height?.coerceAtLeast(0) ?: 0,
            codec = format?.sampleMimeType.orEmpty(), decoder = decoder,
            dropped = counters?.droppedBufferCount ?: 0, rendered = counters?.renderedOutputBufferCount ?: 0,
            bufferMs = player.totalBufferedDuration.coerceAtLeast(0L), state = when (player.playbackState) {
                Player.STATE_BUFFERING -> "Puffert"
                Player.STATE_READY -> if (player.isPlaying) "Läuft" else "Pausiert"
                Player.STATE_ENDED -> "Beendet"
                else -> "Wartet"
            }, automatic = television && enabled, request = request)
    }

    private fun clearHint() {
        if (!ownsHint) return
        ownsHint = false
        rendererReady = false
        hintGeneration++
        lastApplied = 0f
        if (Build.VERSION.SDK_INT >= 31) runCatching {
            val surface = view.holder.surface
            if (surface.isValid) surface.setFrameRate(0f, Surface.FRAME_RATE_COMPATIBILITY_DEFAULT, Surface.CHANGE_FRAME_RATE_ONLY_IF_SEAMLESS)
        }
        runCatching { player.videoChangeFrameRateStrategy = oldStrategy }
    }

    override fun surfaceCreated(holder: SurfaceHolder) { lastApplied = 0f; schedule() }
    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) { schedule() }
    override fun surfaceDestroyed(holder: SurfaceHolder) { lastApplied = 0f }

    fun close() {
        if (closed) return
        closed = true
        handler.removeCallbacksAndMessages(null)
        prefs.unregisterOnSharedPreferenceChangeListener(preferences)
        player.removeAnalyticsListener(analytics)
        player.removeListener(events)
        player.clearVideoFrameMetadataListener(metadata)
        view.holder.removeCallback(this)
        clearHint()
    }
}
