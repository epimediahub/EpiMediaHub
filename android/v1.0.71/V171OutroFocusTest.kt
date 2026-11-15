package de.epimediahub.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
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
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode

@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V171OutroFocusTest {
    @get:Rule val compose = createComposeRule()
    private val episode = MediaEntry("88","Folge 8",MediaKind.EPISODE,
        categoryId="Serie",seriesId="serie",season=1,episode=8,sourceProfileId="playlist")
    private val next = episode.copy(id="89",name="Folge 9",episode=9)
    private val state = mutableStateOf(V115PlaybackUiState(
        positionMs=2_325_000,durationMs=2_400_000,playing=true))
    private val outgoing = mutableListOf<MediaEntry>()
    private val seeks = mutableListOf<Long>()
    private val skipped = mutableListOf<V115Segment>()
    private val outro = V115Segment(V115SegmentKind.OUTRO,
        2_300_000,2_400_000,"reviewed",true,1.0)

    private fun screen(hasNext:Boolean=true) {
        compose.setContent {
            val input=LocalInputModeManager.current
            SideEffect { input.requestInputMode(InputMode.Keyboard) }
            MaterialTheme {
                V115PlayerChrome(episode,
                    if(hasNext) listOf(episode,next) else listOf(episode),
                    state.value,listOf(outro),true,"",
                    onBack={},onPlayPause={},onSeekBy={seeks+=it},onSeekTo={seeks+=it},
                    onEpisode={outgoing+=it},onTrack={},onSubtitlesOff={},
                    onSkipSegment={skipped+=it},
                    skipTools=null
                ) { Box(it) }
            }
        }
        settle()
    }
    private fun settle() {
        compose.waitForIdle()
        compose.mainClock.advanceTimeBy(250)
        compose.waitForIdle()
    }
    private fun key(tag:String,key:Key) {
        compose.onNodeWithTag(tag).performKeyInput { keyDown(key);keyUp(key) }
        settle()
    }

    @Test fun fromFocusedOutroSkipRightSelectsNextAndOkOpensItWithoutSeek() {
        screen()
        compose.onNodeWithTag("vod-skip-outro").assertIsDisplayed()
        compose.onNodeWithTag("vod-outro-next").assertIsDisplayed()
        compose.mainClock.advanceTimeBy(5_200);settle()
        compose.onNodeWithTag("vod-play-pause").assertDoesNotExist()
        compose.onNodeWithTag("vod-skip-outro").performSemanticsAction(
            androidx.compose.ui.semantics.SemanticsActions.RequestFocus)
        settle()
        compose.onNodeWithTag("vod-skip-outro").assertIsFocused()
        key("vod-skip-outro",Key.DirectionRight)
        compose.onNodeWithTag("vod-outro-next").assertIsFocused()
        assertTrue("DPAD_RIGHT must not seek while an action is focused",seeks.isEmpty())
        key("vod-outro-next",Key.Enter)
        assertEquals(listOf(next),outgoing)
        assertTrue(seeks.isEmpty())
        assertTrue(skipped.isEmpty())
    }

    @Test fun leftReturnsToOutroSkipWithoutSkippingOrSeeking() {
        screen()
        compose.onNodeWithTag("vod-outro-next").performSemanticsAction(
            androidx.compose.ui.semantics.SemanticsActions.RequestFocus)
        settle()
        key("vod-outro-next",Key.DirectionLeft)
        compose.onNodeWithTag("vod-skip-outro").assertIsFocused()
        assertTrue(seeks.isEmpty())
    }

    @Test fun noNextEpisodeMeansNoExtraOutroNextButton() {
        screen(false)
        compose.onNodeWithTag("vod-skip-outro").assertIsDisplayed()
        compose.onNodeWithTag("vod-outro-next").assertDoesNotExist()
    }

    @Test fun nextCountdownCardKeepsItsOwnFocus() {
        state.value=state.value.copy(positionMs=2_360_000)
        screen()
        compose.onNodeWithTag("vod-next-card").assertIsDisplayed()
        compose.onNodeWithTag("vod-card-next").assertIsFocused()
        compose.onNodeWithTag("vod-outro-next").assertDoesNotExist()
    }
}
