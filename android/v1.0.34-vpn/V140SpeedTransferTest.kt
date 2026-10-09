package de.epimediahub.app.vpn

import java.net.ServerSocket
import java.net.Socket
import java.net.InetAddress
import java.io.InputStream
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicBoolean
import java.net.SocketException
import java.util.Collections
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/** Loopback integration tests send real HTTP bytes, without external services. */
class V140SpeedTransferTest {
    private lateinit var server: ServerSocket
    private lateinit var worker: Thread
    private lateinit var url: String
    private val serverFailure = AtomicReference<Throwable?>(null)
    private val requests = AtomicInteger()
    private val uploaded = AtomicInteger()
    private val expectClientAbort = AtomicBoolean(false)
    private val activeClients = Collections.synchronizedList(mutableListOf<Thread>())
    @Before fun setup() {
        server = ServerSocket(0, 8, InetAddress.getByName("127.0.0.1"))
        url = "http://127.0.0.1:${server.localPort}"
        worker = thread(name = "speedtest-loopback", isDaemon = true) {
            while (!server.isClosed) {
                try {
                    val client = server.accept()
                    val child = thread(name = "speedtest-loopback-client", isDaemon = true) {
                        try { client.use { serve(it) } }
                        catch (e: Exception) {
                            // A test that deliberately disconnects four active
                            // streams is expected to elicit EPIPE on the fixture.
                            // All other socket errors remain test failures.
                            val expected = expectClientAbort.get() &&
                                e is SocketException &&
                                (e.message?.contains("Broken pipe", ignoreCase = true) == true ||
                                 e.message?.contains("Connection reset", ignoreCase = true) == true)
                            if (!expected) serverFailure.compareAndSet(null, e)
                        }
                    }
                    activeClients.add(child)
                } catch (e: Exception) {
                    if (!server.isClosed) serverFailure.set(e)
                    break
                }
            }
        }
    }
    private fun line(input: InputStream): String {
        val bytes = ArrayList<Byte>()
        while (true) {
            val b = input.read()
            if (b == -1 || b == 10) break
            if (b != 13) bytes.add(b.toByte())
            check(bytes.size <= 8192)
        }
        return bytes.toByteArray().toString(Charsets.US_ASCII)
    }
    private fun serve(socket: Socket) {
        socket.soTimeout = 5000
        val input = socket.getInputStream()
        val request = line(input).split(' ')
        var length = 0
        var range: String? = null
        while (true) {
            val header = line(input)
            if (header.isEmpty()) break
            if (header.startsWith("Content-Length:", ignoreCase = true))
                length = header.substringAfter(':').trim().toInt()
            if (header.startsWith("Range:", ignoreCase = true))
                range = header.substringAfter(':').trim()
        }
        val output = socket.getOutputStream()
        if (request[1] == "/redirect") {
            output.write("HTTP/1.1 302 Found\r\nLocation: /down\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".toByteArray())
        } else if (request[1] == "/forbidden") {
            output.write("HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".toByteArray())
        } else if (request[1] == "/range") {
            val requested = range?.removePrefix("bytes=0-")?.toIntOrNull()?.plus(1)
            val actual = (requested ?: 256 * 1024).coerceIn(1, 256 * 1024)
            val bytes = ByteArray(actual) { (it % 251).toByte() }
            output.write(("HTTP/1.1 206 Partial Content\r\n" +
                "Content-Range: bytes 0-${actual - 1}/104857600\r\n" +
                "Content-Length: $actual\r\nConnection: close\r\n\r\n").toByteArray())
            output.write(bytes)
        } else {
            requests.incrementAndGet()
            val data = if (request[1] == "/up") {
                check(request[0] == "POST")
                val buffer = ByteArray(8192)
                var received = 0
                while (received < length) {
                    val n = input.read(buffer, 0, minOf(buffer.size, length - received))
                    check(n > 0)
                    received += n
                }
                uploaded.addAndGet(received)
                "OK".toByteArray()
            } else ByteArray(256 * 1024) { (it % 251).toByte() }
            output.write("HTTP/1.1 200 OK\r\nContent-Length: ${data.size}\r\nConnection: close\r\n\r\n".toByteArray())
            output.write(data)
        }
        output.flush()
    }
    @After fun teardown() {
        server.close()
        worker.join(1000)
        activeClients.toList().forEach { it.join(3000) }
        assertNull("Loopback server failure", serverFailure.get())
    }

