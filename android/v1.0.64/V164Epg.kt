package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.ensureActive

internal object V164Epg {
    fun seconds(value: Long): Long = if (value > 100_000_000_000L) value / 1000L else value

    /** Direct EPG stays authoritative. At most two already-validated station
     * siblings are consulted when a quality variant has no current programme.
     */
    suspend fun load(
        id: String,
        peers: () -> List<String>,
        cached: (String) -> List<EpgItem>,
        fetch: suspend (String) -> List<EpgItem>,
        publish: (String, List<EpgItem>) -> Unit,
        now: () -> Long = { System.currentTimeMillis() / 1000L }
    ): List<EpgItem> {
        suspend fun guide(key: String): List<EpgItem> {
            currentCoroutineContext().ensureActive()
            val stored = cached(key)
            if (V163Epg.current(stored, now()) != null) return stored
            val events = runCatching { fetch(key) }.getOrElse {
                currentCoroutineContext().ensureActive()
                emptyList()
            }
            currentCoroutineContext().ensureActive()
            if (events.isNotEmpty()) publish(key, events)
            return events
        }
        val direct = guide(id)
        if (V163Epg.current(direct, now()) != null) return direct
        for (peer in peers().asSequence().filter { it != id }.distinct().take(2)) {
            val events = guide(peer)
            if (V163Epg.current(events, now()) != null) return events
        }
        return direct
    }
}
