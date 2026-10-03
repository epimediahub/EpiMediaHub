package de.epimediahub.app.data

import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeoutOrNull

/** The server lease also expires after a crash or a disconnected device. */
internal suspend fun v125KeepSkipPresence(record: suspend (Boolean) -> Unit) {
    try {
        while (true) { record(true); delay(25_000L) }
    } finally {
        withContext(NonCancellable) {
            withTimeoutOrNull(9_000L) { record(false) }
        }
    }
}

internal fun v125MergeCentral(previous: List<V115Segment>, central: V116SkipResult): List<V115Segment> {
    val centralKinds = central.segments.map { it.kind }.toSet() + central.disabled
    return previous.filterNot { it.source == "EpiMediaHub · geprüft" || it.kind in centralKinds } + central.segments
}
