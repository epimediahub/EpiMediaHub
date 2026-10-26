package de.epimediahub.app.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.saveable.SaveableStateHolder
import androidx.compose.ui.Modifier
import de.epimediahub.app.Screen
import de.epimediahub.app.UiState
import de.epimediahub.app.model.MediaKind

internal object V164LiveNavigation {
    fun resume(state: UiState): Screen.Player? =
        state.liveBackgroundPlayer?.takeIf { state.screen == Screen.Categories(MediaKind.LIVE) }

    fun retain(previous: UiState, next: UiState): UiState =
        if (next.liveBackgroundPlayer != null &&
            (next.screen != Screen.Categories(MediaKind.LIVE) || previous.active?.id != next.active?.id))
            next.copy(liveBackgroundPlayer = null) else next
}

/** The player occupies the same Compose slot in full-screen and while browsing.
 * Both Media3 and VLC retain their decoder, connection and audio session.
 */
@Composable
internal fun V164PlayerHost(
    screen: Screen,
    background: Screen.Player?,
    menuStates: SaveableStateHolder? = null,
    menuStateKey: String = "",
    player: @Composable (Screen.Player, Boolean) -> Unit,
    browser: @Composable () -> Unit
) {
    Box(Modifier.fillMaxSize()) {
        val playing = (screen as? Screen.Player) ?: background
        if (playing != null) player(playing, background != null)
        if (screen !is Screen.Player) {
            // Changing a menu's saved-state key must never recreate the player.
            if (menuStates == null) browser()
            else menuStates.SaveableStateProvider(menuStateKey) { browser() }
        }
    }
}
