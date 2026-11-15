package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.asCoroutineDispatcher
import kotlinx.coroutines.cancel
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.yield
import org.junit.Assert.*
import org.junit.Test

class V162SmartEpgTest {
    private fun channel(id: String, name: String = "RTL HD", epgId: String = "", profile: String = "") =
        MediaEntry(id = id, name = name, kind = MediaKind.LIVE, epgId = epgId, sourceProfileId = profile)
    private fun guide(title: String = "Nachrichten", start: Long = 100L) =
        listOf(EpgItem(title, "", start, start + 100L))
    private fun input(
        channels: List<MediaEntry> = listOf(channel("1"), channel("2", "RTL SD")),
        guides: Map<String, List<EpgItem>> = mapOf("1" to guide()),
        key: String = "a|LIVE|revision1",
        rows: Map<String, List<MediaEntry>> = emptyMap(),
        cached: Map<String, List<MediaEntry>> = emptyMap()
    ) = V162EpgInput("a", key, channels, rows, cached, guides)

    @Test fun qualityVariantsShareWithoutMixingRegionsMoviesOrOtherPlaylists() = runBlocking {
        val source = input(listOf(channel("1"), channel("2", "RTL 4K"),
            channel("3", "RTL AT HD"), channel("4", profile = "other"),
            channel("5").copy(kind = MediaKind.MOVIE)))
        val result = V162SmartEpg.enrich(V162SmartEpg.index(source), source.guides, emptyMap())
        assertSame(source.guides["1"], result.guides["2"])
        assertNull(result.guides["3"])
        assertNull(result.guides["4"])
        assertNull(result.guides["5"])
    }

    @Test fun conflictingExplicitStationIdsPreventAnyTransfer() = runBlocking {
        val source = input(listOf(channel("1", epgId = "rtl.de"), channel("2", epgId = "rtl.at")))
        val result = V162SmartEpg.enrich(V162SmartEpg.index(source), source.guides, emptyMap())
        assertSame(source.guides, result.guides)
        assertTrue(result.borrowed.isEmpty())
    }

    @Test fun duplicateRowsAndAllCategoryDoNotDuplicateStationIndex() = runBlocking {
        val channels = listOf(channel("1"), channel("2", "RTL SD"))
        val rows = mapOf("all" to channels, "german" to channels)
        val source = input(channels, rows = rows, cached = rows)
        val index = V162SmartEpg.index(source)
        assertEquals(listOf(listOf("1", "2")), index.groups)
    }

    @Test fun updatedSourceRefreshesBorrowedVariantsInsteadOfTreatingThemAsDonors() = runBlocking {
        val source = input()
        val index = V162SmartEpg.index(source)
        val first = V162SmartEpg.enrich(index, source.guides, emptyMap())
        val updated = guide("Nächste Sendung", 200L)
        val second = V162SmartEpg.enrich(index, first.guides + ("1" to updated), first.borrowed)
        assertSame(updated, second.guides["1"])
        assertSame(updated, second.guides["2"])
    }

    @Test fun conflictingNewDirectGuideRemainsAuthoritativeAndRemovesOldCopies() = runBlocking {
        val source = input(listOf(channel("1"), channel("2", "RTL SD"), channel("3", "RTL FHD")))
        val index = V162SmartEpg.index(source)
        val first = V162SmartEpg.enrich(index, source.guides, emptyMap())
        val actual = guide("Andere Sendung")
        val second = V162SmartEpg.enrich(index, first.guides + ("2" to actual), first.borrowed)
        assertSame(source.guides["1"], second.guides["1"])
        assertSame(actual, second.guides["2"])
        assertNull(second.guides["3"])
    }

    @Test fun equivalentResultPreservesIdentityAndDoesNotTriggerAnotherUiUpdate() = runBlocking {
        val source = input()
        val index = V162SmartEpg.index(source)
        val first = V162SmartEpg.enrich(index, source.guides, emptyMap())
        val second = V162SmartEpg.enrich(index, first.guides, first.borrowed)
        assertSame(first.guides, second.guides)
    }

    @Test fun largeCatalogueTraversalRunsOffUiThreadAndIsReusedForEpgOnlyUpdates() = runBlocking {
        val uiThread = Thread.currentThread()
        val visits = AtomicInteger()
        val wrongThread = AtomicInteger()
        val channels = object : AbstractList<MediaEntry>() {
            override val size = 12_000
            override fun get(index: Int): MediaEntry {
                visits.incrementAndGet()
                if (Thread.currentThread() === uiThread) wrongThread.incrementAndGet()
                return channel(index.toString(), "Sender ${index / 2} " + if (index % 2 == 0) "HD" else "SD")
            }
        }
        Executors.newSingleThreadExecutor().asCoroutineDispatcher().use { background ->
            val received = Channel<Map<String, List<EpgItem>>>(Channel.UNLIMITED)
            val worker = V162EpgWorker(this, background, 0L) { _, output ->
                assertSame(uiThread, Thread.currentThread())
                received.trySend(output)
                true
            }
            worker.submit(input(channels, mapOf("0" to guide())))
            // submit must not enumerate channels, even with an immediate UI dispatcher.
            assertEquals(0, visits.get())
            val first = withTimeout(5_000L) { received.receive() }
            assertEquals(0, wrongThread.get())
            assertNotNull(first["1"])
            val count = visits.get()
            val updated = guide("Aktuell", 200L)
            worker.submit(input(channels, first + ("0" to updated)))
            val second = withTimeout(5_000L) { received.receive() }
            assertSame(updated, second["1"])
            assertEquals(count, visits.get())
            worker.submit(null)
            received.close()
            Unit
        }
    }

