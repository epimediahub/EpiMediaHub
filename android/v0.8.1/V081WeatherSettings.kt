package de.epimediahub.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import de.epimediahub.app.R
import de.epimediahub.app.data.V070WeatherClient

@Composable
fun V081WeatherSettingsCard(accent: androidx.compose.ui.graphics.Color) {
    val context = LocalContext.current
    var showDialog by remember { mutableStateOf(false) }
    var currentPostal by remember { mutableStateOf(V070WeatherClient.postalCode(context)) }
    var currentCountry by remember { mutableStateOf(V070WeatherClient.countryCode(context)) }

    val subtitle = if (currentPostal.isBlank()) {
        "Automatische Standorterkennung"
    } else {
        "PLZ $currentPostal · $currentCountry"
    }

    FocusCard(
        title = "Wetter & Standort",
        subtitle = subtitle,
        imageRes = R.drawable.icon_settings,
        accent = accent,
        onClick = { showDialog = true }
    )

    if (showDialog) {
        var postal by remember(showDialog) { mutableStateOf(currentPostal) }
        var country by remember(showDialog) { mutableStateOf(currentCountry.ifBlank { "DE" }) }
        var error by remember(showDialog) { mutableStateOf("") }

        AlertDialog(
            onDismissRequest = { showDialog = false },
            title = { Text("Wetterstandort") },
            text = {
                Column {
                    Text("Gib deine Postleitzahl ein. Damit verwendet EpiMediaHub einen festen Standort statt einer ungenauen automatischen Erkennung.")
                    Spacer(Modifier.height(14.dp))
                    OutlinedTextField(
                        value = postal,
                        onValueChange = {
                            postal = it.filter { ch -> ch.isLetterOrDigit() || ch == '-' || ch == ' ' }.take(12)
                            error = ""
                        },
                        label = { Text("Postleitzahl") },
                        placeholder = { Text("z. B. 45127") },
                        singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Text),
                        modifier = Modifier.fillMaxWidth()
                    )
                    Spacer(Modifier.height(10.dp))
                    OutlinedTextField(
                        value = country,
                        onValueChange = {
                            country = it.filter(Char::isLetter).uppercase().take(2)
                            error = ""
                        },
                        label = { Text("Land") },
                        placeholder = { Text("DE") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    if (error.isNotBlank()) {
                        Spacer(Modifier.height(8.dp))
                        Text(error, color = MaterialTheme.colorScheme.error)
                    }
                }
            },
            confirmButton = {
                Button(
                    onClick = {
                        val p = postal.trim()
                        val c = country.trim().uppercase().ifBlank { "DE" }
                        if (p.length < 3) {
                            error = "Bitte eine gültige Postleitzahl eingeben."
                        } else {
                            V070WeatherClient.saveLocation(context.applicationContext, p, c)
                            currentPostal = p
                            currentCountry = c
                            showDialog = false
                        }
                    }
                ) {
                    Text("Speichern")
                }
            },
            dismissButton = {
                Row {
                    TextButton(
                        onClick = {
                            V070WeatherClient.saveLocation(context.applicationContext, "", country.ifBlank { "DE" })
                            currentPostal = ""
                            currentCountry = country.ifBlank { "DE" }
                            showDialog = false
                        }
                    ) { Text("Automatisch") }
                    TextButton(onClick = { showDialog = false }) { Text("Abbrechen") }
                }
            }
        )
    }
}
