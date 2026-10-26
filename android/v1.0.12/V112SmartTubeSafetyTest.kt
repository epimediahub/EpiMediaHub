package de.epimediahub.app.ui

import de.epimediahub.app.data.V112PlaylistProbe
import org.junit.Assert.*
import org.junit.Test
import java.net.InetAddress
import java.net.ServerSocket
import java.nio.file.Files

class V112SmartTubeSafetyTest {
    private fun video(id: String, live: Boolean = false) = V100SmartTubeVideo(id, id, "", "", "", 100_000L, live)

    @Test fun serverReachabilityReflectsAnOpenThenClosedPort() {
        val server = ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))
        val url = "http://127.0.0.1:${server.localPort}/get.php?username=sample&password=sample"
        try { assertTrue(V112PlaylistProbe.online(url)) } finally { server.close() }
        assertFalse(V112PlaylistProbe.online(url))
    }

    @Test fun invalidEndpointsAreOffline() {
        listOf("", "not a URL", "http://", "http://127.0.0.1:0", "http://127.0.0.1:70000", "ftp://127.0.0.1")
            .forEach { assertFalse(it, V112PlaylistProbe.online(it)) }
    }

    @Test fun localPlaylistRequiresAnExistingNonEmptyFile() {
        val file = Files.createTempFile("epimediahub-playlist", ".m3u")
        try {
            assertFalse(V112PlaylistProbe.online(file.toUri().toString()))
            Files.write(file, "#EXTM3U\n".toByteArray())
            assertTrue(V112PlaylistProbe.online(file.toUri().toString()))
        } finally { Files.deleteIfExists(file) }
        assertFalse(V112PlaylistProbe.online(file.toUri().toString()))
    }

    @Test fun previewFailureAndLiveStreamAreNeverMarkedWatched() {
        assertFalse(V112SmartTubeWatchRules.isWatched(false, 0L, 100_000L, true))
        assertFalse(V112SmartTubeWatchRules.isWatched(false, 10_000L, 100_000L, false))
        assertFalse(V112SmartTubeWatchRules.isWatched(false, 89_999L, 100_000L, false))
        assertFalse(V112SmartTubeWatchRules.isWatched(false, 30_000L, -1L, false))
        assertFalse(V112SmartTubeWatchRules.isWatched(true, 100_000L, 100_000L, true))
        assertTrue(V112SmartTubeWatchRules.isWatched(false, 90_000L, 100_000L, false))
        assertTrue(V112SmartTubeWatchRules.isWatched(false, 1L, -1L, true))
    }

    @Test fun hiddenVideosAreReplacedByUnseenCandidatesAndHistoryIsRetained() {
        val rows = listOf(V100SmartTubeRow("Vorschläge", listOf(video("seen"), video("new"), video("seen"), video("live", true))))
        val shown = V112SmartTubeSuggestions.visible(rows, setOf("seen", "live"), true)
        assertEquals(listOf("new", "live"), shown.single().videos.map { it.videoId })
        assertEquals(listOf("seen", "new", "live"), V112SmartTubeSuggestions.visible(rows, setOf("seen"), false).single().videos.map { it.videoId })
        assertTrue(V112SmartTubeSuggestions.visible(listOf(V100SmartTubeRow("Leer", listOf(video("seen")))), setOf("seen"), true).isEmpty())
    }

    @Test fun autoplayKeepsItsPlaceAndSkipsWatchedVideos() {
        val rows = listOf(V100SmartTubeRow("Vorschläge", listOf(video("before"), video("current"), video("seen"), video("next"))))
        assertEquals("next", V112SmartTubeSuggestions.next(rows, "current", setOf("current", "seen"))?.videoId)
        assertNull(V112SmartTubeSuggestions.next(rows, "next", emptySet()))
        assertNull(V112SmartTubeSuggestions.next(rows, "missing", emptySet()))
    }

    @Test fun shortsCannotBeSelectedOrRestored() {
        assertFalse(V108SmartTubeSection.entries.any { it.name == "SHORTS" })
    }
}
