package de.epimediahub.app.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ApplicationProvider
import de.epimediahub.app.model.EpgItem
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
class V163LiveUiTest {
    @get:Rule val compose = createComposeRule()
    private lateinit var rootView: View

    private fun saveScreenshot(name: String) {
        lateinit var bitmap: Bitmap
        compose.runOnIdle {
            bitmap = Bitmap.createBitmap(rootView.width, rootView.height, Bitmap.Config.ARGB_8888)
            rootView.draw(Canvas(bitmap))
        }
        val directory = File("build/qa")
        directory.mkdirs()
        File(directory, name).outputStream().use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }

    private fun settle() {
        compose.waitForIdle()
        compose.mainClock.advanceTimeBy(250L)
        compose.waitForIdle()
    }

    @Test fun bootCardHasVisibleFocusAndRemoteEnterPersistsBothStates() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        V159BootAutostart.setEnabled(context, false)
        compose.setContent {
            val mode = LocalInputModeManager.current
            val view = LocalView.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard); rootView = view }
            MaterialTheme {
                Box(Modifier.fillMaxSize().background(Color(0xFF060B12))) {
                    Box(Modifier.width(700.dp)) { V163BootSettingsCard(Color.Cyan) }
                }
            }
        }
        settle()
        val card = compose.onNodeWithTag("boot-autostart-toggle")
        card.performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        settle()
        card.assertIsFocused().assertIsDisplayed()
        assertTrue(card.fetchSemanticsNode().config[V114FocusVisible])
        compose.onNodeWithText("Autostart beim Gerätestart").assertIsDisplayed()
        card.performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }
        settle()
        assertTrue(V159BootAutostart.enabled(context))
        saveScreenshot("autostart-focus.png")
        compose.onNodeWithText("Ein · App nach einem Neustart automatisch öffnen. Verfügbarkeit abhängig vom Gerät.").assertIsDisplayed()
        card.performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }
        settle()
        assertFalse(V159BootAutostart.enabled(context))
    }

    @Test fun descriptionHasSpaceOnShortTvPanelAndLongTextScrollsWithRemote() {
        val now = System.currentTimeMillis() / 1000L
        val text = "Die Ermittler entdecken einen entscheidenden Hinweis und suchen gemeinsam nach dem Täter. ".repeat(35)
        compose.setContent {
            val mode = LocalInputModeManager.current
            val view = LocalView.current
            SideEffect { mode.requestInputMode(InputMode.Keyboard); rootView = view }
            MaterialTheme {
              Box(Modifier.fillMaxSize().background(Color(0xFF060B12))) {
                V163LiveInfoPanel(MediaEntry("rtl", "RTL HD", MediaKind.LIVE),
                    listOf(EpgItem("Aktuelle Folge", text, now - 100, now + 900),
                        EpgItem("Nächste Folge", "", now + 900, now + 1800)),
                    Color.Cyan, false, Modifier.width(318.dp).height(350.dp))
              }
            }
        }
        settle()
        compose.onNodeWithText("Aktuelle Folge").assertIsDisplayed()
        compose.onNodeWithText("WORUM ES GEHT").assertIsDisplayed()
        val description = compose.onNodeWithTag("live-programme-description")
        description.assertIsDisplayed()
        assertTrue(description.fetchSemanticsNode().boundsInRoot.height > 80f)
        saveScreenshot("live-programme-description.png")
        description.performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        settle()
        description.assertIsFocused()
        description.performKeyInput { keyDown(Key.DirectionDown); keyUp(Key.DirectionDown) }
        settle()
        val scroll = compose.onNode(hasScrollAction()).fetchSemanticsNode()
            .config[SemanticsProperties.VerticalScrollAxisRange].value()
        assertTrue("Remote should reveal the rest of a long description", scroll > 0f)
    }
}
