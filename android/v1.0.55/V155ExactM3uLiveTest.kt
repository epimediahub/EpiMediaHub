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
class V155ExactM3uLiveTest {
    private fun scan(text: String, id: String): String? =
        V155ExactM3uLive.find(BufferedReader(StringReader(text)), id)

    @Test fun findsExactStreamWithoutWholePlaylistJsonTree() {
        val url = "https://cdn.example.net/live/demo/demo/40041.m3u8?token=redacted"
        val m3u = """
            #EXTM3U
            #EXTINF:-1 group-title="TR", Turkish channel
            https://cdn.example.net/live/demo/demo/40040.ts
            #EXTINF:-1 group-title="DE", German channel
            $url
        """.trimIndent()
        assertEquals(url, scan(m3u, "40041"))
    }

    @Test fun similarStreamIdsCannotMatchEachOther() {
        val m3u = "#EXTM3U\nhttp://example.net/user/pass/142.ts\n"
        assertNull(scan(m3u, "42"))
        assertEquals("http://example.net/user/pass/142.ts", scan(m3u, "142"))
    }

    @Test fun acceptsExplicitStreamIdButRejectsOtherParametersAndSchemes() {
        assertTrue(V155ExactM3uLive.matches("https://s.example/play?stream_id=42&x=1", "42"))
        assertFalse(V155ExactM3uLive.matches("https://s.example/play?token=42", "42"))
        assertFalse(V155ExactM3uLive.matches("file:///storage/42.ts", "42"))
        assertFalse(V155ExactM3uLive.matches("https://s.example/user/pass/420.ts", "42"))
    }

    @Test fun rejectsBlankAndMalformedUrls() {
        assertNull(scan("#EXTM3U\nthis is not a URL\n", "42"))
        assertFalse(V155ExactM3uLive.matches("bad stream url", "42"))
        assertFalse(V155ExactM3uLive.matches("https://a.example/x/42.ts", ""))
    }

    @Test fun deadlineCancelsScanWithoutReadingFullList() {
        var tick = 0L
        val now = { tick++ * 1000L }
        val content = "#EXTM3U\n" + (1..50).joinToString("\n") { "https://a.example/u/p/$it.ts" }
        assertNull(V155ExactM3uLive.find(BufferedReader(StringReader(content)), "49", now))
    }
}
