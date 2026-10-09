package de.epimediahub.app.vpn

import java.net.ServerSocket
import java.net.Socket
import java.net.InetAddress
import java.io.InputStream
import java.util.concurrent.atomic.AtomicReference
import kotlin.concurrent.thread
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicInteger
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
    @Before fun setup() {
        server = ServerSocket(0, 8, InetAddress.getByName("127.0.0.1"))
        url = "http://127.0.0.1:${server.localPort}"
        worker = thread(name = "speedtest-loopback", isDaemon = true) {
            while (!server.isClosed) {
                try { server.accept().use { serve(it) } }
                catch (e: Exception) {
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
        while (true) {
            val header = line(input)
            if (header.isEmpty()) break
            if (header.startsWith("Content-Length:", ignoreCase = true))
                length = header.substringAfter(':').trim().toInt()
        }
        val output = socket.getOutputStream()
        if (request[1] == "/redirect") {
            output.write("HTTP/1.1 302 Found\r\nLocation: /down\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".toByteArray())
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
                uploaded.set(received)
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

    @Test fun megabitsUseNanosecondDuration() {
        assertEquals(8.0, V140SpeedTransfer.Sample(1_000_000, 1_000_000_000).mbps, 0.0001)
    }
}
