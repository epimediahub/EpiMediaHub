package de.epimediahub.app.ui

import android.app.Activity
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.SurfaceView
import kotlin.math.abs

/**
 * Own a single LIVE HDMI preference across channel/player replacements.
 * No IPTV stream is opened for probing. Change requests are debounced and
 * cancelled on rapid zapping, and VOD has its own independent display lease.
 */
internal object V192LiveCadencePolicy {
    fun target(current: V121DisplayMode, modes: List<V121DisplayMode>, fps: Float): V121DisplayMode? {
        val expectedHz = when {
            abs(fps - 25f) < .13f || abs(fps - 50f) < .13f -> 50f
            abs(fps - 30000f / 1001f) < .01f ||
                abs(fps - 60000f / 1001f) < .01f -> 60000f / 1001f
            abs(fps - 30f) < .13f || abs(fps - 60f) < .13f -> 60f
            else -> return null
        }
        val matched = V170LiveCadencePolicy.matchingMode(current, modes, fps) ?: return null
        return matched.takeIf { abs(it.hz - expectedHz) < .05f }
    }
}

internal object V192LiveModeHold {
    private const val TAG = "EpiMediaHubCadence"
    private const val STABLE_PLAYBACK_MS = 3_000L
    private const val MIN_SWITCH_INTERVAL_MS = 18_000L
    private const val ZAP_GRACE_MS = 7_000L
    private val handler = Handler(Looper.getMainLooper())

    private class Lease(val host: Activity, val originalPreference: Int) {
        var attachments = 0
        var requestedMode: Int? = null
        var lastSwitchMs = 0L
        var pending: Runnable? = null
        var release: Runnable? = null
        var generation = 0
    }

    private var lease: Lease? = null

    fun originalPreference(host: Activity?): Int? =
        lease?.takeIf { it.host === host }?.originalPreference

    private fun cancelPending(state: Lease) {
        state.generation++
        state.pending?.let(handler::removeCallbacks)
        state.pending = null
    }

    fun attach(host: Activity?) {
        if (host == null || host.isFinishing || host.isDestroyed) return
        var state = lease
        if (state != null && state.host !== host) {
            cancelPending(state)
            restore(state)
            state = null
            lease = null
        }
        if (state == null) {
            state = Lease(host, host.window.attributes.preferredDisplayModeId)
            lease = state
        }
        state.release?.let(handler::removeCallbacks)
        state.release = null
        state.attachments++
        cancelPending(state)
    }

    fun invalidate(host: Activity?) {
        lease?.takeIf { it.host === host }?.let(::cancelPending)
    }

    fun detach(host: Activity?) {
        val state = lease?.takeIf { it.host === host } ?: return
        state.attachments = (state.attachments - 1).coerceAtLeast(0)
        cancelPending(state)
        if (state.attachments != 0) return
        state.release?.let(handler::removeCallbacks)
        val task = Runnable {
            if (lease === state && state.attachments == 0) {
                restore(state)
                lease = null
            }
        }
        state.release = task
        handler.postDelayed(task, ZAP_GRACE_MS)
    }

    fun handoffForCinema(host: Activity?) {
        val state = lease?.takeIf { it.host === host } ?: return
        cancelPending(state)
        state.release?.let(handler::removeCallbacks)
        restore(state)
        lease = null
    }

    fun disabled(host: Activity?) {
        lease?.takeIf { it.host === host }?.let { state ->
            cancelPending(state)
            restore(state)
        }
    }

    private fun restore(state: Lease) {
        val owned = state.requestedMode ?: return
        state.requestedMode = null
        val host = state.host
        if (host.isDestroyed) return
        val attrs = host.window.attributes
        if (attrs.preferredDisplayModeId == owned) {
            attrs.preferredDisplayModeId = state.originalPreference
            host.window.attributes = attrs
        }
    }

    fun request(host: Activity?, surface: SurfaceView, fps: Float): String {
        val state = lease?.takeIf { it.host === host && it.attachments > 0 }
            ?: return "Live: HDMI-Sitzung nicht aktiv"
        if (host == null || host.isFinishing || host.isDestroyed || host.isInMultiWindowMode)
            return "Live: Displaywechsel nicht möglich"
        val display = surface.display ?: return "Live: Display noch nicht bereit"
        val current = display.mode.let {
            V121DisplayMode(it.modeId, it.physicalWidth, it.physicalHeight, it.refreshRate)
        }
        val available = display.supportedModes.map {
            V121DisplayMode(it.modeId, it.physicalWidth, it.physicalHeight, it.refreshRate)
        }
        val target = V192LiveCadencePolicy.target(current, available, fps)
            ?: return "Live: kein kompatibler 50/60-Hz-Modus"
        if (target.id == current.id || target.id == state.requestedMode) {
            cancelPending(state)
            return "Live: passender Bildmodus bereits aktiv/angefordert"
        }
        if (state.requestedMode != null &&
            host.window.attributes.preferredDisplayModeId != state.requestedMode)
            return "Live: fremde Bildmoduseinstellung bleibt erhalten"

        cancelPending(state)
        val generation = state.generation
        val elapsed = SystemClock.elapsedRealtime() - state.lastSwitchMs
        val cooldown = if (state.lastSwitchMs == 0L) 0L
            else (MIN_SWITCH_INTERVAL_MS - elapsed).coerceAtLeast(0L)
        val task = Runnable {
            if (lease !== state || state.generation != generation ||
                state.attachments == 0 || host.isFinishing || host.isDestroyed ||
                !surface.isAttachedToWindow || !surface.holder.surface.isValid) return@Runnable
            val actual = surface.display?.mode ?: return@Runnable
            if (actual.physicalWidth != target.width ||
                actual.physicalHeight != target.height) return@Runnable
            val attrs = host.window.attributes
            if (state.requestedMode != null && attrs.preferredDisplayModeId != state.requestedMode)
                return@Runnable
            if (actual.modeId == target.id || attrs.preferredDisplayModeId == target.id)
                return@Runnable
            attrs.preferredDisplayModeId = target.id
            host.window.attributes = attrs
            state.requestedMode = target.id
            state.lastSwitchMs = SystemClock.elapsedRealtime()
            state.pending = null
            Log.i(TAG, "Live requested " + target.hz + " Hz after stable playback; no zap reset")
        }
        state.pending = task
        handler.postDelayed(task, maxOf(STABLE_PLAYBACK_MS, cooldown))
        return "Live: " + target.hz + " Hz nach stabiler Wiedergabe vorgesehen"
    }
}
