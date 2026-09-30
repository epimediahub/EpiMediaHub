@file:OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)

package de.epimediahub.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import de.epimediahub.app.data.*
import kotlinx.coroutines.delay

internal data class V116Draft(val start: Long? = null, val end: Long? = null)

@Composable
internal fun V116SkipEditor(
    duration: Long, position: () -> Long, segments: List<V115Segment>, drafts: MutableMap<V115SegmentKind, V116Draft>,
    status: String, isTv: Boolean, onSeek: (Long) -> Unit, onSave: (V115SegmentKind, Long?, Long?, Boolean) -> Unit,
    onReset: (V115SegmentKind) -> Unit, onResolve: () -> Unit, onDismiss: () -> Unit
) {
    var kind by remember { mutableStateOf(V115SegmentKind.INTRO) }
    val focus = remember { FocusRequester() }
    val input = LocalInputModeManager.current
    val chosen = segments.firstOrNull { it.kind == kind }
    val draft = drafts[kind] ?: V116Draft(chosen?.startMs, chosen?.endMs)
    val valid = draft.start != null && draft.end != null && V115SkipPolicy.valid(V115Segment(kind, draft.start, draft.end, "Eigen", true, 1.0), duration)
    val size = if (isTv) 18.sp else 16.sp
    LaunchedEffect(Unit) { if (isTv) { input.requestInputMode(InputMode.Keyboard); delay(110); runCatching { focus.requestFocus() } } }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(color = Color(0xF51B1B1B), contentColor = Color.White,
            modifier = Modifier.fillMaxWidth(if (isTv) .82f else .96f).heightIn(max = if (isTv) 480.dp else 650.dp).testTag("skip-editor")) {
            Column(Modifier.padding(if (isTv) 24.dp else 16.dp).verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Intro & Abspann", fontSize = if (isTv) 26.sp else 23.sp, fontWeight = FontWeight.Bold)
                Text("Anfang und Ende an der passenden Videostelle markieren. Du kannst diese Ansicht schließen, weiterschauen und später die zweite Stelle ergänzen.", fontSize = size, color = Color.LightGray)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    V115SegmentKind.values().forEach { type ->
                        Button(onClick = { kind = type }, modifier = Modifier.v114FocusRing().then(if (type == V115SegmentKind.INTRO) Modifier.focusRequester(focus) else Modifier).testTag("mark-type-${type.name}"),
                            colors = ButtonDefaults.buttonColors(containerColor = if (kind == type) Color.White else Color(0xFF414141), contentColor = if (kind == type) Color.Black else Color.White)) {
                            Text(when (type) { V115SegmentKind.INTRO -> "Intro"; V115SegmentKind.RECAP -> "Rückblick"; V115SegmentKind.OUTRO -> "Abspann" }, fontSize = size)
                        }
                    }
                }
                fun display(value: Long?): String = value?.let(::V093FormatTime) ?: "Noch nicht markiert"
                Text("Anfang: ${display(draft.start)}     Ende: ${display(draft.end)}", fontSize = size, fontWeight = FontWeight.Bold, modifier = Modifier.testTag("mark-range"))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { drafts[kind] = draft.copy(start = position().coerceIn(0, duration.coerceAtLeast(0))) }, modifier = Modifier.weight(1f).v114FocusRing().testTag("mark-start")) { Text("Anfang an dieser Stelle", color = Color.White, fontSize = size) }
                    OutlinedButton(onClick = { drafts[kind] = draft.copy(end = position().coerceIn(0, duration.coerceAtLeast(0))) }, modifier = Modifier.weight(1f).v114FocusRing().testTag("mark-end")) { Text("Ende an dieser Stelle", color = Color.White, fontSize = size) }
                }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(-10_000L, -1_000L, 1_000L, 10_000L).forEach { delta ->
                        OutlinedButton(onClick = { onSeek((position() + delta).coerceIn(0, duration.coerceAtLeast(0))) }, modifier = Modifier.weight(1f).v114FocusRing().testTag("mark-seek-$delta")) {
                            Text("${if (delta > 0) "+" else ""}${delta / 1000} s", color = Color.White, fontSize = size)
                        }
                    }
                }
                if (!valid) Text("Zum Speichern werden Anfang und Ende eines gültigen Abschnitts benötigt.", color = Color.LightGray, fontSize = if (isTv) 16.sp else 14.sp)
                Button(onClick = { onSave(kind, draft.start, draft.end, false) }, enabled = valid,
                    modifier = Modifier.fillMaxWidth().v114FocusRing().testTag("mark-save"), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFE50914))) { Text("Zeitmarke speichern", fontSize = size) }
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    TextButton(onClick = { onSave(kind, null, null, true) }, modifier = Modifier.weight(1f).v114FocusRing().testTag("mark-disable")) { Text("Für diese Folge ausblenden", color = Color.White, fontSize = size) }
                    TextButton(onClick = { drafts.remove(kind); onReset(kind) }, modifier = Modifier.weight(1f).v114FocusRing().testTag("mark-reset")) { Text("Automatische Zeiten verwenden", color = Color.White, fontSize = size) }
                }
                if (status.isNotBlank()) Text(status, color = Color.LightGray, fontSize = if (isTv) 16.sp else 14.sp, modifier = Modifier.testTag("mark-status"))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onResolve, modifier = Modifier.weight(1f).v114FocusRing().testTag("mark-resolve")) { Text("Zuordnung prüfen", color = Color.White, fontSize = size) }
                    Button(onClick = onDismiss, modifier = Modifier.weight(1f).v114FocusRing().testTag("mark-close"), colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = Color.Black)) { Text("Zurück zum Video", fontSize = size) }
                }
            }
        }
    }
}

