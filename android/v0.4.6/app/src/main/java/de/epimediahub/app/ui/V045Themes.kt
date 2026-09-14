package de.epimediahub.app.ui

import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import de.epimediahub.app.MainViewModel

/**
 * Compatibility shim only. v0.4.6 removed the configurable v0.4.5 Family PIN
 * UI completely; any legacy reference is routed to the fixed Enigma-style gate.
 */
@Composable
fun V045ThemesScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    V046ThemesScreen(vm, accent, isTv)
}
