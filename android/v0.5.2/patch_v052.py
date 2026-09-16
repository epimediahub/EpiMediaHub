#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")

# Version metadata.
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
require_once(s, 'versionCode = 501', 'v0.5.1 versionCode')
require_once(s, 'versionName = "0.5.1"', 'v0.5.1 versionName')
s = s.replace('versionCode = 501', 'versionCode = 502', 1)
s = s.replace('versionName = "0.5.1"', 'versionName = "0.5.2"', 1)
gradle.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.5.1", "0.5.2"))

# ---------------------------------------------------------------------------
# Fire TV: replace the shared 4-digit PIN TextField with a D-pad keypad.
# This prevents the Android/Fire OS IME from stealing focus and trapping Back.
# ---------------------------------------------------------------------------
themes = java / "ui/V046Themes.kt"
s = themes.read_text()
modifier_import = 'import androidx.compose.ui.Modifier\n'
if 'import androidx.compose.ui.focus.FocusRequester\n' not in s:
    require_once(s, modifier_import, 'V046Themes Modifier import')
    s = s.replace(
        modifier_import,
        modifier_import + 'import androidx.compose.ui.focus.FocusRequester\nimport androidx.compose.ui.focus.focusRequester\n',
        1,
    )
start = s.find('@Composable\nfun V046FamilyPinDialog(')
if start < 0:
    raise SystemExit('V046FamilyPinDialog not found')
# This dialog is intentionally the final declaration in V046Themes.kt.
new_pin_dialog = r'''@Composable
fun V046FamilyPinDialog(
    title: String,
    message: String,
    pinLabel: String = "Family-PIN",
    errorText: String = "Family-PIN ist falsch.",
    onDismiss: () -> Unit,
    onVerify: (String) -> Boolean
) {
    var pin by remember { mutableStateOf("") }
    var error by remember { mutableStateOf(false) }
    val firstKeyFocus = remember { FocusRequester() }
    val confirmFocus = remember { FocusRequester() }

    BackHandler(enabled = true) { onDismiss() }
    LaunchedEffect(Unit) { runCatching { firstKeyFocus.requestFocus() } }
    LaunchedEffect(pin) {
        if (pin.length == 4) runCatching { confirmFocus.requestFocus() }
    }

    fun keyPress(key: String) {
        error = false
        when (key) {
            "⌫" -> if (pin.isNotEmpty()) pin = pin.dropLast(1)
            "CLR" -> pin = ""
            else -> if (pin.length < 4 && key.length == 1 && key[0].isDigit()) pin += key
        }
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        icon = { Icon(Icons.Default.Lock, null) },
        title = { Text(title) },
        text = {
            Column {
                Text(message)
                Spacer(Modifier.height(10.dp))
                Text(pinLabel, style = MaterialTheme.typography.labelMedium)
                Spacer(Modifier.height(5.dp))
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    tonalElevation = 2.dp,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        buildString { repeat(4) { append(if (it < pin.length) "●" else "○") } },
                        modifier = Modifier.padding(vertical = 12.dp),
                        textAlign = androidx.compose.ui.text.style.TextAlign.Center,
                        fontSize = 24.sp,
                        letterSpacing = 9.sp,
                        fontWeight = FontWeight.Black
                    )
                }
                Spacer(Modifier.height(10.dp))
                val keys = listOf("1","2","3","4","5","6","7","8","9","⌫","0","CLR")
                keys.chunked(3).forEachIndexed { rowIndex, row ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                        row.forEachIndexed { columnIndex, key ->
                            val focusModifier = if (rowIndex == 0 && columnIndex == 0) Modifier.focusRequester(firstKeyFocus) else Modifier
                            OutlinedButton(
                                onClick = { keyPress(key) },
                                enabled = true,
                                modifier = Modifier.weight(1f).height(46.dp).then(focusModifier),
                                contentPadding = PaddingValues(0.dp)
                            ) { Text(key, fontWeight = FontWeight.Bold) }
                        }
                    }
                    if (rowIndex < 3) Spacer(Modifier.height(6.dp))
                }
                if (error) Text(errorText, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 7.dp))
                Text(
                    "Mit dem Steuerkreuz bedienen · Zurück schließt dieses Fenster.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    modifier = Modifier.padding(top = 7.dp)
                )
            }
        },
        confirmButton = {
            Button(
                enabled = pin.length == 4,
                modifier = Modifier.focusRequester(confirmFocus),
                onClick = { if (!onVerify(pin)) { error = true; pin = ""; runCatching { firstKeyFocus.requestFocus() } } }
            ) { Text("Freischalten") }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Abbrechen") } }
    )
}
'''
s = s[:start] + new_pin_dialog
# Old keyboard imports may remain harmless, but remove the PIN-only ones for clarity.
s = s.replace('import androidx.compose.foundation.text.KeyboardOptions\n', '')
s = s.replace('import androidx.compose.ui.text.input.KeyboardType\n', '')
s = s.replace('import androidx.compose.ui.text.input.PasswordVisualTransformation\n', '')
themes.write_text(s)

