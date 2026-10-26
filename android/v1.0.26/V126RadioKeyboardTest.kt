package de.epimediahub.app.ui

import androidx.compose.material3.MaterialTheme
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.LooperMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk=[28],qualifiers="w960dp-h540dp-land")
@LooperMode(LooperMode.Mode.PAUSED)
class V126RadioKeyboardTest {
    @get:Rule val compose=createComposeRule()
    @Test fun numericRowIsSeparateLargeAndEveryLetterIsReachable() {
        compose.setContent { MaterialTheme { V126RadioKeyboard("Sender suchen","",Color.Cyan,{}, {}) } }
        assertEquals("0123456789",v126RadioKeyRows[0])
        assertEquals(('A'..'Z').toSet(),v126RadioKeyRows.drop(1).joinToString("").filter { it in 'A'..'Z' }.toSet())
        for (key in "0123456789AZÄÖÜ-") compose.onNodeWithTag("radio-key-$key")
            .assertHeightIsAtLeast(48.dp).assertIsDisplayed()
    }
    @Test fun remoteKeysAndClearSubmitAnEmptySearch() {
        var result="unchanged"
        compose.setContent { MaterialTheme { V126RadioKeyboard("Sender suchen","",Color.Cyan,{}, { result=it }) } }
        compose.onNodeWithTag("radio-key-1").performClick()
        compose.onNodeWithTag("radio-key-A").performClick()
        compose.onNodeWithTag("tv-keyboard-submit").performClick()
        assertEquals("1a",result)
        compose.onNodeWithText("LÖSCHEN").performClick()
        compose.onNodeWithTag("tv-keyboard-submit").assertIsEnabled().performClick()
        assertEquals("",result)
    }
}
