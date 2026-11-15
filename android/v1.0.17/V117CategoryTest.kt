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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import de.epimediahub.app.model.MediaCategory
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
class V117CategoryTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var root: View
    private val selected = mutableStateOf("")
    private val categories = listOf(MediaCategory("de", "DE: Netflix Serien"), MediaCategory("it", "IT: Netflix Serie"))

    private fun screen() {
        compose.setContent {
            val mode = LocalInputModeManager.current; val view = LocalView.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard); root = view }
            MaterialTheme {
                Box(Modifier.fillMaxSize().background(Color.White)) {
                    V071CategoryRail(categories, selected.value, Color(0xFFE50914),
                        onOverview = { selected.value = "" }, onCategory = { _, category -> selected.value = category.id })
                }
            }
        }
        compose.waitForIdle(); compose.mainClock.advanceTimeBy(400); compose.waitForIdle()
    }

    @Test fun theDarkCategoryPanelRemainsReadableAgainstTheBrightestSkin() {
        screen()
        compose.onNodeWithText("DE: Netflix Serien").assertIsDisplayed()
        compose.onNodeWithText("IT: Netflix Serie").assertIsDisplayed()
        lateinit var bitmap: Bitmap
        compose.runOnIdle { bitmap = Bitmap.createBitmap(root.width, root.height, Bitmap.Config.ARGB_8888); root.draw(Canvas(bitmap)) }
        val rail = compose.onNodeWithTag("vod-category-rail").fetchSemanticsNode().boundsInRoot
        val panelPixel = bitmap.getPixel((rail.left + 3).toInt(), (rail.bottom / 2).toInt())
        assertTrue("The skin must not shine brightly through the category panel", AndroidColor.red(panelPixel) < 45 && AndroidColor.green(panelPixel) < 45 && AndroidColor.blue(panelPixel) < 45)
        assertEquals("The rest of the skin keeps its original background", AndroidColor.WHITE, bitmap.getPixel(root.width - 3, root.height / 2))
        File("build/reports/ui").mkdirs()
        File("build/reports/ui/v117-categories-bright-skin.png").outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    @Test fun remoteFocusAndCategorySelectionStillWorkWithOpaqueRows() {
        screen()
        compose.onNodeWithText("Übersicht").assertIsFocused().performKeyInput { keyDown(Key.DirectionDown); keyUp(Key.DirectionDown) }
        compose.waitForIdle()
        compose.onNodeWithText("DE: Netflix Serien").assertIsFocused().assert(SemanticsMatcher.expectValue(V114FocusVisible, true))
            .performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }
        compose.waitForIdle(); assertEquals("de", selected.value)
    }
}
