package de.epimediahub.app.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color as AndroidColor
import android.view.View
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
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
class V128LoadingAndPinUiTest {
    @get:Rule val compose = createComposeRule()
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(200); compose.waitForIdle() }

    @Test fun allThreeLoadingMessagesHaveOpaqueDarkPanelsOnABrightSkin() {
        val title = mutableStateOf("Serien werden geladen …")
        lateinit var root: View
        compose.setContent {
            val view = LocalView.current
            SideEffect { root = view }
            MaterialTheme {
                Box(Modifier.fillMaxSize().background(Color.White), contentAlignment = Alignment.Center) {
                    V128LoadingPanel(title.value, "Katalog wird vorbereitet", Color.Cyan, true)
                }
            }
        }
        listOf("Serien werden geladen …", "Filme werden geladen …", "Sender werden geladen …").forEach { text ->
            compose.runOnIdle { title.value = text }; settle()
            compose.onNodeWithText(text).assertIsDisplayed()
            val panel = compose.onNodeWithTag("readable-loading-panel").fetchSemanticsNode().boundsInRoot
            lateinit var bitmap: Bitmap
            compose.runOnIdle { bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888); root.draw(Canvas(bitmap)) }
            val pixel = bitmap.getPixel((panel.left + 8).toInt(), ((panel.top + panel.bottom) / 2).toInt())
            assertTrue(AndroidColor.red(pixel) < 40 && AndroidColor.green(pixel) < 40 && AndroidColor.blue(pixel) < 45)
            assertEquals(AndroidColor.WHITE, bitmap.getPixel(2, 2))
            File("build/reports/ui").mkdirs()
            File("build/reports/ui/v128-loading-${text.substringBefore(' ')}.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
        }
    }

    @Test fun fourRemoteDigitsStayMaskedAndFocusMovesToConfirmation() {
        var submitted: String? = null
        compose.setContent {
            val mode = LocalInputModeManager.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme { V128PinEntry("PIN eingeben", Color.Cyan, false, "", {}, { submitted = it }) }
        }
        settle()
        compose.onNodeWithTag("pin-key-1").assertIsFocused()
        compose.onNodeWithTag("pin-key-1").performKeyInput {
            listOf(Key.Zero, Key.Zero, Key.Four, Key.Two).forEach { key -> keyDown(key); keyUp(key) }
        }
        settle()
        compose.onNodeWithTag("pin-confirm").assertIsFocused().assertIsEnabled()
        compose.onNodeWithText("0042").assertDoesNotExist()
        compose.onNodeWithTag("pin-masked").assertTextEquals("●●●●")
        compose.onNodeWithTag("pin-confirm").performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }
        settle(); assertEquals("0042", submitted)
    }

    @Test fun wrongPinClearsTheInputAndStartsWithTheFirstDigitAgain() {
        val error = mutableStateOf("")
        compose.setContent { MaterialTheme { V128PinEntry("PIN eingeben", Color.Cyan, false, error.value, {}, {}) } }
        settle()
        listOf("1", "2", "3", "4").forEach { compose.onNodeWithTag("pin-key-$it").performClick() }
        settle()
        compose.runOnIdle { error.value = "PIN falsch. Bitte erneut eingeben." }; settle()
        compose.onNodeWithTag("pin-masked").assertTextEquals("○○○○")
        compose.onNodeWithTag("pin-confirm").assertIsNotEnabled()
        compose.onNodeWithText("PIN falsch. Bitte erneut eingeben.").assertIsDisplayed()
    }
}