    @Test fun rapidlyChangingGuideInputsCoalesceIntoOnePublication() = runBlocking {
        val channels = listOf(channel("1"), channel("2"))
        val received = Channel<Map<String, List<EpgItem>>>(Channel.UNLIMITED)
        val worker = V162EpgWorker(this, debounceMs = 10L) { _, output -> received.trySend(output); true }
        repeat(100) { worker.submit(input(channels, mapOf("1" to guide("Sendung $it")))) }
        val result = withTimeout(5_000L) { received.receive() }
        assertEquals("Sendung 99", result["2"]?.first()?.title)
        assertTrue(received.tryReceive().isFailure)
        worker.submit(null)
        received.close()
        Unit
    }

    @Test fun supersededInFlightCatalogueCannotPublishOldProgrammes() = runBlocking {
        val started = CountDownLatch(1)
        val release = CountDownLatch(1)
        val reads = AtomicInteger()
        val channels = object : AbstractList<MediaEntry>() {
            override val size = 2
            override fun get(index: Int): MediaEntry {
                if (reads.getAndIncrement() == 0) {
                    started.countDown()
                    check(release.await(5, TimeUnit.SECONDS))
                }
                return channel((index + 1).toString())
            }
        }
        Executors.newSingleThreadExecutor().asCoroutineDispatcher().use { background ->
            val received = Channel<Map<String, List<EpgItem>>>(Channel.UNLIMITED)
            val worker = V162EpgWorker(this, background, 0L) { _, output -> received.trySend(output); true }
            worker.submit(input(channels, mapOf("1" to guide("Alt"))))
            yield()
            assertTrue(withContext(Dispatchers.IO) { started.await(5, TimeUnit.SECONDS) })
            worker.submit(input(channels, mapOf("1" to guide("Neu"))))
            release.countDown()
            val result = withTimeout(5_000L) { received.receive() }
            assertEquals("Neu", result["2"]?.first()?.title)
            assertTrue(received.tryReceive().isFailure)
            worker.submit(null)
            received.close()
            Unit
        }
    }

    @Test fun changedPlaylistRevisionCannotReuseBorrowedProgrammeProvenance() = runBlocking {
        val channels = listOf(channel("1"), channel("2"))
        val received = Channel<Map<String, List<EpgItem>>>(Channel.UNLIMITED)
        val worker = V162EpgWorker(this, debounceMs = 0L) { _, output -> received.trySend(output); true }
        worker.submit(input(channels))
        withTimeout(5_000L) { received.receive() }
        val newGuide = guide("Neuer Anbieter")
        worker.submit(input(channels, mapOf("2" to newGuide), key = "a|LIVE|revision2"))
        val result = withTimeout(5_000L) { received.receive() }
        assertSame(newGuide, result["1"])
        worker.submit(null)
        received.close()
        Unit
    }

    @Test fun cancelledScopeNeverStartsCatalogueTraversal() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        scope.cancel()
        val channels = object : AbstractList<MediaEntry>() {
            override val size = 1
            override fun get(index: Int): MediaEntry = error("Cancelled work traversed catalogue")
        }
        var published = false
        V162EpgWorker(scope, debounceMs = 0L) { _, _ -> published = true; true }.submit(input(channels))
        assertFalse(published)
    }

    @Test fun providerRequestsDeduplicateBoundQueueAndAllowRetriesAfterCooldown() {
        val requests = V162EpgRequests(maxPending = 2, maxRemembered = 2, retryAfterMs = 100L)
        assertTrue(requests.acquire("a|1", 0L))
        assertFalse(requests.acquire("a|1", 1L))
        assertTrue(requests.acquire("a|2", 1L))
        assertFalse(requests.acquire("a|3", 2L))
        requests.complete("a|1", false, 10L)
        assertFalse(requests.acquire("a|1", 109L))
        assertTrue(requests.acquire("a|1", 110L))
        requests.complete("a|1", true, 111L)
        assertTrue(requests.acquire("a|1", 112L))
        requests.complete("a|2", true, 113L)
        assertTrue(requests.acquire("b|1", 113L))
    }
}
