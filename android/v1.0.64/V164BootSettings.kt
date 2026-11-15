package de.epimediahub.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.unit.dp

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
        modifier = Modifier.fillMaxWidth().testTag("boot-autostart-toggle"),
        trailing = {
            Spacer(Modifier.width(20.dp))
            // The whole card owns focus and click; the switch is a visible state indicator.
            Switch(checked = enabled, onCheckedChange = null,
                colors = SwitchDefaults.colors(checkedTrackColor = accent,
                    uncheckedTrackColor = Color(0xFF4A5666), uncheckedThumbColor = Color.White),
                modifier = Modifier.testTag("boot-autostart-switch")
                    .clearAndSetSemantics { stateDescription = if (enabled) "Ein" else "Aus" })
        }
    )
}
