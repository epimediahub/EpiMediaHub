package de.epimediahub.app.ui

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import kotlinx.coroutines.delay

/**
 * Explicit, cancellable TV remote dialog. Opt-out has first focus and causes
 * NO changes to stream selection. It is only shown after sustained 25 fps.
 */
@Composable
internal fun V187SportModeOffer(onYes: () -> Unit, onNo: () -> Unit) {
    val noFocus = remember { FocusRequester() }
    AlertDialog(
        onDismissRequest = onNo,
        title = { Text("Sportmodus verfügbar") },
        text = {
            Text("Dieser Sender läuft mit 25 fps. Möchten Sie eine flüssigere " +
                "50-fps-Variante suchen? Die App prüft Alternativen nacheinander. " +
                "Mit Nein bleibt die aktuelle Wiedergabe unverändert.")
        },
        confirmButton = {
            TextButton(
                onClick = onYes,
                modifier = Modifier.v114FocusRing().testTag("sportmode-confirm")
            ) { Text("Ja · Sportmodus") }
        },
        dismissButton = {
            TextButton(
                onClick = onNo,
                modifier = Modifier.focusRequester(noFocus).v114FocusRing()
                    .testTag("sportmode-decline")
            ) { Text("Nein · Hier bleiben", color = Color.White) }
        },
        modifier = Modifier.testTag("sportmode-offer")
    )
    LaunchedEffect(Unit) {
        delay(100L)
        runCatching { noFocus.requestFocus() }
    }
}
