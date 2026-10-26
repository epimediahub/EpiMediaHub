package de.epimediahub.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import de.epimediahub.app.data.RadioQuery
import de.epimediahub.app.radio.RadioPlaybackState
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode

@OptIn(ExperimentalComposeUiApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@LooperMode(LooperMode.Mode.PAUSED)
class V125RadioSearchTest {
    @get:Rule val compose = createComposeRule()

    @Test fun clearingTvRadioSearchCanBeConfirmedWithoutLosingOtherFilters() {
        val ui = mutableStateOf(RadioUiState(query = RadioQuery(name = "epi", countryCode = "IT", language = "italian")))
        compose.setContent {
            val input = LocalInputModeManager.current
            SideEffect { input.requestInputMode(InputMode.Keyboard) }
            MaterialTheme(colorScheme = darkColorScheme()) {
                RadioContent(ui.value, RadioPlaybackState(), true, Color.Cyan,
                    RadioActions(query = { ui.value = ui.value.copy(query = it) }))
            }
        }
        compose.onNodeWithTag("radio-search").performClick()
        compose.onNodeWithText("LÖSCHEN").performClick()
        compose.onNodeWithTag("tv-keyboard-submit").assertIsEnabled().performClick()
        compose.onNodeWithTag("tv-keyboard-submit").assertDoesNotExist()
        assertEquals("", ui.value.query.name)
        assertEquals("IT", ui.value.query.countryCode)
        assertEquals("italian", ui.value.query.language)
    }

    @Test fun otherSearchesRetainTheirNonemptyRequirement() {
        compose.setContent {
            MaterialTheme { V110TvKeyboardDialog("Videos suchen", "", Color.Cyan, {}, onSubmit = {}) }
        }
        compose.onNodeWithTag("tv-keyboard-submit").assertIsNotEnabled()
    }
}
