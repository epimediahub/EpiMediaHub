package de.epimediahub.app.ui

import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.width
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.ExperimentalTestApi
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsFocused
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithTag
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.onRoot
import androidx.compose.ui.test.performKeyInput
import androidx.compose.ui.test.performSemanticsAction
import androidx.compose.ui.test.printToString
import androidx.compose.ui.unit.dp
import de.epimediahub.app.model.MediaCategory
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode

/** Exercises the actual Live TV panes with remote-control keys and state updates. */
@OptIn(ExperimentalTestApi::class, ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V113LiveTvNavigationTest {
    @get:Rule val compose = createComposeRule()

    private class Fixture {
        var playlist by mutableStateOf("playlist-${System.nanoTime()}")
        var category by mutableStateOf("a")
        var visible by mutableStateOf(true)
        val selections = mutableStateMapOf<String, String>()
        fun selected() = selections["$playlist:$category"] ?: "$category-0"
        fun tag(index: Int) = "live-channel:$category-$index"
    }

    private fun screen(): Fixture {
        val fixture = Fixture()
        compose.setContent {
            val inputMode = LocalInputModeManager.current
            SideEffect { inputMode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme {
                if (fixture.visible) {
                    val categories = listOf(MediaCategory("a", "Kategorie A"), MediaCategory("b", "Kategorie B"))
                    val channels = (0 until 100).map { index ->
                        MediaEntry(
                            id = "${fixture.category}-$index", name = "Sender ${index + 1}",
                            kind = MediaKind.LIVE, categoryId = fixture.category, sourceProfileId = fixture.playlist
                        )
                    }
                    Row(Modifier.width(800.dp).height(350.dp)) {
                        V076CategoryPane(
                            categories = categories,
                            selectedId = fixture.category,
                            memoryKey = V113LiveTvKeys.categories(fixture.playlist),
                            focusScope = V113LiveTvKeys.focus(fixture.playlist),
                            accent = Color.Cyan,
                            onCategory = { fixture.category = it.id },
                            modifier = Modifier.width(180.dp).fillMaxHeight()
                        )
                        V076ChannelPane(
                            channels = channels,
                            selectedId = fixture.selected(),
                            memoryKey = V113LiveTvKeys.channels(fixture.playlist, fixture.category),
                            focusScope = V113LiveTvKeys.focus(fixture.playlist),
                            accent = Color.Cyan,
                            isTv = true,
                            onSelected = { _, channel -> fixture.selections["${fixture.playlist}:${fixture.category}"] = channel.id },
                            onPlay = {},
                            modifier = Modifier.width(450.dp).fillMaxHeight()
                        )
                    }
                }
            }
        }
        settle()
        return fixture
    }

    private fun settle() {
        compose.waitForIdle()
        compose.mainClock.advanceTimeBy(250L)
        compose.waitForIdle()
    }

    private fun focus(fixture: Fixture, index: Int) {
        compose.onNodeWithTag(fixture.tag(index)).performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        settle()
        compose.onNodeWithTag(fixture.tag(index)).assertIsFocused().assertIsDisplayed()
    }

    private fun move(fixture: Fixture, from: Int, to: Int) {
        val step = if (to > from) 1 else -1
        val key = if (step == 1) Key.DirectionDown else Key.DirectionUp
        var index = from
        while (index != to) {
            compose.onNodeWithTag(fixture.tag(index)).performKeyInput { keyDown(key); keyUp(key) }
            compose.waitForIdle()
            index += step
            compose.onNodeWithTag(fixture.tag(index)).assertIsFocused().assertIsDisplayed()
            compose.runOnIdle { assertEquals("${fixture.category}-$index", fixture.selected()) }
        }
    }

    @Test fun dpadScrollsPastTenChannelsAndBackUp() {
        val fixture = screen()
        focus(fixture, 0)
        move(fixture, 0, 40)
        move(fixture, 40, 0)
    }

    @Test fun returningToLiveTvRestoresChannelAndScrollingContinues() {
        val fixture = screen()
        focus(fixture, 0)
        move(fixture, 0, 27)
        compose.runOnIdle { fixture.visible = false }
        settle()
        compose.runOnIdle { fixture.visible = true }
        settle()
        compose.onNodeWithTag(fixture.tag(27)).assertIsFocused().assertIsDisplayed()
        move(fixture, 27, 28)
    }

    @Test fun categoriesAndPlaylistsKeepSeparateScrollPositions() {
        val fixture = screen()
        val firstPlaylist = fixture.playlist
        focus(fixture, 0)
        move(fixture, 0, 16)
        compose.onNodeWithText("Kategorie B").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        settle()
        focus(fixture, 0)
        move(fixture, 0, 13)
        compose.onNodeWithText("Kategorie A").performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        settle()
        focus(fixture, 16)
        move(fixture, 16, 17)
        compose.runOnIdle { fixture.playlist = "second-${System.nanoTime()}" }
        settle()
        focus(fixture, 0)
        compose.runOnIdle { fixture.playlist = firstPlaylist }
        settle()
        try {
            compose.onNodeWithTag(fixture.tag(17)).assertIsFocused().assertIsDisplayed()
        } catch (failure: AssertionError) {
            val key = V113LiveTvKeys.channels(firstPlaylist, fixture.category)
            println("Returned selection=${fixture.selected()} memory=${V111MenuMemory.id(key)} scroll=${V111MenuMemory.scroll(key)} ownsFocus=${V111MenuMemory.ownsFocus(key, V113LiveTvKeys.focus(firstPlaylist))}")
            println(compose.onRoot(useUnmergedTree = true).printToString())
            throw failure
        }
        move(fixture, 17, 18)
    }
}
