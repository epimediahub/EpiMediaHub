package de.epimediahub.app.data

import android.os.SystemClock
import java.util.concurrent.ConcurrentHashMap

/** Bounded in-memory cache; an expired catalogue never becomes a permanent snapshot. */
internal class V128TimedCache<T>(
    private val ttlMs: Long = 600_000L,
    private val limit: Int = 3,
    private val now: () -> Long = SystemClock::elapsedRealtime
) {
    private data class Value<T>(val data: T, val storedAt: Long)
    private val values = ConcurrentHashMap<String, Value<T>>()
    private val locks = ConcurrentHashMap<String, Any>()
    val keys: MutableSet<String> get() = values.keys
    operator fun get(key: String): T? {
        val value = values[key] ?: return null
        if (now() - value.storedAt >= ttlMs) { values.remove(key, value); return null }
        return value.data
    }
    operator fun set(key: String, data: T) {
        values[key] = Value(data, now())
        while (values.size > limit) values.entries.minByOrNull { it.value.storedAt }?.let { values.remove(it.key, it.value) }
    }
    fun getOrLoad(key: String, load: () -> T): T {
        get(key)?.let { return it }
        val lock = locks.computeIfAbsent(key) { Any() }
        return synchronized(lock) { get(key) ?: load().also { set(key, it) } }
    }
    fun clear() { values.clear() }
    fun remove(key: String) { values.remove(key) }
}

internal data class V128LibraryCatalog(
    val categories: List<de.epimediahub.app.model.MediaCategory>,
    val rows: Map<String, List<de.epimediahub.app.model.MediaEntry>>
)
