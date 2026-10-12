package de.epimediahub.app.ui

import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.semantics.SemanticsProperties
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.core.app.ApplicationProvider
import de.epimediahub.app.Screen
import de.epimediahub.app.UiState
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

@OptIn(ExperimentalTestApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V164LiveBrowserTest {
    @get:Rule val compose = createComposeRule()
    private val channel = MediaEntry("1", "Sender", MediaKind.LIVE)

    @Test fun okAndBackKeepTheSamePlayerSessionButNormalExitDisposesIt() {
        val playing = Screen.Player(channel, listOf(channel))
        var screen: Screen by mutableStateOf(playing)
        var background: Screen.Player? by mutableStateOf(null)
        var created = 0
        var released = 0
        compose.setContent {
            V164PlayerHost(screen, background, player = { _, covered ->
                DisposableEffect(Unit) { created++; onDispose { released++ } }
                if (!covered) Column {
                    Button(onClick = { background = playing; screen = Screen.Categories(MediaKind.LIVE) }) { Text("Senderliste öffnen") }
                    Button(onClick = { screen = Screen.Categories(MediaKind.LIVE) }) { Text("Normal verlassen") }
                }
            }, browser = {
                Button(onClick = { screen = background ?: Screen.Home; background = null }) { Text("Zurück") }
            })
        }
        compose.onNodeWithText("Senderliste öffnen").performClick()
        compose.runOnIdle { assertEquals(1, created); assertEquals(0, released) }
        compose.onNodeWithText("Zurück").performClick()
        compose.runOnIdle { assertSame(playing, screen); assertEquals(1, created); assertEquals(0, released) }
        compose.onNodeWithText("Normal verlassen").performClick()
        compose.runOnIdle { assertEquals(1, released) }
        compose.onNodeWithText("Zurück").performClick()
        compose.runOnIdle { assertEquals(Screen.Home, screen) }
    }

    @Test fun onlyOkRetainsAReturnTargetAndOtherRoutesClearIt() {
        val playing = Screen.Player(channel)
        val normal = UiState(screen = Screen.Categories(MediaKind.LIVE))
        assertNull(V164LiveNavigation.resume(normal))
        val opened = normal.copy(liveBackgroundPlayer = playing)
        assertSame(playing, V164LiveNavigation.resume(opened))
        assertNull(V164LiveNavigation.retain(opened, opened.copy(screen = Screen.Home)).liveBackgroundPlayer)
        assertNull(V164LiveNavigation.retain(opened, opened.copy(screen = Screen.Settings)).liveBackgroundPlayer)
    }

    @Test fun autostartSwitchIsVisibleAndRemoteOkChangesItsDisplayedState() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        V159BootAutostart.setEnabled(context, false)
        compose.setContent { V163BootSettingsCard(Color.Cyan) }
        val state = compose.onNodeWithTag("boot-autostart-switch", useUnmergedTree = true)
        state.assertIsDisplayed().assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "Aus"))
        val card = compose.onNodeWithTag("boot-autostart-toggle")
        card.performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        card.performKeyInput { keyDown(Key.Enter); keyUp(Key.Enter) }
        compose.waitForIdle()
        state.assertIsDisplayed().assert(SemanticsMatcher.expectValue(SemanticsProperties.StateDescription, "Ein"))
        compose.runOnIdle { assertTrue(V159BootAutostart.enabled(context)) }
    }
}
