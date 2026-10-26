package de.epimediahub.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import de.epimediahub.app.model.MediaCategory
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
class V127CategoryTest {
    @get:Rule val compose = createComposeRule()
    private val accent = Color(0xFF32B9EE)
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(200); compose.waitForIdle() }

    @Test fun categoryTextAndNeighboursKeepTheirBoundsAcrossFocusChanges() {
        val first = FocusRequester(); val second = FocusRequester()
        compose.setContent {
            val mode = LocalInputModeManager.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme {
                Column(Modifier.width(190.dp)) {
                    V071CategoryRailItem("DE: Dokumentationen und Hintergrund", false, accent, Modifier.focusRequester(first)) {}
                    V071CategoryRailItem("IT: Serie", false, accent, Modifier.focusRequester(second)) {}
                }
            }
        }
        settle()
        val labels = listOf("DE: Dokumentationen und Hintergrund", "IT: Serie")
        val before = labels.map { compose.onNodeWithText(it).getUnclippedBoundsInRoot() }
        compose.runOnIdle { first.requestFocus() }; settle()
        assertEquals(before, labels.map { compose.onNodeWithText(it).getUnclippedBoundsInRoot() })
        compose.runOnIdle { second.requestFocus() }; settle()
        assertEquals(before, labels.map { compose.onNodeWithText(it).getUnclippedBoundsInRoot() })
    }

    @Test fun repeatedDpadNavigationScrollsTheLiveCategoriesAndKeepsSelection() {
        val categories = (0 until 50).map { MediaCategory("category-$it", "Kategorie $it") }
        val selected = mutableStateOf(categories.first().id)
        val memory = "v127-live-category-test"
        compose.setContent {
            val mode = LocalInputModeManager.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme {
                V076CategoryPane(categories, memory, memory, selected.value, accent,
                    onCategory = { selected.value = it.id }, modifier = Modifier.width(226.dp).height(310.dp))
            }
        }
        settle()
        repeat(20) { index ->
            compose.onNodeWithTag("live-category-Kategorie $index").performKeyInput {
                keyDown(Key.DirectionDown); keyUp(Key.DirectionDown)
            }
            settle()
        }
        compose.onNodeWithTag("live-category-Kategorie 20").assertIsFocused().assertIsDisplayed()
        assertEquals("category-20", selected.value)
        assertEquals("category-20", V111MenuMemory.id(memory))
        assertTrue(V111MenuMemory.scroll(memory).first > 0)
    }

    @Test fun posterAnimationDoesNotRecomposeItsContentOnEveryFrame() {
        var compositions = 0
        val focus = FocusRequester()
        compose.mainClock.autoAdvance = false
        compose.setContent {
            val mode = LocalInputModeManager.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard) }
            val measuredModifier = remember {
                Modifier.composed { SideEffect { compositions++ }; Modifier.focusRequester(focus) }
            }
            MaterialTheme {
                V060Poster(MediaEntry("127", "Poster", MediaKind.SERIES), accent, true,
                    rememberedFocus = measuredModifier) {}
            }
        }
        compose.mainClock.advanceTimeBy(200); compose.waitForIdle()
        compose.runOnIdle { focus.requestFocus() }
        compose.mainClock.advanceTimeByFrame(); compose.waitForIdle()
        val start = compositions
        compose.mainClock.advanceTimeBy(100); compose.waitForIdle()
        assertEquals("Animation frames should only redraw the layer and border", start, compositions)
        compose.onNodeWithTag("poster-legacy:SERIES:127").assertIsFocused()
    }
}
