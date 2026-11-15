package de.epimediahub.app.ui

import kotlin.math.abs
import kotlin.math.roundToInt

internal data class V121DisplayMode(val id: Int, val width: Int, val height: Int, val hz: Float)

/** Select only whole-frame cadence at the current output resolution. Never force 24/25/60. */
internal object V121FrameRatePolicy {
    fun valid(fps: Float) = fps.isFinite() && fps >= 10f && fps <= 240f

    fun cadenceError(hz: Float, fps: Float): Float {
        if (!valid(fps) || !hz.isFinite() || hz < fps * .999f) return Float.POSITIVE_INFINITY
        val multiple = (hz / fps).roundToInt().coerceAtLeast(1)
        return abs(hz / multiple - fps)
    }

    fun matchingMode(current: V121DisplayMode, available: List<V121DisplayMode>, fps: Float): V121DisplayMode? {
        if (!valid(fps)) return null
        val exact = available.filter { it.width == current.width && it.height == current.height &&
            cadenceError(it.hz, fps) <= .012f }
        // A 60 Hz screen already fits 30 fps; 120 Hz fits 24 fps. Avoid needless blackouts.
        if (exact.any { it.id == current.id }) return current
        return exact.minWithOrNull(compareBy<V121DisplayMode> { cadenceError(it.hz, fps) }
            .thenBy { abs(it.hz - current.hz) }.thenBy { it.id })
    }
}
