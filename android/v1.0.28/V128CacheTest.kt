package de.epimediahub.app.ui

import de.epimediahub.app.data.V128TimedCache
import org.junit.Assert.*
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class V128CacheTest {
    @Test fun concurrentReadersShareOneLoadAndExpiredDataIsRefetched() {
        var now = 10L
        val cache = V128TimedCache<Int>(100, 3) { now }
        val loads = AtomicInteger()
        val threads = Executors.newFixedThreadPool(6)
        val start = CountDownLatch(1)
        try {
            val results = (0 until 6).map { threads.submit<Int> {
                start.await()
                cache.getOrLoad("catalogue") { Thread.sleep(30); loads.incrementAndGet() }
            } }
            start.countDown()
            assertEquals(listOf(1,1,1,1,1,1), results.map { it.get(2, TimeUnit.SECONDS) })
            assertEquals(1, loads.get())
            now = 110L
            assertEquals(2, cache.getOrLoad("catalogue") { loads.incrementAndGet() })
        } finally { threads.shutdownNow() }
    }
    @Test fun largeLibrariesAreBoundedAndConfigurationChangesHaveSeparateKeys() {
        var now = 0L
        val cache = V128TimedCache<String>(1000, 2) { now }
        cache["profile|old"] = "old"
        now++; cache["profile|new"] = "new"
        assertEquals("old", cache["profile|old"])
        assertEquals("new", cache["profile|new"])
        now++; cache["other"] = "other"
        assertNull(cache["profile|old"])
        assertEquals(2, cache.keys.size)
        cache.clear(); assertNull(cache["profile|new"])
    }
}