@Composable
internal fun V116IdentityDialog(choices: List<V116TitleChoice>, loading: Boolean, isTv: Boolean, onChoose: (V116TitleChoice) -> Unit, onDismiss: () -> Unit) {
    val focus = remember { FocusRequester() }; val input = LocalInputModeManager.current
    LaunchedEffect(loading) { if (isTv) { input.requestInputMode(InputMode.Keyboard); delay(110); runCatching { focus.requestFocus() } } }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(color = Color(0xFF1B1B1B), contentColor = Color.White, modifier = Modifier.fillMaxWidth(if (isTv) .7f else .95f).heightIn(max = 460.dp).testTag("mark-identities")) {
            Column(Modifier.padding(20.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Text("Passenden Titel auswählen", fontSize = 23.sp, fontWeight = FontWeight.Bold)
                Text("Prüfe Titel und Erscheinungsjahr. Die Auswahl gilt für diese Serie beziehungsweise diesen Film.", fontSize = 16.sp, color = Color.LightGray)
                if (loading) Text("Titel werden gesucht …", fontSize = 18.sp)
                else if (choices.isEmpty()) Text("Kein eindeutiger Treffer verfügbar. Eigene Zeitmarken kannst du trotzdem speichern.", fontSize = 18.sp)
                LazyColumn(Modifier.weight(1f, fill = false), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    items(choices) { choice ->
                        OutlinedButton(onClick = { onChoose(choice) }, modifier = Modifier.fillMaxWidth().v114FocusRing().testTag("mark-title-${choice.imdb.ifBlank { choice.tmdb.toString() }}")) {
                            Text("${choice.title}${choice.year.takeIf { it.matches(Regex("[0-9]{4}")) }?.let { " ($it)" }.orEmpty()}", color = Color.White, fontSize = if (isTv) 19.sp else 16.sp)
                        }
                    }
                }
                Button(onClick = onDismiss, modifier = Modifier.focusRequester(focus).v114FocusRing().testTag("mark-identity-close")) { Text("Zurück", fontSize = 18.sp) }
            }
        }
    }
}
