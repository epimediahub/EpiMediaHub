package de.epimediahub.app.vpn

import com.sun.net.httpserver.HttpServer
import java.net.InetSocketAddress
import java.util.concurrent.CancellationException
import java.util.concurrent.atomic.AtomicInteger
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

/** Loopback integration tests send real HTTP bytes, without external services. */
class V140SpeedTransferTest {
    private lateinit var server: HttpServer
    private lateinit var url: String
    private val requests = AtomicInteger()
    private val uploaded = AtomicInteger()
    @Before fun setup() {
        server = HttpServer.create(InetSocketAddress("127.0.0.1", 0), 0)
        server.createContext("/down") { exchange ->
            requests.incrementAndGet()
            val data = ByteArray(256 * 1024) { (it % 251).toByte() }
            exchange.sendResponseHeaders(200, data.size.toLong())
            exchange.responseBody.use { it.write(data) }
        }
        server.createContext("/up") { exchange ->
            requests.incrementAndGet()
            assertEquals("POST", exchange.requestMethod)
            uploaded.set(exchange.requestBody.use { it.readBytes().size })
            exchange.sendResponseHeaders(200, 2)
            exchange.responseBody.use { it.write("OK".toByteArray()) }
        }
        server.createContext("/redirect") { exchange ->
            exchange.responseHeaders.add("Location", "/down")
            exchange.sendResponseHeaders(302, -1)
            exchange.close()
        }
        server.start()
        url = "http://127.0.0.1:${server.address.port}"
    }
    @After fun teardown() { server.stop(0) }

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
    @Test fun megabitsUseNanosecondDuration() {
        assertEquals(8.0, V140SpeedTransfer.Sample(1_000_000, 1_000_000_000).mbps, 0.0001)
    }
}
