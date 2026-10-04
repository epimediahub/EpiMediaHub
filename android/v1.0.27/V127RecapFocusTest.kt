package de.epimediahub.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
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
import org.robolectric.annotation.LooperMode

@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@LooperMode(LooperMode.Mode.PAUSED)
class V127RecapFocusTest {
    @get:Rule val compose = createComposeRule()
    private val episode = MediaEntry("127", "Serie", MediaKind.EPISODE, seriesId = "series", season = 1, episode = 1)
    private val recap = V115Segment(V115SegmentKind.RECAP, 10_000, 30_000, "reviewed", true, 1.0)
    private val intro = V115Segment(V115SegmentKind.INTRO, 35_000, 85_000, "reviewed", true, 1.0)
    private val playback = mutableStateOf(V115PlaybackUiState(positionMs = 1_000, durationMs = 2_400_000, playing = true))
    private val markers = mutableStateOf(listOf(recap, intro))
    private val skipped = mutableListOf<V115Segment>()
    private var toggles = 0

    private fun screen(tv: Boolean = true) {
        compose.setContent {
            val mode = LocalInputModeManager.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme {
                V115PlayerChrome(episode, listOf(episode), playback.value, markers.value, tv, "",
                    onBack = {}, onPlayPause = { toggles++ }, onSeekBy = {},
                    onSeekTo = { playback.value = playback.value.copy(positionMs = it) },
                    onEpisode = {}, onTrack = {}, onSubtitlesOff = {},
                    onSkipSegment = { skipped += it; playback.value = playback.value.copy(positionMs = it.endMs) }
                ) { Box(it) }
            }
        }
        settle()
    }
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(250); compose.waitForIdle() }
    private fun at(value: Long) { compose.runOnIdle { playback.value = playback.value.copy(positionMs = value) }; settle() }
    private fun key(tag: String, key: Key) { compose.onNodeWithTag(tag).performKeyInput { keyDown(key); keyUp(key) }; settle() }

    @Test fun recapTakesFocusWithHiddenControlsAndOneOkSkipsWithoutPausing() {
        screen(); compose.mainClock.advanceTimeBy(5_200); settle()
        compose.onNodeWithTag("vod-play-pause").assertDoesNotExist()
        at(10_000)
        compose.onNodeWithTag("vod-skip-recap").assertIsFocused()
        key("vod-skip-recap", Key.Enter)
        assertEquals(listOf(recap), skipped)
        assertEquals(30_000L, playback.value.positionMs)
        assertEquals(0, toggles)
        compose.onNodeWithTag("vod-skip-recap").assertDoesNotExist()
        at(35_000)
        compose.onNodeWithTag("vod-skip-intro").assertIsFocused()
    }

    @Test fun aVisibleRecapDoesNotStealFocusAgainOnProgressUpdates() {
        playback.value = playback.value.copy(positionMs = 15_000); screen()
        compose.onNodeWithTag("vod-skip-recap").assertIsFocused()
        key("vod-skip-recap", Key.DirectionDown)
        compose.onNodeWithTag("vod-skip-recap").assertIsNotFocused()
        val destination = compose.onNode(isFocused()).fetchSemanticsNode().id
        at(16_000)
        assertEquals(destination, compose.onNode(isFocused()).fetchSemanticsNode().id)
        at(32_000); at(12_000)
        compose.onNodeWithTag("vod-skip-recap").assertIsFocused()
    }

    @Test fun anOpenAudioDialogKeepsFocusUntilItCloses() {
        screen(); compose.onNodeWithTag("vod-audio").performClick(); settle()
        at(12_000)
        compose.onNodeWithTag("track-subtitles-off").assertIsFocused()
        compose.onNodeWithTag("vod-track-close").performClick(); settle()
        compose.onNodeWithTag("vod-skip-recap").assertIsFocused()
    }

    @Test fun overlapUsesOneRecapTargetAndThenFocusesTheRemainingIntro() {
        markers.value = listOf(intro.copy(startMs = 10_000), recap)
        playback.value = playback.value.copy(positionMs = 15_000); screen()
        compose.onNodeWithTag("vod-skip-recap").assertIsFocused()
        compose.onNodeWithTag("vod-skip-intro").assertIsNotFocused()
        key("vod-skip-recap", Key.Enter)
        compose.onNodeWithTag("vod-skip-intro").assertIsFocused()
    }

    @Test fun touchPlaybackStillUsesTheSameSkipAction() {
        playback.value = playback.value.copy(positionMs = 12_000); screen(tv = false)
        compose.onNodeWithTag("vod-skip-recap").performClick(); settle()
        assertEquals(listOf(recap), skipped)
        assertEquals(0, toggles)
    }
}
