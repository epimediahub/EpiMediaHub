package de.epimediahub.app.ui

import androidx.media3.common.*
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import java.lang.reflect.Proxy

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V115TracksTest {
    private val audio = TrackGroup("audio", Format.Builder().setSampleMimeType("audio/aac").setLanguage("deu").setChannelCount(2).build(),
        Format.Builder().setSampleMimeType("audio/ac3").setLanguage("ita").setChannelCount(6).build(),
        Format.Builder().setSampleMimeType("audio/bad").setLanguage("eng").build())
    private val text = TrackGroup("text", Format.Builder().setSampleMimeType("text/vtt").setLanguage("de").build(),
        Format.Builder().setSampleMimeType("text/vtt").setLanguage("en").build())
    private val tracks = Tracks(listOf(
        Tracks.Group(audio, false, intArrayOf(C.FORMAT_HANDLED, C.FORMAT_HANDLED, C.FORMAT_UNSUPPORTED_TYPE), booleanArrayOf(true, false, false)),
        Tracks.Group(text, false, intArrayOf(C.FORMAT_HANDLED, C.FORMAT_HANDLED), booleanArrayOf(true, false))))
    private var parameters = TrackSelectionParameters.Builder(ApplicationProvider.getApplicationContext()).build()
    private fun player(): Player = Proxy.newProxyInstance(Player::class.java.classLoader, arrayOf(Player::class.java)) { _, method, args ->
        when (method.name) {
            "getTrackSelectionParameters" -> parameters
            "setTrackSelectionParameters" -> { parameters = args!![0] as TrackSelectionParameters; null }
            else -> throw AssertionError("Unexpected player call: ${method.name}")
        }
    } as Player

    @Test fun onlySupportedOfferedTracksAreListedWithReadableLanguageNames() {
        val choices = V115Tracks.choices(tracks, C.TRACK_TYPE_AUDIO)
        assertEquals(2, choices.size)
        assertTrue(choices[0].label.contains("Deutsch") && choices[0].label.contains("Stereo"))
        assertTrue(choices[1].label.contains("Italienisch") && choices[1].label.contains("5.1"))
        assertEquals("it", choices[1].language)
        assertTrue(V115Tracks.choices(Tracks.EMPTY, C.TRACK_TYPE_TEXT).isEmpty())
    }

    @Test fun switchingAudioDoesNotChangeSubtitleSelection() {
        parameters = parameters.buildUpon().setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true).build()
        V115Tracks.select(player(), V115Tracks.choices(tracks, C.TRACK_TYPE_AUDIO)[1])
        assertEquals(listOf(1), parameters.overrides[audio]!!.trackIndices)
        assertTrue(parameters.disabledTrackTypes.contains(C.TRACK_TYPE_TEXT))
    }

    @Test fun subtitlesCanBeDisabledAndEnabledWithoutChangingAudio() {
        val p = player()
        V115Tracks.select(p, V115Tracks.choices(tracks, C.TRACK_TYPE_AUDIO)[1])
        V115Tracks.select(p, V115Tracks.choices(tracks, C.TRACK_TYPE_TEXT)[1])
        assertEquals(listOf(1), parameters.overrides[text]!!.trackIndices)
        V115Tracks.subtitlesOff(p)
        assertTrue(parameters.disabledTrackTypes.contains(C.TRACK_TYPE_TEXT))
        assertNull(parameters.overrides[text]); assertNotNull(parameters.overrides[audio])
        V115Tracks.select(p, V115Tracks.choices(tracks, C.TRACK_TYPE_TEXT)[0])
        assertFalse(parameters.disabledTrackTypes.contains(C.TRACK_TYPE_TEXT))
        assertEquals(listOf(0), parameters.overrides[text]!!.trackIndices)
    }
}
