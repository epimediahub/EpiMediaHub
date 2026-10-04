package de.epimediahub.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties

internal val v126RadioKeyRows = listOf("0123456789", "ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZÄÖÜ-")

@Composable
internal fun V126RadioKeyboard(title: String, initialValue: String, accent: Color,
    onDismiss: () -> Unit, onSubmit: (String) -> Unit) {
    var value by remember(initialValue) { mutableStateOf(initialValue) }
    val config = LocalConfiguration.current
    Dialog(onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth(.94f).widthIn(max = 920.dp)
            .heightIn(max = config.screenHeightDp.dp * .94f),
            color = Color(0xFF111821), shape = RoundedCornerShape(18.dp),
            border = BorderStroke(1.dp, accent.copy(.65f))) {
            Column(Modifier.padding(20.dp).verticalScroll(rememberScrollState()),
                verticalArrangement = Arrangement.spacedBy(10.dp)) {
                Text(title, color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Bold)
                Surface(Modifier.fillMaxWidth().height(48.dp), color = Color(0xFF070D16),
                    shape = RoundedCornerShape(8.dp)) {
                    Box(Modifier.padding(horizontal = 14.dp), contentAlignment = Alignment.CenterStart) {
                        Text(value.ifBlank { "Suchbegriff eingeben …" }, color = Color.White,
                            fontSize = 20.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
                v126RadioKeyRows.forEachIndexed { index, row ->
                    Row(Modifier.fillMaxWidth().testTag("radio-key-row-$index"),
                        horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                        row.forEach { character ->
                            OutlinedButton(onClick = { value += character.lowercaseChar() },
                                modifier = Modifier.weight(1f).height(48.dp).v114FocusRing()
                                    .testTag("radio-key-$character"),
                                contentPadding = PaddingValues(0.dp),
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)) {
                                Text(character.toString(), fontSize = 21.sp, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedButton({ value += " " }, Modifier.weight(1.5f).height(48.dp).v114FocusRing()) {
                        Text("LEERZEICHEN", fontSize = 16.sp, color = Color.White)
                    }
                    OutlinedButton({ value = value.dropLast(1) }, Modifier.weight(1f).height(48.dp).v114FocusRing()) {
                        Text("⌫", fontSize = 23.sp, color = Color.White)
                    }
                    OutlinedButton({ value = "" }, Modifier.weight(1f).height(48.dp).v114FocusRing()) {
                        Text("LÖSCHEN", fontSize = 16.sp, color = Color.White)
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(12.dp, Alignment.End)) {
                    OutlinedButton(onDismiss, Modifier.height(48.dp).v114FocusRing()) { Text("Abbrechen", fontSize = 18.sp) }
                    Button({ onSubmit(value.trim()) }, Modifier.height(48.dp).v114FocusRing().testTag("tv-keyboard-submit"),
                        colors = ButtonDefaults.buttonColors(containerColor = accent)) {
                        Text(if (value.isBlank()) "Übernehmen" else "Suchen", fontSize = 18.sp)
                    }
                }
            }
        }
    }
}
