package de.epimediahub.app.ui

internal data class V118NextWindow(val startMs: Long)

/** The requested fixed window works without an intro/credits analysis result. */
internal fun v118NextWindow(durationMs: Long): V118NextWindow? =
    if (durationMs <= 0) null else V118NextWindow((durationMs - 40_000L).coerceAtLeast(0))

internal fun v118NextTarget(positionMs: Long, durationMs: Long): Long =
    (positionMs + 10_000L).coerceAtMost(durationMs)
