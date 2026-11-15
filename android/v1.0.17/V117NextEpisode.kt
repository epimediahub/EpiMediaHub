package de.epimediahub.app.ui

import de.epimediahub.app.data.V115Segment
import de.epimediahub.app.data.V115SegmentKind
import de.epimediahub.app.data.V115SkipPolicy
import kotlin.math.abs

internal data class V117NextWindow(val startMs: Long, val credits: Boolean)

/** Only verified terminal credits may shorten an episode; otherwise count to its real end. */
internal fun v117NextWindow(durationMs: Long, segments: List<V115Segment>): V117NextWindow? {
    if (durationMs <= 0) return null
    val credits = segments.filter {
        it.kind == V115SegmentKind.OUTRO && it.durationMatched && it.confidence >= .85 &&
            V115SkipPolicy.valid(it, durationMs) && abs(it.endMs - durationMs) <= 1_000L
    }.minByOrNull { it.startMs }
    return if (credits != null) V117NextWindow(credits.startMs, true)
    else V117NextWindow((durationMs - 10_000L).coerceAtLeast(0), false)
}
