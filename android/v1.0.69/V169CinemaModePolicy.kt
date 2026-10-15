package de.epimediahub.app.ui

import kotlin.math.abs

/**
 * Opt-in VOD-only display-mode selection. Keep the existing resolution when
 * possible; use 1080p only if enabled and no suitable mode exists at 4K.
 * Never choose 50/60 Hz as a substitute for 23.976 fps.
 */
internal object V169CinemaModePolicy {
    private const val TOLERANCE_FPS = 0.034f // 23.976 -> 24.000 is an acceptable last resort.

    fun matchingMode(
        current: V121DisplayMode,
        available: List<V121DisplayMode>,
        fps: Float,
        allow1080p: Boolean
    ): V121DisplayMode? {
        if (!V121FrameRatePolicy.valid(fps)) return null
        fun candidate(width: Int, height: Int): V121DisplayMode? {
            val compatible = available.filter {
                it.width == width && it.height == height &&
                    V121FrameRatePolicy.cadenceError(it.hz, fps) <= TOLERANCE_FPS
            }
            if (compatible.isEmpty()) return null
            compatible.firstOrNull { it.id == current.id }?.let { return it }
            return compatible.minWithOrNull(
                compareBy<V121DisplayMode> { V121FrameRatePolicy.cadenceError(it.hz, fps) }
                    .thenBy { abs(it.hz - current.hz) }
                    .thenBy { it.id }
            )
        }
        candidate(current.width, current.height)?.let { return it }
        if (!allow1080p || current.width < 1920 || current.height < 1080) return null
        return candidate(1920, 1080)
    }
}
