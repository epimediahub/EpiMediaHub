package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import java.util.Locale
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.CoroutineStart
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** An immutable, cheap snapshot: never flatten or normalize a catalogue on the UI thread. */
internal class V162EpgInput(
    val profileId: String,
    val profileKey: String,
    val items: List<MediaEntry>,
    val rows: Map<String, List<MediaEntry>>,
    val cachedRows: Map<String, List<MediaEntry>>,
    val guides: Map<String, List<EpgItem>>
) {
    fun sameChannels(other: V162EpgInput): Boolean =
        profileKey == other.profileKey && items === other.items &&
            rows === other.rows && cachedRows === other.cachedRows

    fun channels(): Sequence<MediaEntry> = sequence {
        yieldAll(items)
        rows.values.forEach { yieldAll(it) }
        if (cachedRows !== rows) cachedRows.values.forEach { yieldAll(it) }
    }
}

internal object V162SmartEpg {
    internal class Index(val groups: List<List<String>>)
    internal data class Result(
        val guides: Map<String, List<EpgItem>>,
        val borrowed: Map<String, List<EpgItem>>
    )

    suspend fun index(input: V162EpgInput): Index {
        val groups = linkedMapOf<String, MutableList<MediaEntry>>()
        val seen = hashSetOf<String>()
        var visited = 0
        for (channel in input.channels()) {
            if (++visited % 128 == 0) currentCoroutineContext().ensureActive()
            if (channel.kind != MediaKind.LIVE ||
                channel.sourceProfileId.isNotBlank() && channel.sourceProfileId != input.profileId ||
                !seen.add(channel.id)) continue
            val name = V161SmartEpg.stationKey(channel.name)
            if (name.isNotBlank()) groups.getOrPut(name) { mutableListOf() }.add(channel)
        }
        val compatible = mutableListOf<List<String>>()
        for (members in groups.values) {
            currentCoroutineContext().ensureActive()
            if (members.size < 2) continue
            val explicitIds = members.map { it.epgId.trim().lowercase(Locale.ROOT) }
                .filter { it.isNotBlank() }.toSet()
            if (explicitIds.size <= 1) compatible.add(members.map { it.id })
        }
        // Retain only compact IDs, never a second full MediaEntry catalogue.
        return Index(compatible)
    }

    private fun sameProgramme(a: List<EpgItem>, b: List<EpgItem>): Boolean =
        a.take(2).map { Triple(it.start, it.end, it.title.trim().lowercase(Locale.ROOT)) } ==
            b.take(2).map { Triple(it.start, it.end, it.title.trim().lowercase(Locale.ROOT)) }

    suspend fun enrich(
        index: Index,
        guides: Map<String, List<EpgItem>>,
        previousBorrowed: Map<String, List<EpgItem>>
    ): Result {
        val direct = guides.toMutableMap()
        // A copied programme is not an independent source. A newly fetched list
        // has a different identity and must remain authoritative, even if equal.
        for ((id, guide) in previousBorrowed) {
            currentCoroutineContext().ensureActive()
            if (direct[id] === guide) direct.remove(id)
        }
        val result = direct.toMutableMap()
        val borrowed = mutableMapOf<String, List<EpgItem>>()
        for (members in index.groups) {
            currentCoroutineContext().ensureActive()
            val sources = members.mapNotNull { direct[it]?.takeIf { epg -> epg.isNotEmpty() } }
            val source = sources.firstOrNull() ?: continue
            if (sources.any { !sameProgramme(source, it) }) continue
            for (id in members) {
                if (direct[id].isNullOrEmpty()) {
                    result[id] = source
                    borrowed[id] = source
                }
            }
        }
        // Equality is deliberately checked on the worker, not on the UI thread.
        return Result(if (result == guides) guides else result, borrowed)
    }
}

/** Coalesces catalogue/EPG changes; cancelled or outdated work can never publish. */
internal class V162EpgWorker(
    private val scope: CoroutineScope,
    private val dispatcher: CoroutineDispatcher = Dispatchers.Default,
    private val debounceMs: Long = 120L,
    private val publish: (V162EpgInput, Map<String, List<EpgItem>>) -> Boolean
) {
    private val lock = Any()
    private var generation = 0L
    private var job: Job? = null
    private var indexedInput: V162EpgInput? = null
    private var index: V162SmartEpg.Index? = null
    private var borrowed: Map<String, List<EpgItem>> = emptyMap()

    fun submit(input: V162EpgInput?) = synchronized(lock) {
        val token = ++generation
        job?.cancel()
        if (input == null) {
            job = null
            indexedInput = null
            index = null
            borrowed = emptyMap()
            return@synchronized
        }
        val reusable = index.takeIf { indexedInput?.sameChannels(input) == true }
        val inherited = borrowed.takeIf { indexedInput?.profileKey == input.profileKey }.orEmpty()
        // Always enqueue, including when called during ViewModel construction.
        // Catalogue traversal starts only inside the background dispatcher.
        val next = scope.launch(start = CoroutineStart.LAZY) {
            try {
                delay(debounceMs)
                val calculated = withContext(dispatcher) {
                    val currentIndex = reusable ?: V162SmartEpg.index(input)
                    currentIndex to V162SmartEpg.enrich(currentIndex, input.guides, inherited)
                }
                synchronized(lock) {
                    if (token == generation && publish(input, calculated.second.guides)) {
                        // EPG changes reuse the station index; do not retain large
                        // old guide maps in the cached channel-source identity.
                        indexedInput = V162EpgInput(input.profileId, input.profileKey,
                            input.items, input.rows, input.cachedRows, emptyMap())
                        index = calculated.first
                        borrowed = calculated.second.borrowed
                    }
                }
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (_: Exception) {
                // Programme reuse is optional; the already published channel
                // list and the provider's direct EPG remain fully usable.
            }
        }
        job = next
        next.start()
    }
}

/** Keeps missing-guide retries and queued provider work bounded while scrolling. */
internal class V162EpgRequests(
    private val maxPending: Int = 16,
    private val maxRemembered: Int = 128,
    private val retryAfterMs: Long = 30_000L
) {
    private val pending = hashSetOf<String>()
    private val failedAt = linkedMapOf<String, Long>()

    @Synchronized fun acquire(key: String, now: Long): Boolean {
        if (key in pending || pending.size >= maxPending) return false
        val failed = failedAt[key]
        if (failed != null && now - failed < retryAfterMs) return false
        failedAt.remove(key)
        pending.add(key)
        return true
    }

    @Synchronized fun complete(key: String, success: Boolean, now: Long) {
        pending.remove(key)
        if (success) failedAt.remove(key) else {
            failedAt[key] = now
            while (failedAt.size > maxRemembered) failedAt.remove(failedAt.keys.first())
        }
    }
}
