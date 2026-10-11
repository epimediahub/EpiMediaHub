package de.epimediahub.app.ui

import kotlin.math.exp

/** Shared, elapsed-time timeline. No independent repeating animations can drift from the sound. */
internal object V121IntroTimeline {
    const val DURATION_MS = 10000L
    const val LOGO_START_MS = 8700L
    val heartbeats = listOf(460L, 1100L, 4660L, 5300L, 6410L, 7020L, 8630L)

    fun ease(value: Float): Float {
        val x = value.coerceIn(0f, 1f)
        return x * x * (3f - 2f * x)
    }

    fun envelope(timeMs: Long, start: Long, inMs: Long, end: Long, outMs: Long): Float =
        ease((timeMs - start).toFloat() / inMs) * ease((end - timeMs).toFloat() / outMs)

    fun worldAlpha(timeMs: Long) = envelope(timeMs, 130, 320, 1680, 290)
    fun appAlpha(timeMs: Long) = envelope(timeMs, 7720, 280, 9040, 280)
    fun logoAlpha(timeMs: Long) = envelope(timeMs, LOGO_START_MS, 300, DURATION_MS, 160)

    fun pulse(timeMs: Long): Float = heartbeats.sumOf { start ->
        val first = (timeMs - start).toDouble() / 72.0
        val second = (timeMs - start - 170L).toDouble() / 65.0
        exp(-first * first) + .56 * exp(-second * second)
    }.toFloat().coerceIn(0f, 1f)

    fun textScale(timeMs: Long) = 1f + .025f * pulse(timeMs)
    fun logoScale(timeMs: Long) = .92f + .08f * ease((timeMs - LOGO_START_MS).toFloat() / 800f)
}
