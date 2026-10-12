package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import org.junit.Assert.*
import org.junit.Test

class V163EpgQueueTest {
    @Test fun currentProgrammeUsesTimeInsteadOfFirstProviderRow() {
        val expired = EpgItem("Vorher", "", 0, 100)
        val current = EpgItem("Jetzt", "Beschreibung", 100, 200)
        val next = EpgItem("Danach", "", 200, 300)
        assertSame(current, V163Epg.current(listOf(next, expired, current), 150))
        assertSame(next, V163Epg.next(listOf(next, expired, current), 150))
        assertSame(next, V163Epg.current(listOf(current, next), 200))
        assertNull(V163Epg.current(listOf(expired), 150))
        assertNull(V163Epg.current(listOf(next), 150))
    }

    @Test fun playbackBypassesBlockedBrowsingAndPromotesWithoutDuplicateFetch() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val queue = V163EpgQueue(scope, maxBackground = 2)
            val started = Channel<String>(Channel.UNLIMITED)
            val releaseBackground = CompletableDeferred<Unit>()
            assertTrue(queue.submit("slow", false) { started.send("slow"); releaseBackground.await(); true })
            assertEquals("slow", withTimeout(2_000) { started.receive() })
            assertTrue(queue.submit("target", false) { started.send("target"); true })
            assertFalse(queue.submit("rejected", false) { error("Full queue accepted another request") })
            assertFalse(queue.submit("target", true) { error("Promotion duplicated provider work") })
            assertEquals("target", withTimeout(2_000) { started.receive() })
            assertTrue(started.tryReceive().isFailure)
            releaseBackground.complete(Unit)
        } finally { scope.cancel() }
    }

    @Test fun rapidZappingOnlyRetainsLatestWaitingPlayingChannel() = runBlocking {
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val queue = V163EpgQueue(scope)
            val started = Channel<String>(Channel.UNLIMITED)
            val release = CompletableDeferred<Unit>()
            queue.submit("first", true) { started.send("first"); release.await(); true }
            assertEquals("first", withTimeout(2_000) { started.receive() })
            queue.submit("skipped", true) { error("Superseded channel was fetched") }
            queue.submit("latest", true) { started.send("latest"); true }
            release.complete(Unit)
            assertEquals("latest", withTimeout(2_000) { started.receive() })
            assertTrue(started.tryReceive().isFailure)
        } finally { scope.cancel() }
    }

    @Test fun failedGuidesRetryAfterCooldownAndPlaylistResetClearsIt() = runBlocking {
        var now = 0L
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val queue = V163EpgQueue(scope, retryAfterMs = 100L, clock = { now })
            assertTrue(queue.submit("a", true) { false })
            assertFalse(queue.submit("a", true) { true })
            now = 100L
            assertTrue(queue.submit("a", true) { false })
            queue.clear()
            assertTrue(queue.submit("a", true) { true })
        } finally { scope.cancel() }
    }

    @Test fun oldSessionCompletionCannotPoisonNewSessionRequestWithSameId() = runBlocking {
        var now = 0L
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        try {
            val queue = V163EpgQueue(scope, retryAfterMs = 1_000L, clock = { now })
            val release = CompletableDeferred<Unit>()
            val fetched = CompletableDeferred<Unit>()
            queue.submit("same", true) { release.await(); false }
            queue.clear()
            assertTrue(queue.submit("same", true) { fetched.complete(Unit); true })
            release.complete(Unit)
            withTimeout(2_000) { fetched.await() }
            assertTrue(queue.submit("same", true) { true })
        } finally { scope.cancel() }
    }
}
