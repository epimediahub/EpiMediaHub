package de.epimediahub.app.ui

import kotlin.math.abs

/** Presentation timestamps describe the content, unlike callback/arrival wall-clock times.
 * Accept only a continuous, near-constant cadence over at least three seconds. Millisecond
 * container timestamps may alternate (e.g. 41/42 ms); average the complete window. A seek,
 * dropped frame or variable cadence restarts the window instead of guessing a TV mode.
 * This instance is confined to the playback thread; no allocation on ordinary frames.
 */
internal class V122FrameRateEstimator {
    private var previous = Long.MIN_VALUE
    private var totalUs = 0L
    private var intervals = 0
    private var minimum = Long.MAX_VALUE
    private var maximum = 0L

    fun reset() {
        previous = Long.MIN_VALUE
        totalUs = 0L
        intervals = 0
        minimum = Long.MAX_VALUE
        maximum = 0L
    }

    fun sample(presentationTimeUs: Long): Float? {
        val last = previous
        previous = presentationTimeUs
        if (last == Long.MIN_VALUE) return null
        val delta = presentationTimeUs - last
        if (delta !in 4_000L..100_000L) { restartAt(presentationTimeUs); return null }
        minimum = minOf(minimum, delta)
        maximum = maxOf(maximum, delta)
        if (maximum - minimum > 1_100L) { restartAt(presentationTimeUs); return null }
        totalUs += delta
        intervals++
        if (totalUs < 3_000_000L || intervals < 48) return null
        val measured = intervals * 1_000_000.0 / totalUs
        restartAt(presentationTimeUs)
        // Do not confuse 23.976 with 24 (or 29.97 with 30). The tolerance is smaller
        // than half that separation, including containers quantized to milliseconds.
        return RATES.minByOrNull { abs(it - measured) }?.takeIf { abs(it - measured) <= .008 }
    }

    private fun restartAt(pts: Long) { reset(); previous = pts }

    companion object {
        private val RATES = floatArrayOf(24000f / 1001f, 24f, 25f, 30000f / 1001f, 30f,
            48000f / 1001f, 48f, 50f, 60000f / 1001f, 60f, 100f, 120000f / 1001f, 120f)

        fun contentRate(metadata: Float, measured: Float): Float = when {
            // Correct rounding of otherwise valid metadata, never halve/double a known rate.
            V121FrameRatePolicy.valid(metadata) -> if (V121FrameRatePolicy.valid(measured) &&
                abs(measured - metadata) < .05f) measured else metadata
            V121FrameRatePolicy.valid(measured) -> measured
            else -> 0f
        }
    }
}