    @Test fun actualDownloadAndUploadMatchServerBytes() {
        val transfer = V140SpeedTransfer()
        val down = transfer.download("$url/down", 256 * 1024) {}
        val up = transfer.upload("$url/up", 64 * 1024) {}
        assertEquals(256 * 1024L, down.bytes)
        assertEquals(64 * 1024L, up.bytes)
        assertEquals(64 * 1024, uploaded.get())
        assertTrue(down.mbps.isFinite() && down.mbps > 0)
        assertTrue(up.mbps.isFinite() && up.mbps > 0)
    }
    @Test fun incompleteDownloadCannotProduceResult() {
        assertThrows(IllegalStateException::class.java) {
            V140SpeedTransfer().download("$url/down", 512 * 1024) {}
        }
    }
    @Test fun redirectIsNotFollowed() {
        assertThrows(IllegalStateException::class.java) {
            V140SpeedTransfer().download("$url/redirect", 256 * 1024) {}
        }
        assertEquals(0, requests.get())
    }
    @Test fun blockedRouteNeverOpensConnection() {
        assertThrows(IllegalStateException::class.java) {
            V140SpeedTransfer().download("$url/down", 256 * 1024) { error("VPN lost") }
        }
        assertEquals(0, requests.get())
    }
    @Test fun cancelledRunStaysCancelledAfterNewRun() {
        val old = V140SpeedTransfer()
        old.cancel()
        V140SpeedTransfer().download("$url/down", 256 * 1024) {}
        assertThrows(CancellationException::class.java) {
            old.download("$url/down", 256 * 1024) {}
        }
        assertEquals(1, requests.get())
    }
    @Test fun liveReadingsComeFromActualTransferredBytes() {
        val readings = mutableListOf<V140SpeedTransfer.Sample>()
        val transfer = V140SpeedTransfer()
        val verifiedChunks = AtomicInteger()
        val down = transfer.downloadLive("$url/down", 256 * 1024,
            { verifiedChunks.incrementAndGet() }, readings::add)
        assertTrue("VPN route must be rechecked throughout the live download",
            verifiedChunks.get() > 2)
        assertTrue(readings.isNotEmpty())
        assertEquals(down.bytes, readings.last().bytes)
        assertTrue(readings.all { it.bytes in 1L..down.bytes && it.nanos > 0L })
        assertTrue(readings.zipWithNext().all { (a, b) -> b.bytes >= a.bytes })

        readings.clear()
        val up = transfer.uploadLive("$url/up", 64 * 1024, {}, readings::add)
        assertTrue(readings.isNotEmpty())
        assertEquals(up.bytes, readings.last().bytes)
        assertEquals(64 * 1024, uploaded.get())
    }

    @Test fun cancelledByLiveCallbackMustNeverReturnSuccessfulSpeed() {
        val transfer = V140SpeedTransfer()
        assertThrows(CancellationException::class.java) {
            transfer.downloadLive("$url/down", 256 * 1024, {}) { _ -> transfer.cancel() }
        }
        assertTrue(transfer.isCancelled())
    }

    @Test fun fourStreamGigabitTestMeasuresAggregateActualBytes() {
        val count = AtomicInteger()
        val samples = Collections.synchronizedList(
            mutableListOf<V140SpeedTransfer.Sample>())
        val transfer = V140SpeedTransfer()
        val down = V144GigabitTransfer.measure(
            transfer, "$url/down", 256 * 1024, false,
            { count.incrementAndGet() }, samples::add)
        assertEquals(4L * 256 * 1024, down.bytes)
        assertEquals(4, requests.get())
        assertTrue("All workers must re-verify the route", count.get() > 8)
        assertTrue(samples.isNotEmpty())
        assertEquals(down.bytes, samples.last().bytes)
        assertTrue(down.mbps > 0.0 && down.mbps.isFinite())

        val up = V144GigabitTransfer.measure(
            transfer, "$url/up", 256 * 1024, true, {}, {})
        assertEquals(4L * 256 * 1024, up.bytes)
        assertEquals(4 * 256 * 1024, uploaded.get())
    }

    @Test fun forbiddenCloudflareDownloadIsTypedRemoteRejection() {
        val error = assertThrows(V146SpeedServerException::class.java) {
            V140SpeedTransfer().download("$url/forbidden", 32) {}
        }
        assertEquals(403, error.httpStatus)
    }

