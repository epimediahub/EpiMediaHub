package de.epimediahub.app.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class V176SmartTubeQualityTest {
    @Test fun supportsOnlyRealAdaptiveHeights() {
        assertEquals(listOf(2160,1080,720,480),
            V176SmartTubeQuality.supportedHeights(
                listOf(720,1080,2160,1080,480,-1), "mpd"))
        assertEquals(listOf(1080,720),
            V176SmartTubeQuality.supportedHeights(listOf(720,1080), "M3U8"))
    }

    @Test fun fixedStreamsDoNotOfferFalseControls() {
        assertTrue(V176SmartTubeQuality.supportedHeights(listOf(1080), "mpd").isEmpty())
        assertTrue(V176SmartTubeQuality.supportedHeights(listOf(2160,1080), "mp4").isEmpty())
        assertTrue(V176SmartTubeQuality.supportedHeights(listOf(2160,1080), "webm").isEmpty())
    }

    @Test fun unknownAndUnsupportedHeightsHidden() {
        assertTrue(V176SmartTubeQuality.supportedHeights(
            listOf(0, -1, 720), "mpd").isEmpty())
        assertEquals(listOf(2160,720),
            V176SmartTubeQuality.supportedHeights(
                listOf(-1, 0, 5000,2160,720), "m3u8"))
    }

    @Test fun humanReadableLabels() {
        assertEquals("Automatisch",V176SmartTubeQuality.label(null))
        assertEquals("1080p",V176SmartTubeQuality.label(1080))
    }
}
