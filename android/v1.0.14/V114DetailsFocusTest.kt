package de.epimediahub.app.ui

import android.graphics.Bitmap
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.getValue
import androidx.compose.runtime.setValue
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asAndroidBitmap
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
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
class V114DetailsFocusTest {
    @get:Rule val compose = createComposeRule()
    private val paragraph = "Eine Gruppe reist an einen abgelegenen Ort. Dort entdeckt sie ein Geheimnis und muss gemeinsam einen Weg nach Hause finden. "

    private fun screen(tv: Boolean = true, series: Boolean = false, description: String = paragraph.repeat(55), visible: androidx.compose.runtime.MutableState<Boolean>? = null) {
        val key = "detail-test-${System.nanoTime()}"
        compose.setContent {
            val inputMode = LocalInputModeManager.current
            SideEffect { inputMode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme {
                Box(Modifier.fillMaxSize().background(Color(0xFFFFDB55))) {
                    if (visible?.value != false) V114DetailLayout(
                        title = "Camp Miasma – Adolescenza, sesso e morte (2026) FHD",
                        description = description, accent = Color(0xFFEBC344), isTv = tv, memoryKey = key,
                        metadata = listOf("2026", "01:52", "Horror, Drama", "★ 5.9"),
                        credits = listOf("Darsteller" to "Hauptdarsteller und weitere Besetzung", "Regie" to "Regisseur"),
                        isSeries = series, favorite = false, onPlay = {}, onFavorite = {}, onTrailer = {},
                        poster = { modifier -> Box(modifier.background(Color(0xFF384459)), contentAlignment = androidx.compose.ui.Alignment.Center) { Text("FILMPOSTER", color = Color.White) } }
                    )
                }
            }
        }
        settle()
    }

    private fun settle() {
        compose.waitForIdle()
        compose.mainClock.advanceTimeBy(250L)
        compose.waitForIdle()
    }

    private fun key(tag: String, key: Key) {
        compose.onNodeWithTag(tag).performKeyInput { keyDown(key); keyUp(key) }
        settle()
    }

    private fun scroll(): Float = compose.onNodeWithTag("detail-description-body")
        .fetchSemanticsNode().config[SemanticsProperties.VerticalScrollAxisRange].value()

    private fun focus(tag: String) {
        compose.onNodeWithTag(tag).performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        settle()
    }

    private fun saveScreenshot(name: String) {
        val directory = File("build/reports/ui")
        directory.mkdirs()
        File(directory, name).outputStream().use { compose.onRoot().captureToImage().asAndroidBitmap().compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    @Test fun descriptionScrollsDownAndBackUpToPlayWithoutGettingTrapped() {
        screen()
        compose.onNodeWithTag("detail-play").assertIsFocused().assertIsDisplayed()
        key("detail-play", Key.DirectionDown)
        compose.onNodeWithTag("detail-description").assertIsFocused()
        repeat(12) { key("detail-description", Key.DirectionDown) }
        assertTrue("The remote must scroll the description", scroll() > 0f)
        repeat(12) { key("detail-description", Key.DirectionUp) }
        assertEquals(0f, scroll(), 1f)
        key("detail-description", Key.DirectionUp)
        compose.onNodeWithTag("detail-play").assertIsFocused().assertIsDisplayed()
        saveScreenshot("movie-details-tv.png")
    }

    @Test fun bottomOfDescriptionCanAlwaysBeLeftByScrollingUp() {
        screen(description = paragraph.repeat(6))
        focus("detail-description")
        repeat(35) { key("detail-description", Key.DirectionDown) }
        val bottom = scroll()
        assertTrue(bottom > 0f)
        key("detail-description", Key.DirectionUp)
        assertTrue("Up must still work at the end of the text", scroll() < bottom)
        compose.onNodeWithTag("detail-description").assertIsFocused()
    }

    @Test fun actionButtonsAndDescriptionHaveVisibleFocusOnBrightSkins() {
        screen(series = true)
        for (tag in listOf("detail-play", "detail-favorite", "detail-trailer", "detail-description")) {
            focus(tag)
            compose.onNodeWithTag(tag).assertIsFocused().assert(SemanticsMatcher.expectValue(V114FocusVisible, true))
            val image = compose.onNodeWithTag(tag).captureToImage().asAndroidBitmap()
            val color = image.getPixel(image.width / 2, 4)
            assertTrue("Focus must draw a white outline", android.graphics.Color.red(color) > 230 && android.graphics.Color.green(color) > 230 && android.graphics.Color.blue(color) > 230)
        }
        compose.onNodeWithText("Staffeln & Episoden").assertIsDisplayed()
        saveScreenshot("series-details-tv.png")
    }

    @Test fun commonTilesTransferTheirVisibleSelectionWithTheRemote() {
        compose.setContent {
            val mode = LocalInputModeManager.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard) }
            MaterialTheme {
                Row(Modifier.fillMaxSize().background(Color.White), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                    FocusCard("Erste Kachel", accent = Color.Yellow, onClick = {}, modifier = Modifier.width(280.dp).height(140.dp).testTag("first"))
                    FocusCard("Zweite Kachel", accent = Color.Yellow, onClick = {}, modifier = Modifier.width(280.dp).height(140.dp).testTag("second"))
                }
            }
        }
        focus("first")
        key("first", Key.DirectionRight)
        compose.onNodeWithTag("second").assertIsFocused().assert(SemanticsMatcher.expectValue(V114FocusVisible, true))
        compose.onNodeWithTag("first").assert(SemanticsMatcher.expectValue(V114FocusVisible, false))
        saveScreenshot("tile-focus.png")
    }

    @Test fun returningFromAnotherScreenRestoresDescriptionFocusAndScroll() {
        val visible = mutableStateOf(true)
        screen(visible = visible)
        focus("detail-description")
        repeat(8) { key("detail-description", Key.DirectionDown) }
        val previous = scroll()
        compose.runOnIdle { visible.value = false }
        settle()
        compose.runOnIdle { visible.value = true }
        settle()
        compose.onNodeWithTag("detail-description").assertIsFocused().assertIsDisplayed()
        assertEquals(previous, scroll(), 1f)
        key("detail-description", Key.DirectionUp)
        assertTrue(scroll() < previous)
    }

    @Test @Config(qualifiers = "w360dp-h740dp-port")
    fun phoneLayoutKeepsPosterSmallAndActionsVisible() {
        screen(tv = false)
        compose.onNodeWithTag("detail-play").assertIsDisplayed()
        compose.onNodeWithTag("detail-favorite").assertIsDisplayed()
        compose.onNodeWithTag("detail-description-body").assertIsDisplayed()
        val poster = compose.onNodeWithTag("detail-poster").fetchSemanticsNode().boundsInRoot
        assertTrue(poster.width < 130f)
        saveScreenshot("movie-details-phone.png")
    }
}
