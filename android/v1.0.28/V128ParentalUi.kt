package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.*
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import coil.compose.AsyncImage
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.data.V128ParentalControl
import de.epimediahub.app.model.MediaEntry

internal val LocalV128ArtworkLocked = staticCompositionLocalOf<(MediaEntry) -> Boolean> { { false } }

@Composable
internal fun V128MediaArtwork(item: MediaEntry, modifier: Modifier = Modifier,
    scale: ContentScale = ContentScale.Crop) {
    if (LocalV128ArtworkLocked.current(item)) {
        Box(modifier.background(Color(0xFF111B27)).testTag("adult-artwork-locked"), contentAlignment = Alignment.Center) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                Icon(Icons.Default.Lock, null, tint = Color.White.copy(.85f), modifier = Modifier.size(32.dp))
                Text("PIN erforderlich", color = Color.White, fontSize = 12.sp)
            }
        }
    } else if (item.image.isNotBlank()) {
        AsyncImage(item.image, item.name, modifier, contentScale = scale)
    }
}

@Composable
internal fun V128LoadingPanel(title: String, subtitle: String, accent: Color,
    isTv: Boolean = false, modifier: Modifier = Modifier) {
    Surface(modifier.widthIn(max = 540.dp).testTag("readable-loading-panel"),
        color = Color(0xFF101925), contentColor = Color.White, shape = RoundedCornerShape(20.dp),
        border = BorderStroke(1.dp, Color.White.copy(.16f))) {
        Column(Modifier.padding(horizontal = if (isTv) 36.dp else 24.dp, vertical = 26.dp),
            horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator(Modifier.size(if (isTv) 44.dp else 36.dp), color = accent, strokeWidth = 3.dp)
            Spacer(Modifier.height(16.dp))
            Text(title, color = Color.White, fontSize = if (isTv) 20.sp else 17.sp, fontWeight = FontWeight.Bold)
            if (subtitle.isNotBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(subtitle, color = Color.White.copy(.82f), fontSize = if (isTv) 14.sp else 12.sp)
            }
        }
    }
}

@Composable
internal fun V128PinEntry(title: String, accent: Color, busy: Boolean, error: String,
    onCancel: () -> Unit, onSubmit: (String) -> Unit) {
    var digits by remember(title, error) { mutableStateOf("") }
    val first = remember { FocusRequester() }
    val confirm = remember { FocusRequester() }
    fun digit(value: String) { if (!busy && digits.length < 4) digits += value }
    LaunchedEffect(title, error) { withFrameNanos { }; runCatching { first.requestFocus() } }
    LaunchedEffect(digits.length) { if (digits.length == 4) { withFrameNanos { }; runCatching { confirm.requestFocus() } } }
    Column(Modifier.widthIn(max = 460.dp).verticalScroll(rememberScrollState())
        .onPreviewKeyEvent { event ->
            if (busy || event.type != KeyEventType.KeyDown) false else {
                val value = when (event.key) {
                    Key.Zero -> "0"; Key.One -> "1"; Key.Two -> "2"; Key.Three -> "3"; Key.Four -> "4"
                    Key.Five -> "5"; Key.Six -> "6"; Key.Seven -> "7"; Key.Eight -> "8"; Key.Nine -> "9"
                    else -> null
                }
                when {
                    value != null -> { digit(value); true }
                    event.key == Key.Backspace -> { digits = digits.dropLast(1); true }
                    else -> false
                }
            }
        }.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(title, color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(8.dp))
        Text("Vierstellige PIN", color = Color.White.copy(.75f))
        Text("●".repeat(digits.length) + "○".repeat(4 - digits.length),
            modifier = Modifier.padding(vertical = 10.dp).testTag("pin-masked"), color = Color.White, fontSize = 30.sp, letterSpacing = 10.sp)
        if (error.isNotBlank()) Text(error, color = Color(0xFFFFB4AB), modifier = Modifier.testTag("pin-error"))
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth().padding(vertical = 8.dp), color = accent)
        listOf(listOf("1", "2", "3"), listOf("4", "5", "6"), listOf("7", "8", "9"), listOf("Löschen", "0", "Zurück")).forEach { row ->
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEach { value ->
                    OutlinedButton(onClick = { when(value) { "Löschen" -> digits = ""; "Zurück" -> digits = digits.dropLast(1); else -> digit(value) } },
                        enabled = !busy, modifier = Modifier.weight(1f).heightIn(min = 48.dp).testTag("pin-key-$value")
                            .then(if (value == "1") Modifier.focusRequester(first) else Modifier).v114FocusRing(),
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)) {
                        Text(value, fontSize = if (value.length == 1) 20.sp else 12.sp)
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(top = 10.dp), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            OutlinedButton(onClick = onCancel, enabled = !busy, modifier = Modifier.weight(1f).v114FocusRing()) { Text("Abbrechen", color = Color.White) }
            Button(onClick = { if (V128ParentalControl.validPin(digits)) onSubmit(digits) }, enabled = !busy && digits.length == 4,
                modifier = Modifier.weight(1f).focusRequester(confirm).v114FocusRing().testTag("pin-confirm"),
                colors = ButtonDefaults.buttonColors(containerColor = accent, contentColor = Color.Black)) { Text("Bestätigen") }
        }
    }
}

