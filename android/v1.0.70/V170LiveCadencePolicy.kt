package de.epimediahub.app.ui

import kotlin.math.abs

/**
 * Live-TV cadence matching: prefer refresh rates typical for television,
 * keep the existing output resolution and never up/down-scale while zapping.
 * A 25 fps TV stream is displayed at 50 Hz, not 25 Hz.
 */
internal object V170LiveCadencePolicy {
    private const val STREAM_TOLERANCE = 0.12f
    private const val MODE_TOLERANCE = 0.012f

    private data class Target(val source: Float, val preferredHz: List<Float>)

    private val known = listOf(
        Target(24000f / 1001f, listOf(24000f / 1001f, 48000f / 1001f)),
        Target(24f, listOf(48f, 24f)),
        Target(25f, listOf(50f, 25f)),
        Target(30000f / 1001f, listOf(60000f / 1001f, 30000f / 1001f)),
        Target(30f, listOf(60f, 30f)),
        Target(50f, listOf(50f)),
        Target(60000f / 1001f, listOf(60000f / 1001f)),
        Target(60f, listOf(60f))
    )

    fun matchingMode(
        current: V121DisplayMode,
        available: List<V121DisplayMode>,
        fps: Float
    ): V121DisplayMode? {
        if (!V121FrameRatePolicy.valid(fps)) return null
        val knownRate = known.minByOrNull { abs(it.source - fps) }
            ?.takeIf { abs(it.source - fps) <= STREAM_TOLERANCE }
            ?: return null

        val sameResolution = available.filter {
            it.width == current.width && it.height == current.height
        }
        for (targetHz in knownRate.preferredHz) {
            val matches = sameResolution.filter { abs(it.hz - targetHz) <= MODE_TOLERANCE }
            // Avoid HDMI switches when already at the best matching cadence.
            matches.firstOrNull { it.id == current.id }?.let { return it }
            matches.minByOrNull { it.id }?.let { return it }
        }
        // Unknown/display-restricted TV modes should never be forced.
        return null
    }
}