# ---------------------------------------------------------------------------
# Fire TV: rewrite dashboard-code entry to a native D-pad A-Z/2-9 keypad.
# No TextField means no Fire OS keyboard can capture Back/focus.
# ---------------------------------------------------------------------------
dialog = java / "ui/V051DashboardConnect.kt"
dialog.write_text(r'''package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.data.SetupCodeProvisioning
import de.epimediahub.app.data.SetupCodeResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun V051DashboardConnectDialog(
    onDismiss: () -> Unit,
    onProvisioned: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val firstKeyFocus = remember { FocusRequester() }
    val connectFocus = remember { FocusRequester() }
    var code by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    val allowed = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

    fun raw() = SetupCodeProvisioning.rawCode(code)
    fun add(char: Char) {
        if (!busy && raw().length < 12) {
            code = SetupCodeProvisioning.normalize(raw() + char)
            error = null
        }
    }
    fun erase() {
        if (!busy && raw().isNotEmpty()) {
            code = SetupCodeProvisioning.normalize(raw().dropLast(1))
            error = null
        }
    }
    fun clear() {
        if (!busy) { code = ""; error = null }
    }

    val submit: () -> Unit = {
        if (!busy && SetupCodeProvisioning.isValid(code)) {
            busy = true
            error = null
            scope.launch {
                val result = withContext(Dispatchers.IO) {
                    SetupCodeProvisioning.redeem(
                        context.applicationContext,
                        SetupCodeProvisioning.PRODUCTION_BASE_URL,
                        code
                    )
                }
                busy = false
                when (result) {
                    is SetupCodeResult.Success -> onProvisioned()
                    is SetupCodeResult.Error -> {
                        error = result.message
                        clear()
                        runCatching { firstKeyFocus.requestFocus() }
                    }
                }
            }
        }
    }

    BackHandler(enabled = true) {
        if (!busy) onDismiss()
    }
    LaunchedEffect(Unit) { runCatching { firstKeyFocus.requestFocus() } }
    LaunchedEffect(code) {
        if (raw().length == 12) runCatching { connectFocus.requestFocus() }
    }

    AlertDialog(
        onDismissRequest = { if (!busy) onDismiss() },
        title = { Text("Mit Dashboard verbinden") },
        text = {
            Column {
                Text("Gib den 12-stelligen Einrichtungscode aus dem EpiMediaHub-Dashboard ein.")
                Spacer(Modifier.height(9.dp))
                Surface(
                    shape = RoundedCornerShape(10.dp),
                    tonalElevation = 2.dp,
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        if (code.isBlank()) "____-____-____" else code,
                        modifier = Modifier.padding(vertical = 10.dp),
                        textAlign = TextAlign.Center,
                        fontSize = 20.sp,
                        letterSpacing = 2.sp,
                        fontWeight = FontWeight.Black
                    )
                }
                Spacer(Modifier.height(9.dp))
                allowed.chunked(8).forEachIndexed { rowIndex, row ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        row.forEachIndexed { columnIndex, char ->
                            val focusModifier = if (rowIndex == 0 && columnIndex == 0) Modifier.focusRequester(firstKeyFocus) else Modifier
                            OutlinedButton(
                                onClick = { add(char) },
                                enabled = !busy && raw().length < 12,
                                modifier = Modifier.weight(1f).height(40.dp).then(focusModifier),
                                contentPadding = PaddingValues(0.dp)
                            ) { Text(char.toString(), fontSize = 12.sp, fontWeight = FontWeight.Bold) }
                        }
                    }
                    if (rowIndex < 3) Spacer(Modifier.height(4.dp))
                }
                Spacer(Modifier.height(7.dp))
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(7.dp)) {
                    OutlinedButton(onClick = { erase() }, enabled = !busy && raw().isNotEmpty(), modifier = Modifier.weight(1f)) { Text("⌫ Löschen") }
                    OutlinedButton(onClick = { clear() }, enabled = !busy && raw().isNotEmpty(), modifier = Modifier.weight(1f)) { Text("Alles löschen") }
                }
                error?.let {
                    Spacer(Modifier.height(6.dp))
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
                Text(
                    "Steuerkreuz + OK verwenden. Die Fire-TV-Tastatur wird nicht geöffnet. Zurück = Abbrechen.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    fontSize = 11.sp,
                    modifier = Modifier.padding(top = 6.dp)
                )
            }
        },
        confirmButton = {
            Button(
                enabled = !busy && SetupCodeProvisioning.isValid(code),
                onClick = submit,
                modifier = Modifier.focusRequester(connectFocus)
            ) { Text(if (busy) "Wird verbunden …" else "Verbinden") }
        },
        dismissButton = {
            TextButton(enabled = !busy, onClick = onDismiss) { Text("Abbrechen") }
        }
    )
}
''')

print("Android v0.5.2 Fire TV D-pad setup navigation applied")
