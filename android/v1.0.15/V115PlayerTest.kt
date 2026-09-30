package de.epimediahub.app.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.media3.common.*
import de.epimediahub.app.data.V115Segment
import de.epimediahub.app.data.V115SegmentKind
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V115PlayerTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var root: View
    private val episode = MediaEntry("18", "Geheimnisse", MediaKind.EPISODE, categoryId = "Dark", seriesId = "dark", season = 1, episode = 18, sourceProfileId = "playlist")
    private val episodes = (1..60).map { episode.copy(id = "$it", episode = it, name = "Episode $it") } +
        listOf(episode.copy(id = "other", episode = 19, sourceProfileId = "other-playlist"))
    private val playback = mutableStateOf(V115PlaybackUiState(positionMs = 300_000, durationMs = 2_400_000, playing = true))
    private val markers = mutableStateOf<List<V115Segment>>(emptyList())
    private var toggles = 0
    private var backs = 0
    private val seeks = mutableListOf<Long>()
    private val switched = mutableListOf<MediaEntry>()
    private val selectedTracks = mutableListOf<V115TrackChoice>()
    private var subtitlesOff = 0

    private fun screen(tv: Boolean = true, movie: Boolean = false) {
        compose.setContent {
            val mode = LocalInputModeManager.current; val view = LocalView.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard); root = view }
            MaterialTheme {
                V115PlayerChrome(if (movie) episode.copy(kind = MediaKind.MOVIE, name = "Der Film") else episode,
                    if (movie) emptyList() else episodes, playback.value, markers.value, tv, "",
                    onBack = { backs++ }, onPlayPause = {
                        toggles++; playback.value = playback.value.copy(playWhenReady = !playback.value.playWhenReady, playing = !playback.value.playWhenReady)
                    }, onSeekBy = { delta -> seeks += delta; playback.value = playback.value.copy(positionMs = (playback.value.positionMs + delta).coerceIn(0, playback.value.durationMs)) },
                    onSeekTo = { target -> seeks += target; playback.value = playback.value.copy(positionMs = target) },
                    onEpisode = { switched += it }, onTrack = { selectedTracks += it }, onSubtitlesOff = { subtitlesOff++ }) { modifier ->
                    Box(modifier.background(Brush.linearGradient(listOf(Color(0xFF0C1725), Color(0xFF415063), Color(0xFF10161C)))) , contentAlignment = Alignment.Center) {
                        Text("VIDEOBILD", color = Color.White.copy(alpha = .25f))
                    }
                }
            }
        }
        settle()
    }
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(250); compose.waitForIdle() }
    private fun key(tag: String, key: Key) { compose.onNodeWithTag(tag).performKeyInput { keyDown(key); keyUp(key) }; settle() }
    private fun screenshot(name: String) {
        lateinit var bitmap: Bitmap
        compose.runOnIdle { bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888); root.draw(Canvas(bitmap)) }
        File("build/reports/ui").mkdirs()
        File("build/reports/ui", name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    @Test fun remoteOkPausesAndKeepsTheInformationVisibleWhilePaused() {
        screen()
        compose.onNodeWithTag("vod-play-pause").assertIsFocused().assert(SemanticsMatcher.expectValue(V114FocusVisible, true))
        key("vod-play-pause", Key.Enter)
        assertEquals(1, toggles); assertFalse(playback.value.playWhenReady)
        compose.onNodeWithTag("vod-paused").assertIsDisplayed()
        compose.mainClock.advanceTimeBy(15_000); settle()
        compose.onNodeWithTag("vod-play-pause").assertIsDisplayed().assertIsFocused()
        screenshot("vod-player-paused-tv.png")
        key("vod-play-pause", Key.Enter)
        assertTrue(playback.value.playWhenReady)
    }

    @Test fun hiddenControlsCanBePausedWithOneOkWithoutDoubleActivation() {
        screen()
        compose.mainClock.advanceTimeBy(5_200); settle()
        compose.onNodeWithTag("vod-play-pause").assertDoesNotExist()
        compose.onNodeWithTag("vod-player").assertIsFocused()
        key("vod-player", Key.Enter)
        assertEquals("The release of OK must not activate the newly focused button again", 1, toggles)
        compose.onNodeWithTag("vod-paused").assertIsDisplayed()
        compose.onNodeWithTag("vod-play-pause").assertIsFocused()
    }

    @Test fun directionKeysRevealControlsAndNeverSwitchEpisodes() {
        screen()
        compose.mainClock.advanceTimeBy(5_200); settle()
        key("vod-player", Key.DirectionDown)
        compose.onNodeWithTag("vod-play-pause").assertIsFocused()
        key("vod-play-pause", Key.DirectionUp)
        compose.onNodeWithTag("vod-timeline").assertIsFocused()
        key("vod-timeline", Key.DirectionRight)
        assertEquals(listOf(10_000L), seeks)
        key("vod-timeline", Key.DirectionDown)
        assertTrue(switched.isEmpty())
        screenshot("vod-player-controls-tv.png")
    }

    @Test fun focusedSeekButtonsReceiveOkAndDoNotOnlyToggleTheOverlay() {
        screen()
        key("vod-play-pause", Key.DirectionRight)
        compose.onNodeWithTag("vod-rewind").assertIsFocused()
        key("vod-rewind", Key.Enter)
        assertEquals(290_000L, playback.value.positionMs)
        key("vod-rewind", Key.DirectionRight)
        compose.onNodeWithTag("vod-forward").assertIsFocused()
        key("vod-forward", Key.Enter)
        assertEquals(300_000L, playback.value.positionMs)
        assertEquals(0, toggles)
    }

    @Test fun skipActionsExistOnlyInsideTheirVerifiedSegmentAndSeekToItsEnd() {
        markers.value = listOf(V115Segment(V115SegmentKind.INTRO, 30_000, 90_000, "SkipDB", true, .9))
        playback.value = playback.value.copy(positionMs = 10_000)
        screen()
        compose.onNodeWithTag("vod-skip-intro").assertDoesNotExist()
        compose.runOnIdle { playback.value = playback.value.copy(positionMs = 45_000) }; settle()
        compose.onNodeWithTag("vod-skip-intro").assertIsDisplayed().performClick(); settle()
        assertEquals(90_000L, playback.value.positionMs)
        compose.onNodeWithTag("vod-skip-intro").assertDoesNotExist()
        assertTrue(switched.isEmpty())
    }

    @Test fun episodePickerScrollsBeyondTheInitialViewportAndSelectsTheFocusedEpisode() {
        screen()
        compose.onNodeWithTag("vod-episodes").performClick(); settle()
        compose.onNodeWithTag("vod-episode-1-18").assertIsFocused()
        repeat(15) { key("vod-episode-list", Key.DirectionDown) }
        compose.onNodeWithTag("vod-episode-1-33").assertIsFocused().assertIsDisplayed()
        key("vod-episode-1-33", Key.Enter)
        assertEquals(33, switched.single().episode)
        assertEquals("playlist", switched.single().sourceProfileId)
    }

    @Test fun nextCountdownOnlyStartsAfterEndedAndCanBeCancelled() {
        playback.value = playback.value.copy(positionMs = 2_350_000)
        screen()
        compose.mainClock.advanceTimeBy(12_000); settle()
        assertTrue(switched.isEmpty())
        compose.onNodeWithTag("vod-next-card").assertDoesNotExist()
        compose.runOnIdle { playback.value = playback.value.copy(ended = true, playing = false) }; settle()
        compose.onNodeWithTag("vod-next-card").assertIsDisplayed()
        compose.onNodeWithTag("vod-cancel-next").performClick(); settle()
        compose.mainClock.advanceTimeBy(15_000); settle()
        assertTrue(switched.isEmpty())
        screenshot("vod-next-episode-tv.png")
        compose.onNodeWithTag("vod-next").performClick(); settle()
        assertEquals(19, switched.single().episode)
    }

    @Test fun reopeningEpisodePickerRestoresItsLastFocusedEpisode() {
        screen()
        compose.onNodeWithTag("vod-episodes").performClick(); settle()
        repeat(15) { key("vod-episode-list", Key.DirectionDown) }
        compose.onNodeWithTag("vod-episode-1-33").assertIsFocused()
        compose.onNodeWithTag("vod-episode-close").performClick(); settle()
        compose.onNodeWithTag("vod-episodes").assertIsFocused()
        key("vod-episodes", Key.Enter)
        compose.onNodeWithTag("vod-episode-1-33").assertIsFocused().assertIsDisplayed()
        assertTrue(switched.isEmpty())
    }

    @Test fun completedEpisodeAutomaticallyAdvancesExactlyOnce() {
        playback.value = playback.value.copy(ended = true, playing = false)
        screen()
        compose.mainClock.advanceTimeBy(11_000); settle()
        assertEquals(1, switched.size); assertEquals(19, switched.single().episode)
        compose.mainClock.advanceTimeBy(20_000); settle()
        assertEquals(1, switched.size)
    }

    @Test fun offeredAudioAndSubtitlesAreSelectableAndFocusReturnsToTheirLauncher() {
        val audio = TrackGroup("audio", Format.Builder().setSampleMimeType("audio/aac").setLanguage("de").build(), Format.Builder().setSampleMimeType("audio/aac").setLanguage("it").build())
        val text = TrackGroup("text", Format.Builder().setSampleMimeType("text/vtt").setLanguage("en").build())
        playback.value = playback.value.copy(tracks = Tracks(listOf(
            Tracks.Group(audio, false, intArrayOf(C.FORMAT_HANDLED, C.FORMAT_HANDLED), booleanArrayOf(true, false)),
            Tracks.Group(text, false, intArrayOf(C.FORMAT_HANDLED), booleanArrayOf(false)))))
        screen()
        compose.onNodeWithTag("vod-audio").performClick(); settle()
        compose.onNodeWithTag("track-audio-0").assertIsFocused()
        key("track-audio-0", Key.DirectionDown); key("track-audio-1", Key.Enter)
        assertEquals("it", selectedTracks.single().language)
        compose.onNodeWithTag("vod-audio").assertIsFocused()
        key("vod-audio", Key.Enter)
        compose.onNodeWithTag("track-subtitle-0").performClick(); settle()
        assertEquals(C.TRACK_TYPE_TEXT, selectedTracks.last().type)
        key("vod-audio", Key.Enter)
        compose.onNodeWithTag("track-subtitles-off").performClick(); settle()
        assertEquals(1, subtitlesOff)
        compose.onNodeWithTag("vod-audio").assertIsFocused()
    }

    @Test
    @Config(qualifiers = "w412dp-h800dp-port")
    fun phonePlayerShowsLargeTouchControlsAndAvailableTracks() {
        screen(tv = false, movie = true)
        compose.onNodeWithTag("vod-play-pause").assertIsDisplayed().performClick(); settle()
        compose.onNodeWithTag("vod-paused").assertIsDisplayed()
        compose.onNodeWithTag("vod-audio").assertIsDisplayed()
        screenshot("vod-player-phone.png")
        compose.onNodeWithTag("vod-audio").performClick(); settle()
        compose.onNodeWithTag("track-subtitles-off").assertIsDisplayed()
        compose.onNodeWithText("Für dieses Video wurden keine verfügbaren Untertitel angeboten.").assertIsDisplayed()
    }
}
