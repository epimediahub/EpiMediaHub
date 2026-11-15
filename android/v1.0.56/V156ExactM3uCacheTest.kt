package de.epimediahub.app.data

import java.io.BufferedReader
import java.io.StringReader
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V156ExactM3uCacheTest {
    private fun parse(text: String): Map<String, String> =
        V156ExactM3uCache.index(BufferedReader(StringReader(text)))

    @Test fun oneScanBuildsIndexForManySenderSwitches() {
        val m3u = """
            #EXTM3U
            #EXTINF:-1 group-title="TR", Test Turkish
            http://cdn.example/user/pass/1001.ts
            #EXTINF:-1 group-title="DE", Test German
            http://cdn.example/user/pass/1002.m3u8?token=redacted
            #EXTINF:-1 group-title="DE", Test another
            http://cdn.example/user/pass/1003.ts
        """.trimIndent()
        val cache = parse(m3u)
        assertEquals(3, cache.size)
        assertEquals("http://cdn.example/user/pass/1001.ts", cache["1001"])
        assertEquals("http://cdn.example/user/pass/1002.m3u8?token=redacted", cache["1002"])
        assertEquals("http://cdn.example/user/pass/1003.ts", cache["1003"])
    }

    @Test fun exactMatchingDoesNotMixNearbyIds() {
        val cache = parse("#EXTM3U\nhttp://s.example/a/b/142.ts\nhttp://s.example/a/b/42.ts")
        assertEquals("http://s.example/a/b/42.ts", cache["42"])
        assertEquals("http://s.example/a/b/142.ts", cache["142"])
    }

    @Test fun supportsNamedStreamIdAndRejectsMalformedUrls() {
        assertEquals("201", V156ExactM3uCache.streamId("https://s.example/play?stream_id=201&token=redacted"))
        assertNull(V156ExactM3uCache.streamId("file:///path/201.ts"))
        assertNull(V156ExactM3uCache.streamId("malformed URL"))
        assertTrue(parse("#EXTM3U\nnot a url\n").isEmpty())
    }

    @Test fun obeysScanDeadline() {
        var tick = 0L
        val clock = { tick++ * 1000L }
        val lines = (1..200).joinToString("\n") { "https://s.example/u/p/$it.ts" }
        val result = V156ExactM3uCache.index(
            BufferedReader(StringReader(lines)), nowMs = clock)
        assertTrue(result.size < 200)
    }

    @Test fun noCompletePlaylistBodyNeededToGetAllAvailableIds() {
        val cache = parse("#EXTM3U\nhttps://s.example/x/100.ts\nhttps://s.example/x/101.ts\n")
        assertEquals(setOf("100", "101"), cache.keys)
    }
}
