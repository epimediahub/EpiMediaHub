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
        Text("Bildrate an Film anpassen: " + if (enabled) "Automatisch" else "Aus",
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
        // Phones retain Media3's seamless policy; long TV videos may use matching modes.
        frameRate = if (isTv && next is ExoPlayer) {
            (videoSurfaceView as? SurfaceView)?.let { V121FrameRateController(context, next, it, displayLease) }
        } else null
        if (!isTv) displayLease.restore()
    }

    fun close() {
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

    fun match(fps: Float, surface: SurfaceView) {
        val host = activity ?: return
        if (host.isFinishing || host.isDestroyed || host.isInMultiWindowMode) return
        val display = surface.display ?: return
        val current = display.mode.let { V121DisplayMode(it.modeId, it.physicalWidth, it.physicalHeight, it.refreshRate) }
        val available = display.supportedModes.map { V121DisplayMode(it.modeId, it.physicalWidth, it.physicalHeight, it.refreshRate) }
        val target = V121FrameRatePolicy.matchingMode(current, available, fps)
        if (target == null) { restore(); return }
        if (target.id == current.id || requestedMode == target.id) return
        val attributes = host.window.attributes
        attributes.preferredDisplayModeId = target.id
        host.window.attributes = attributes
        requestedMode = target.id
        Log.i("EpiMediaHubVideo", "TV cadence: $fps fps -> ${target.hz} Hz")
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
    private val displayLease: V121DisplayLease
) : SurfaceHolder.Callback {
    private val prefs = frameRatePreferences(context)
    private val handler = Handler(Looper.getMainLooper())
    private val oldStrategy = player.videoChangeFrameRateStrategy
    private var enabled = prefs.getBoolean(FRAME_RATE_KEY, true)
    private var closed = false
    private var lastApplied = 0f
    private var ownsHint = false
    private val apply = Runnable { applyFrameRate() }
    private val preferences = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
        if (key == FRAME_RATE_KEY) { enabled = prefs.getBoolean(FRAME_RATE_KEY, true); schedule() }
    }
    private val analytics = object : AnalyticsListener {
        override fun onVideoInputFormatChanged(eventTime: AnalyticsListener.EventTime, format: Format,
            decoderReuseEvaluation: DecoderReuseEvaluation?) { schedule() }
    }
    private val events = object : Player.Listener {
        override fun onPlaybackParametersChanged(playbackParameters: PlaybackParameters) { schedule() }
    }

    init {
        prefs.registerOnSharedPreferenceChangeListener(preferences)
        player.addAnalyticsListener(analytics)
        player.addListener(events)
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
        val fps = (player.videoFormat?.frameRate ?: -1f) * player.playbackParameters.speed
        if (!enabled || !V121FrameRatePolicy.valid(fps)) {
            clearHint()
            displayLease.restore()
            return
        }
        if (Build.VERSION.SDK_INT >= 31) {
            val surface = view.holder.surface
            if (!surface.isValid || kotlin.math.abs(lastApplied - fps) < .002f) return
            try {
                // Android honours the user's system Match Content Frame Rate preference.
                // Disable Media3's competing seamless-only hints only while we own this hint.
                player.videoChangeFrameRateStrategy = C.VIDEO_CHANGE_FRAME_RATE_STRATEGY_OFF
                ownsHint = true
                surface.setFrameRate(fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE, Surface.CHANGE_FRAME_RATE_ALWAYS)
                lastApplied = fps
                Log.i("EpiMediaHubVideo", "Requested TV content frame rate: $fps fps")
            } catch (failure: RuntimeException) {
                clearHint()
                Log.w("EpiMediaHubVideo", "Frame-rate hint unavailable; using normal playback", failure)
            }
        } else {
            // Android 7/Fire OS through Android 11: preserve resolution and require an exact cadence.
            runCatching { displayLease.match(fps, view) }
                .onFailure { Log.w("EpiMediaHubVideo", "Display mode unchanged", it) }
        }
    }

    private fun clearHint() {
        if (!ownsHint) return
        ownsHint = false
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
        handler.removeCallbacks(apply)
        prefs.unregisterOnSharedPreferenceChangeListener(preferences)
        player.removeAnalyticsListener(analytics)
        player.removeListener(events)
        view.holder.removeCallback(this)
        clearHint()
    }
}
