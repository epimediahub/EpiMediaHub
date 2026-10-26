package de.epimediahub.app.ui

import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag

@Composable
internal fun V163BootSettingsCard(accent: Color) {
    val context = LocalContext.current
    var enabled by remember(context) { mutableStateOf(V159BootAutostart.enabled(context)) }
    FocusCard(
        title = "Autostart beim Gerätestart",
        subtitle = (if (enabled) "Ein" else "Aus") +
            " · App nach einem Neustart automatisch öffnen. Verfügbarkeit abhängig vom Gerät.",
        accent = accent,
        onClick = {
            enabled = !enabled
            V159BootAutostart.setEnabled(context, enabled)
        },
        modifier = Modifier.fillMaxWidth().testTag("boot-autostart-toggle")
    )
}
