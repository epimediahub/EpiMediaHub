package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch

internal object V163Epg {
    fun current(events: List<EpgItem>, now: Long): EpgItem? =
        events.firstOrNull { it.start <= now && now < it.end && it.title.isNotBlank() }

    fun next(events: List<EpgItem>, now: Long): EpgItem? =
        events.asSequence().filter { it.start > now && it.end > it.start && it.title.isNotBlank() }
            .minByOrNull { it.start }
}

/** One provider slot is reserved for the playing channel, one for browsing.
 * Promotion shares the same request; it never downloads a channel twice.
 */
internal class V163EpgQueue(
    scope: CoroutineScope,
    private val maxBackground: Int = 16,
    private val retryAfterMs: Long = 30_000L,
    private val clock: () -> Long = { System.nanoTime() / 1_000_000L }
) {
    private class Request(val key: String, var priority: Boolean, val task: suspend () -> Boolean) {
        var started = false
    }
    private val lock = Any()
    private val pending = linkedMapOf<String, Request>()
    private val failedAt = linkedMapOf<String, Long>()
    private val backgroundSignal = Channel<Unit>(Channel.CONFLATED)
    private val prioritySignal = Channel<Unit>(Channel.CONFLATED)

    init {
        for (priority in listOf(false, true)) scope.launch {
            val signal = if (priority) prioritySignal else backgroundSignal
            for (ignored in signal) {
                while (true) {
                    val request = synchronized(lock) {
                        pending.values.firstOrNull { !it.started && it.priority == priority }
                            ?.also { it.started = true }
                    } ?: break
                    var success = false
                    try { success = request.task() }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { /* Missing guide data must not interrupt playback. */ }
                    finally {
                        synchronized(lock) {
                            // clear() may have replaced this key for another playlist session.
                            if (pending[request.key] === request) {
                                pending.remove(request.key)
                                if (success) failedAt.remove(request.key) else {
                                    failedAt[request.key] = clock()
                                    while (failedAt.size > 128) failedAt.remove(failedAt.keys.first())
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    fun submit(key: String, priority: Boolean, task: suspend () -> Boolean): Boolean = synchronized(lock) {
        pending[key]?.let {
            if (priority && !it.started && !it.priority) {
                pending.entries.removeAll { entry -> entry.key != key && entry.value.priority && !entry.value.started }
                it.priority = true
                prioritySignal.trySend(Unit)
            }
            return@synchronized false
        }
        if (failedAt[key]?.let { clock() - it < retryAfterMs } == true) return@synchronized false
        if (priority) {
            // Fast zapping retains only the latest queued playing channel.
            pending.entries.removeAll { it.value.priority && !it.value.started }
        } else if (pending.values.count { !it.priority } >= maxBackground) return@synchronized false
        pending[key] = Request(key, priority, task)
        (if (priority) prioritySignal else backgroundSignal).trySend(Unit)
        true
    }

    fun clear() = synchronized(lock) {
        pending.clear()
        failedAt.clear()
    }
}