@Composable
internal fun V128PinDialog(title: String, accent: Color, busy: Boolean, error: String,
    onCancel: () -> Unit, onSubmit: (String) -> Unit) {
    Dialog(onDismissRequest = { if (!busy) onCancel() }, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.padding(16.dp).widthIn(max = 470.dp), color = Color(0xFF101925),
            shape = RoundedCornerShape(20.dp), border = BorderStroke(1.dp, Color.White.copy(.2f))) {
            V128PinEntry(title, accent, busy, error, onCancel, onSubmit)
        }
    }
}

@Composable
internal fun V128MenuLockScreen(vm: MainViewModel, accent: Color, onExit: () -> Unit) {
    LaunchedEffect(Unit) { vm.requestMenuUnlock() }
    BackHandler { onExit() }
    Box(Modifier.fillMaxSize().background(Color(0xFF080D15)), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Icon(Icons.Default.Lock, null, tint = Color.White, modifier = Modifier.size(52.dp))
            Text("Menü gesperrt", color = Color.White, fontWeight = FontWeight.Bold, fontSize = 26.sp, modifier = Modifier.padding(16.dp))
            Button(onClick = { vm.requestMenuUnlock() }, modifier = Modifier.v114FocusRing()) { Text("Mit PIN entsperren") }
        }
    }
}

@Composable
fun V128ParentalSettingsScreen(vm: MainViewModel, accent: Color) {
    val ui by vm.ui.collectAsState()
    val settings = ui.parentalSettings
    var changePin by remember { mutableStateOf(false) }
    var firstPin by remember { mutableStateOf<String?>(null) }
    var setupError by remember { mutableStateOf("") }
    var removeConfirmation by remember { mutableStateOf(false) }
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("KINDERSICHERUNG & PIN", R.drawable.brand_header, { vm.back() })
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            FocusCard(if (settings.hasPin) "PIN ändern" else "Eigene PIN festlegen", "Vier Ziffern · dieselbe PIN für alle aktivierten Sperren",
                R.drawable.icon_settings, accent = accent, modifier = Modifier.fillMaxWidth(), onClick = { firstPin = null; setupError = ""; changePin = true })
            V128ProtectionToggle("18+-Inhalte sperren", "Erwachsenen-Kategorien und Alterskennzeichnungen des Anbieters", settings.lockAdult,
                settings.hasPin, accent) { vm.updateParentalSettings(adult = !settings.lockAdult) }
            V128ProtectionToggle("Inhalte ohne Altersangabe sperren", "Zusätzlicher Schutz für Filme und Serien ohne Freigabe", settings.lockUnrated,
                settings.hasPin && settings.lockAdult, accent) { vm.updateParentalSettings(unrated = !settings.lockUnrated) }
            V128ProtectionToggle("Hauptmenü sperren", "PIN beim App-Start und nach Rückkehr aus dem Hintergrund", settings.lockMenu,
                settings.hasPin, accent) { vm.updateParentalSettings(menu = !settings.lockMenu) }
            if (settings.hasPin) FocusCard("PIN und Sperren entfernen", "Deaktiviert die Kindersicherung und die Menüsperre",
                R.drawable.icon_settings, accent = accent, modifier = Modifier.fillMaxWidth(), onClick = { removeConfirmation = true })
        }
    }
    if (changePin) V128PinDialog(if (firstPin == null) "Neue PIN festlegen" else "PIN wiederholen", accent, ui.parentalBusy, setupError,
        onCancel = { changePin = false; firstPin = null }, onSubmit = { pin ->
            if (firstPin == null) firstPin = pin
            else if (firstPin != pin) { firstPin = null; setupError = "Die PINs stimmen nicht überein. Bitte neu festlegen." }
            else vm.setParentalPin(pin) { success ->
                if (success) { changePin = false; firstPin = null }
                else setupError = "PIN konnte nicht gespeichert werden. Bitte erneut versuchen."
            }
        })
    if (removeConfirmation) AlertDialog(onDismissRequest = { removeConfirmation = false },
        title = { Text("Sperren entfernen?") }, text = { Text("18+-Inhalte und das Hauptmenü sind anschließend ohne PIN erreichbar.") },
        confirmButton = { TextButton(onClick = { vm.removeParentalPin(); removeConfirmation = false }, modifier = Modifier.v114FocusRing()) { Text("Entfernen") } },
        dismissButton = { TextButton(onClick = { removeConfirmation = false }, modifier = Modifier.v114FocusRing()) { Text("Abbrechen") } })
}

@Composable
private fun V128ProtectionToggle(title: String, detail: String, checked: Boolean, enabled: Boolean,
    accent: Color, onClick: () -> Unit) {
    Surface(Modifier.fillMaxWidth(), color = Color(0xFF111B29), shape = RoundedCornerShape(16.dp)) {
        TextButton(onClick = onClick, enabled = enabled, modifier = Modifier.fillMaxWidth().v114FocusRing()) {
            Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(title, color = if(enabled) Color.White else Color.White.copy(.5f), fontWeight = FontWeight.Bold)
                    Text(detail, color = Color.White.copy(.68f), fontSize = 12.sp)
                }
                Text(if (checked) "AN" else "AUS", color = if (checked) accent else Color.White.copy(.6f), modifier = Modifier.padding(start = 12.dp))
            }
        }
    }
}
