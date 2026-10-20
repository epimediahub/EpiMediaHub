package de.epimediahub.admin

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp

/** Native M3U / Xtream playlist form. Nothing is rendered as HTML/WebView.
 * Existing provider credentials are never read back from the server.
 */
@Composable
internal fun NativePlaylistEditorDialog(
    customerId: String,
    playlistId: String?,
    initialName: String,
    onDismiss: () -> Unit,
    onFinished: (Boolean, String) -> Unit
) {
    var name by remember(customerId, playlistId) { mutableStateOf(initialName) }
    var kind by remember(customerId, playlistId) { mutableStateOf("M3U") }
    var url by remember(customerId, playlistId) { mutableStateOf("") }
    var server by remember(customerId, playlistId) { mutableStateOf("") }
    var username by remember(customerId, playlistId) { mutableStateOf("") }
    var password by remember(customerId, playlistId) { mutableStateOf("") }
    var output by remember(customerId, playlistId) { mutableStateOf("ts") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val editing = playlistId != null
    val valid = name.trim().isNotBlank() &&
        (if (kind == "M3U") url.trim().startsWith("http")
        else server.trim().startsWith("http") &&
            username.trim().isNotBlank() && (editing || password.isNotBlank()))
    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text(if (editing) "Playlist bearbeiten" else "Neue Playlist") },
        text = {
            Column(
                Modifier.fillMaxWidth().verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Text("Playlist-Art")
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(selected = kind == "M3U", onClick = { kind = "M3U" },
                        label = { Text("M3U") }, enabled = !busy)
                    FilterChip(selected = kind == "XTREAM", onClick = { kind = "XTREAM" },
                        label = { Text("Xtream") }, enabled = !busy)
                }
                OutlinedTextField(
                    value = name, onValueChange = { name = it.take(120) },
                    label = { Text("Playlist-Name") }, singleLine = true,
                    enabled = !busy, modifier = Modifier.fillMaxWidth())
                if (kind == "M3U") {
                    OutlinedTextField(
                        value = url, onValueChange = { url = it.take(1600) },
                        label = { Text("Vollständige M3U-Adresse") },
                        enabled = !busy, modifier = Modifier.fillMaxWidth())
                } else {
                    OutlinedTextField(
                        value = server, onValueChange = { server = it.take(1600) },
                        label = { Text("Xtream-Server URL") },
                        enabled = !busy, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(
                        value = username, onValueChange = { username = it.take(150) },
                        label = { Text("Xtream-Benutzername") },
                        enabled = !busy, modifier = Modifier.fillMaxWidth())
                    OutlinedTextField(
                        value = password, onValueChange = { password = it.take(256) },
                        label = { Text(if (editing) "Neues Passwort (leer = behalten)"
                            else "Xtream-Passwort") },
                        visualTransformation = PasswordVisualTransformation(),
                        enabled = !busy, modifier = Modifier.fillMaxWidth())
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        FilterChip(selected = output == "ts", onClick = { output = "ts" },
                            label = { Text("TS") }, enabled = !busy)
                        FilterChip(selected = output == "m3u8", onClick = { output = "m3u8" },
                            label = { Text("M3U8") }, enabled = !busy)
                    }
                }
                Text(
                    if (editing) "Aus Datenschutzgründen werden vorhandene "
                        + "Playlist-Adressen und Zugangsdaten nicht angezeigt. "
                        + "Zum Bearbeiten bitte den vollständigen Zugriff erneut eingeben. "
                        + "Bei Xtream bleibt ein leeres Passwort unverändert."
                    else "Die Zugangsdaten werden nur an den geschützten "
                        + "Admin-Server übertragen und nicht in der App gespeichert.",
                    style = MaterialTheme.typography.bodySmall
                )
                if (error.isNotBlank()) Text(error,
                    color = MaterialTheme.colorScheme.error)
                if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
            }
        },
        dismissButton = {
            TextButton(onClick = onDismiss, enabled = !busy) { Text("Abbrechen") }
        },
        confirmButton = {
            Button(enabled = !busy && valid, onClick = {
                val fields = mapOf(
                    "playlist_name" to name.trim(),
                    "playlist_type" to kind,
                    "playlist_url" to if (kind == "M3U") url.trim() else "",
                    "xtream_server" to if (kind == "XTREAM")
                        server.trim().trimEnd('/') else "",
                    "xtream_username" to if (kind == "XTREAM") username.trim() else "",
                    "xtream_password" to if (kind == "XTREAM") password else "",
                    "xtream_output" to output
                )
                busy = true
                error = ""
                NativeLegacyActions.execute(
                    if (editing) "edit-playlist" else "add-playlist",
                    playlistId ?: customerId, fields
                ) { outcome ->
                    busy = false
                    password = ""
                    if (outcome.applied) onFinished(true, outcome.message)
                    else error = outcome.message
                }
            }) { Text(if (editing) "Änderung speichern" else "Playlist anlegen") }
        }
    )
}