    @Test fun fixedFileRangeReadsExactlyBoundedBytesWithVPNVerification() {
        val transfer = V140SpeedTransfer()
        val checkCalls = AtomicInteger()
        val samples = mutableListOf<V140SpeedTransfer.Sample>()
        val downloaded = transfer.downloadFilePrefixLive(
            "$url/range", 256 * 1024, { checkCalls.incrementAndGet() }, samples::add)
        assertEquals(256L * 1024L, downloaded.bytes)
        assertTrue(checkCalls.get() >= 3)
        assertEquals(downloaded.bytes, samples.last().bytes)
        val two = V144GigabitTransfer.measureWithStreams(
            transfer, "$url/range", 256 * 1024, false, {}, 2, {}, true)
        assertEquals(512L * 1024L, two.bytes)
        assertTrue(two.mbps.isFinite())
    }

    @Test fun parallel403PreservesRealHttpStatusForAlternativeProvider() {
        val transfer = V140SpeedTransfer()
        val error = assertThrows(V146SpeedServerException::class.java) {
            V144GigabitTransfer.measureWithStreams(
                transfer, "$url/forbidden", 256 * 1024, false, {}, 2, {})
        }
        assertEquals(403, error.httpStatus)
        assertFalse("Remote 403 must not mean VPN cancellation", transfer.isCancelled())
    }

    @Test fun gigabitSampleSizingHonorsRealBudgetAndNoArtificial250MbpsCeiling() {
        assertEquals(8 * 1024 * 1024,
            V144GigabitTransfer.downloadBytesPerStream(15.0))
        assertEquals(64 * 1024 * 1024,
            V144GigabitTransfer.downloadBytesPerStream(500.0))
        assertEquals(128 * 1024 * 1024,
            V144GigabitTransfer.downloadBytesPerStream(1_000.0))
        assertEquals(8 * 1024 * 1024,
            V144GigabitTransfer.uploadBytesPerStream(1_000.0))
    }

    @Test fun parallelCancellationPreventsAnySuccessfulReading() {
        expectClientAbort.set(true)
        val transfer = V140SpeedTransfer()
        assertThrows(CancellationException::class.java) {
            V144GigabitTransfer.measure(
                transfer, "$url/down", 256 * 1024, false, {},
                { transfer.cancel() })
        }
        assertTrue(transfer.isCancelled())
    }

    @Test fun throttledRouteGuardChecksAtFixedIntervalAndFailCloses() {
        var now = 1_000_000_000L
        var checks = 0
        var blocked = false
        val guard = V145RouteGuard({
            checks++
            if (blocked) throw IllegalStateException("VPN network lost")
        }, { now })
        repeat(1000) { guard.checkIfDue() }
        assertEquals("Repeated 64 KiB chunks must not flood VPN state probes", 0, checks)
        now += 124_000_000L
        guard.checkIfDue()
        assertEquals(0, checks)
        now += 1_000_000L
        guard.checkIfDue()
        assertEquals(1, checks)
        blocked = true
        now += 125_000_000L
        assertThrows(IllegalStateException::class.java) { guard.checkIfDue() }
        assertEquals(2, checks)
        assertThrows(IllegalStateException::class.java) { guard.force() }
        assertEquals(3, checks)
    }

    @Test fun twoStreamDiagnosticIsActualTransferAndRetainsRouteChecks() {
        val verified = AtomicInteger()
        val parent = V140SpeedTransfer()
        val result = V144GigabitTransfer.measureWithStreams(
            parent, "$url/down", 256 * 1024, false,
            { verified.incrementAndGet() }, 2, {})
        assertEquals(2L * 256L * 1024L, result.bytes)
        assertEquals(2, requests.get())
        assertTrue(verified.get() >= 6)
        assertTrue(result.mbps.isFinite() && result.mbps > 0.0)
    }

    @Test fun diagnosticRejectsInvalidStreamCountsBeforeSendingAnyPackets() {
        val parent = V140SpeedTransfer()
        for (streams in listOf(0, 5)) {
            assertThrows(IllegalArgumentException::class.java) {
                V144GigabitTransfer.measureWithStreams(
                    parent, "$url/down", 256 * 1024, false, {}, streams, {})
            }
        }
        assertEquals(0, requests.get())
    }

    @Test fun megabitsUseNanosecondDuration() {
        assertEquals(8.0, V140SpeedTransfer.Sample(1_000_000, 1_000_000_000).mbps, 0.0001)
    }
}
