package de.epimediahub.app.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.text.TextLayoutResult
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
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V117PlayerTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var root: View
    private val episode = MediaEntry("18", "Lie To Me S02 E18 Il Sospetto Ita-Eng Webmux DD5 1", MediaKind.EPISODE,
        categoryId = "Lie to Me", seriesId = "lie-to-me", season = 2, episode = 18, sourceProfileId = "playlist")
    private val next = episode.copy(id = "19", episode = 19, name = "Die nächste Folge")
    private val playback = mutableStateOf(V115PlaybackUiState(positionMs = 300_000, durationMs = 2_400_000, playing = true))
    private val markers = mutableStateOf<List<V115Segment>>(emptyList())
    private val error = mutableStateOf("")
    private val switched = mutableListOf<MediaEntry>()
    private val skipped = mutableListOf<V115Segment>()
    private var toggles = 0
    private val intro = V115Segment(V115SegmentKind.INTRO, 30_000, 90_000, "reviewed", true, 1.0)
    private val credits = V115Segment(V115SegmentKind.OUTRO, 2_300_000, 2_400_000, "reviewed", true, 1.0)

    private fun screen(tv: Boolean = true, movie: Boolean = false, last: Boolean = false) {
        compose.setContent {
            val mode = LocalInputModeManager.current; val view = LocalView.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard); root = view }
            MaterialTheme {
                V115PlayerChrome(if (movie) episode.copy(kind = MediaKind.MOVIE) else episode,
                    if (movie) emptyList() else if (last) listOf(episode) else listOf(episode, next),
                    playback.value, markers.value, tv, error.value,
                    onBack = {}, onPlayPause = {
                        toggles++; val play = !playback.value.playWhenReady
                        playback.value = playback.value.copy(playWhenReady = play, playing = play)
                    }, onSeekBy = { playback.value = playback.value.copy(positionMs = playback.value.positionMs + it) },
                    onSeekTo = { playback.value = playback.value.copy(positionMs = it) },
                    onEpisode = { switched += it }, onTrack = {}, onSubtitlesOff = {},
                    onSkipSegment = { segment -> skipped += segment; playback.value = playback.value.copy(positionMs = segment.endMs, playing = true, playWhenReady = true) },
                    skipTools = { close -> TextButton(onClick = close, modifier = Modifier.testTag("fixture-skip-close")) { Text("Schließen") } }
                ) { modifier -> Box(modifier.background(Color(0xFF18354D))) }
            }
        }
        settle()
    }

    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(250); compose.waitForIdle() }
    private fun position(value: Long) { compose.runOnIdle { playback.value = playback.value.copy(positionMs = value) }; settle() }
    private fun key(tag: String, key: Key) { compose.onNodeWithTag(tag).performKeyInput { keyDown(key); keyUp(key) }; settle() }
    private fun completeBounds(vararg tags: String) {
        val viewport = compose.onNodeWithTag("vod-player").getUnclippedBoundsInRoot()
        for (tag in tags) {
            compose.onNodeWithTag(tag).assertIsDisplayed()
            val bounds = compose.onNodeWithTag(tag).getUnclippedBoundsInRoot()
            assertTrue("$tag must fit completely in the viewport: $bounds / $viewport",
                bounds.left >= viewport.left && bounds.right <= viewport.right && bounds.top >= viewport.top && bounds.bottom <= viewport.bottom)
        }
    }
    private fun allControls() {
        completeBounds("vod-play-pause", "vod-rewind", "vod-forward", "vod-next", "vod-audio", "vod-skip-tools", "vod-episodes", "vod-timeline")
        for (text in listOf("Nächste Folge", "Audio & Untertitel", "Intro & Abspann", "Folgen")) {
            compose.onNodeWithText(text, useUnmergedTree = true).performSemanticsAction(SemanticsActions.GetTextLayoutResult) { action ->
                val layouts = mutableListOf<TextLayoutResult>()
                assertTrue(action(layouts))
                assertFalse("$text must not be clipped", layouts.single().hasVisualOverflow)
            }
        }
    }
    private fun screenshot(name: String) {
        lateinit var bitmap: Bitmap
        compose.runOnIdle { bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888); root.draw(Canvas(bitmap)) }
        File("build/reports/ui").mkdirs()
        File("build/reports/ui", name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    @Test fun everySeriesControlFitsOnTheTvWithoutScrolling() {
        screen(); allControls(); screenshot("v117-player-tv.png")
    }

    @Test @Config(qualifiers = "w640dp-h360dp-land")
    fun controlsAlsoFitOnACompactTv() {
        screen(); allControls(); screenshot("v117-player-compact-tv.png")
    }

    @Test @Config(qualifiers = "w360dp-h720dp-port")
    fun phoneSeriesControlsIncludingNextAndSkipEditorFitWithoutScrolling() {
        screen(tv = false); allControls(); screenshot("v117-player-phone.png")
    }

    @Test fun filmControlsFitAndHaveNoEpisodeChange() {
        screen(movie = true)
        completeBounds("vod-play-pause", "vod-rewind", "vod-forward", "vod-audio", "vod-skip-tools")
        compose.onNodeWithTag("vod-next").assertDoesNotExist()
        compose.onNodeWithTag("vod-episodes").assertDoesNotExist()
    }

    @Test fun anIntroAppearanceFocusesItsButtonAndOneOkSkipsWithHiddenControls() {
        markers.value = listOf(intro); playback.value = playback.value.copy(positionMs = 20_000)
        screen(); compose.mainClock.advanceTimeBy(5_200); settle()
        compose.onNodeWithTag("vod-play-pause").assertDoesNotExist()
        position(30_000)
        compose.onNodeWithTag("vod-skip-intro").assertIsFocused().assert(SemanticsMatcher.expectValue(V114FocusVisible, true))
        screenshot("v117-intro-focused-tv.png")
        key("vod-skip-intro", Key.Enter)
        assertEquals(listOf(intro), skipped); assertEquals(0, toggles)
        assertEquals(90_000L, playback.value.positionMs)
        compose.onNodeWithTag("vod-skip-intro").assertDoesNotExist()
    }

    @Test fun introDoesNotRepeatedlyStealFocusWhileItRemainsVisible() {
        markers.value = listOf(intro); playback.value = playback.value.copy(positionMs = 45_000)
        screen()
        compose.onNodeWithTag("vod-skip-intro").assertIsFocused()
        key("vod-skip-intro", Key.DirectionDown)
        compose.onNodeWithTag("vod-timeline").assertIsFocused()
        position(46_000)
        compose.onNodeWithTag("vod-timeline").assertIsFocused()
        position(95_000); position(40_000)
        compose.onNodeWithTag("vod-skip-intro").assertIsFocused()
    }

    @Test fun aNewIntroWaitsForTheAudioDialogToCloseBeforeTakingFocus() {
        markers.value = listOf(intro); playback.value = playback.value.copy(positionMs = 20_000)
        screen(); compose.onNodeWithTag("vod-audio").performClick(); settle()
        position(40_000)
        compose.onNodeWithTag("track-subtitles-off").assertIsFocused()
        compose.onNodeWithTag("vod-track-close").performClick(); settle()
        compose.onNodeWithTag("vod-skip-intro").assertIsFocused()
    }

    @Test fun verifiedCreditsShowTheCountdownAndAdvanceBeforeTheEndExactlyOnce() {
        markers.value = listOf(credits); playback.value = playback.value.copy(positionMs = 2_299_000)
        screen(); compose.onNodeWithTag("vod-next-card").assertDoesNotExist()
        position(2_300_000)
        completeBounds("vod-next-card", "vod-card-next", "vod-cancel-next")
        compose.onNodeWithText("Nächste Folge in 10 Sekunden").assertIsDisplayed()
        screenshot("v117-credits-countdown-tv.png")
        position(2_305_000); assertTrue(switched.isEmpty())
        compose.onNodeWithText("Nächste Folge in 5 Sekunden").assertIsDisplayed()
        position(2_310_000); assertEquals(listOf(next), switched)
        position(2_399_000); assertEquals(1, switched.size)
    }

    @Test fun creditsCountdownRemainsCancellableAndManualNextStillWorks() {
        markers.value = listOf(credits); playback.value = playback.value.copy(positionMs = 2_300_000)
        screen(); compose.onNodeWithTag("vod-cancel-next").performClick(); settle()
        position(2_320_000)
        compose.runOnIdle { playback.value = playback.value.copy(ended = true, playing = false) }; settle()
        compose.mainClock.advanceTimeBy(15_000); settle(); assertTrue(switched.isEmpty())
        compose.onNodeWithTag("vod-card-next").performClick(); settle(); assertEquals(listOf(next), switched)
    }

    @Test fun pauseAndBufferingDoNotConsumeTheCreditCountdown() {
        markers.value = listOf(credits); playback.value = playback.value.copy(positionMs = 2_300_000)
        screen()
        compose.runOnIdle { playback.value = playback.value.copy(playing = false, playWhenReady = false) }; settle()
        compose.mainClock.advanceTimeBy(15_000); settle(); assertTrue(switched.isEmpty())
        compose.onNodeWithText("Nächste Folge in 10 Sekunden").assertIsDisplayed()
        compose.runOnIdle { playback.value = playback.value.copy(playing = false, playWhenReady = true, buffering = true, positionMs = 2_311_000) }; settle()
        assertTrue(switched.isEmpty())
        compose.runOnIdle { playback.value = playback.value.copy(playing = true, buffering = false) }; settle()
        assertEquals(listOf(next), switched)
    }

    @Test fun unknownCreditsCountToTheRealEndWithNoAdditionalTenSecondWait() {
        playback.value = playback.value.copy(positionMs = 2_389_000)
        screen(); compose.onNodeWithTag("vod-next-card").assertDoesNotExist()
        position(2_391_000)
        compose.onNodeWithText("Nächste Folge in 9 Sekunden").assertIsDisplayed()
        compose.mainClock.advanceTimeBy(20_000); settle(); assertTrue(switched.isEmpty())
        compose.runOnIdle { playback.value = playback.value.copy(positionMs = 2_400_000, ended = true, playing = false) }; settle()
        assertEquals(listOf(next), switched)
    }

    @Test fun browsingEpisodesDuringCreditsCancelsTheAutomaticChange() {
        markers.value = listOf(credits); playback.value = playback.value.copy(positionMs = 2_300_000)
        screen(); compose.onNodeWithTag("vod-episodes").performClick(); settle()
        position(2_320_000)
        compose.onNodeWithTag("vod-episode-dialog").assertIsDisplayed(); assertTrue(switched.isEmpty())
    }

    @Test fun aPlaybackErrorCannotAutomaticallyChangeTheEpisode() {
        markers.value = listOf(credits); playback.value = playback.value.copy(positionMs = 2_300_000)
        screen(); compose.runOnIdle { error.value = "Wiedergabe unterbrochen" }; settle()
        position(2_320_000); assertTrue(switched.isEmpty())
    }

    @Test fun theLastEpisodeAndFilmsHaveNoAutoplayCountdown() {
        markers.value = listOf(credits); playback.value = playback.value.copy(positionMs = 2_300_000)
        screen(last = true); position(2_399_000)
        compose.onNodeWithTag("vod-next-card").assertDoesNotExist(); assertTrue(switched.isEmpty())
    }
}
