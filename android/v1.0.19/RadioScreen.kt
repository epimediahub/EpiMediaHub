package de.epimediahub.app.ui

import android.view.KeyEvent
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.lifecycle.viewmodel.compose.viewModel
import coil.compose.AsyncImage
import de.epimediahub.app.data.*
import de.epimediahub.app.radio.RadioPlaybackState
import kotlinx.coroutines.delay

/** Header shortcuts stay separate from the six large home tiles. */
@Composable
internal fun RadioHomeActions(showPlaylistSwitch: Boolean, isTv: Boolean, accent: Color,
    onPlaylistSwitch: () -> Unit, onRadio: () -> Unit, modifier: Modifier = Modifier) {
    Row(modifier.testTag("home-round-actions"), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        if (showPlaylistSwitch) RadioHomeButton("playlist-switch", "Playlist wechseln", isTv, accent, onPlaylistSwitch) {
            Icon(Icons.Default.SwapHoriz, null, Modifier.size(if (isTv) 23.dp else 20.dp))
        }
        RadioHomeButton("radio", "Radio", isTv, accent, onRadio) {
            Icon(Icons.Default.Radio, null, Modifier.size(if (isTv) 23.dp else 20.dp))
        }
    }
}

@Composable
private fun RadioHomeButton(id: String, label: String, isTv: Boolean, accent: Color,
    onClick: () -> Unit, content: @Composable () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        modifier = Modifier.size(if (isTv) 44.dp else 40.dp)
            .then(v111RememberFocus("home", id, if (id == "radio") 7 else 6, isTv))
            .onFocusChanged { focused = it.hasFocus }
            .semantics { contentDescription = label; this[V114FocusVisible] = focused }.testTag("home-$id")
            .clickable(role = Role.Button, onClick = onClick),
        color = if (focused) accent else Color(0xF51A222C), contentColor = Color.White,
        shape = CircleShape,
        border = BorderStroke(if (focused) 3.dp else 1.dp, if (focused) Color.White else Color.White.copy(.3f))
    ) { Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { content() } }
}

internal data class RadioActions(
    val back: () -> Unit = {}, val mode: (RadioMode) -> Unit = {}, val query: (RadioQuery) -> Unit = {},
    val play: (RadioStation) -> Unit = {}, val favorite: (RadioStation) -> Unit = {},
    val more: () -> Unit = {}, val reload: () -> Unit = {}, val toggle: () -> Unit = {},
    val previous: () -> Unit = {}, val next: () -> Unit = {}, val stop: () -> Unit = {}
)

@Composable
internal fun RadioScreen(isTv: Boolean, accent: Color, onBack: () -> Unit,
    vm: RadioViewModel = viewModel(key = "international-radio")) {
    val state by vm.ui.collectAsState()
    val playback by vm.player.state.collectAsState()
    RadioContent(state, playback, isTv, accent, RadioActions(onBack, vm::mode, vm::query, vm::play, vm::favorite,
        { vm.load(true) }, { vm.refresh() }, vm.player::toggle, vm.player::previous, vm.player::next, vm.player::stop))
}

@OptIn(ExperimentalComposeUiApi::class)
@Composable
internal fun RadioContent(state: RadioUiState, playback: RadioPlaybackState, isTv: Boolean, accent: Color, actions: RadioActions) {
    var picker by remember { mutableStateOf<String?>(null) }
    var search by remember { mutableStateOf(false) }
    val backFocus = remember { FocusRequester() }
    val inputMode = LocalInputModeManager.current
    val shown = remember(state.mode, state.query, state.stations, state.favorites, state.recent) { state.visible }
    val favorites = remember(state.favorites) { state.favoriteIds }
    val memory = "radio:${state.mode}:${state.query}"
    val list = v111RememberLazyListState(memory)
    BackHandler { actions.back() }
    LaunchedEffect(isTv) {
        if (isTv) { inputMode.requestInputMode(InputMode.Keyboard); delay(100); runCatching { backFocus.requestFocus() } }
    }

    Column(Modifier.fillMaxSize().testTag("radio-screen").onPreviewKeyEvent {
        if (it.nativeKeyEvent.action != KeyEvent.ACTION_DOWN) false else when (it.nativeKeyEvent.keyCode) {
            KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE -> { actions.toggle(); true }
            KeyEvent.KEYCODE_MEDIA_NEXT -> { actions.next(); true }
            KeyEvent.KEYCODE_MEDIA_PREVIOUS -> { actions.previous(); true }
            KeyEvent.KEYCODE_MEDIA_STOP -> { actions.stop(); true }
            else -> false
        }
    }.padding(horizontal = if (isTv) 26.dp else 10.dp, vertical = if (isTv) 14.dp else 5.dp)) {
        Row(Modifier.fillMaxWidth().height(if (isTv) 56.dp else 42.dp).background(Color(0xE80B111C), RoundedCornerShape(12.dp)), verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            IconButton(actions.back, Modifier.focusRequester(backFocus).v114FocusRing().testTag("radio-back")) {
                Icon(Icons.Default.ArrowBack, "Zurück", tint = Color.White)
            }
            Icon(Icons.Default.Radio, null, tint = accent)
            Text("RADIO", color = Color.White, fontWeight = FontWeight.Black, fontSize = if (isTv) 26.sp else 20.sp)
            Text("Weltweit", color = Color.White.copy(.7f), fontSize = if (isTv) 15.sp else 12.sp, modifier = Modifier.weight(1f))
            RadioTextButton("DE", "radio-quick-de", accent) { actions.mode(RadioMode.DISCOVER); actions.query(state.query.copy(countryCode = "DE")) }
            RadioTextButton("IT", "radio-quick-it", accent) { actions.mode(RadioMode.DISCOVER); actions.query(state.query.copy(countryCode = "IT")) }
        }
        Row(Modifier.weight(1f).fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(if (isTv) 16.dp else 7.dp)) {
            Surface(Modifier.width(if (isTv) 166.dp else 114.dp).fillMaxHeight(), color = Color(0xF20B111C), shape = RoundedCornerShape(14.dp)) {
                Column(Modifier.padding(8.dp), verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    RadioMode.entries.forEach { mode ->
                        OutlinedButton({ actions.mode(mode) }, Modifier.fillMaxWidth().height(if (isTv) 52.dp else 43.dp)
                            .v114FocusRing().testTag("radio-mode-${mode.name.lowercase()}"),
                            contentPadding = PaddingValues(6.dp), border = BorderStroke(1.dp, if (state.mode == mode) accent else Color.White.copy(.16f)),
                            colors = ButtonDefaults.outlinedButtonColors(containerColor = if (state.mode == mode) accent.copy(.23f) else Color.Transparent, contentColor = Color.White)) {
                            Text(mode.label, maxLines = 1, fontSize = if (isTv) 14.sp else 11.sp, fontWeight = FontWeight.Bold)
                        }
                    }
                    Spacer(Modifier.weight(1f))
                    Text("Senderverzeichnis:\nRadio Browser", color = Color.White.copy(.55f), fontSize = 10.sp)
                }
            }
            Column(Modifier.weight(1f).fillMaxHeight().background(Color(0xD90B111C), RoundedCornerShape(14.dp)).padding(horizontal = 7.dp)) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    RadioFilter("Land: ${radioCountryName(state.query.countryCode).ifBlank { "Weltweit" }}", "radio-country", Modifier.weight(1f), isTv) { picker = "country" }
                    RadioFilter("Sprache: ${radioLanguageName(state.query.language).ifBlank { "Alle" }}", "radio-language", Modifier.weight(1f), isTv) { picker = "language" }
                    RadioFilter(state.query.category?.label ?: "Musik & Themen", "radio-category", Modifier.weight(1f), isTv) { picker = "category" }
                    IconButton({ search = true }, Modifier.v114FocusRing().testTag("radio-search")) { Icon(Icons.Default.Search, "Sender suchen", tint = Color.White) }
                }
                if (state.query != RadioQuery()) {
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(listOf(state.query.name, radioCountryName(state.query.countryCode), radioLanguageName(state.query.language), state.query.category?.label.orEmpty())
                            .filter { it.isNotBlank() }.joinToString(" · "), Modifier.weight(1f), color = Color.White.copy(.8f), maxLines = 1,
                            overflow = TextOverflow.Ellipsis, fontSize = 12.sp)
                        RadioTextButton("Zurücksetzen", "radio-reset", accent) { actions.query(RadioQuery()) }
                    }
                }
                if (state.error.isNotBlank()) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(state.error, color = Color.White, fontSize = 12.sp, modifier = Modifier.weight(1f))
                        RadioTextButton("Erneut laden", "radio-retry", accent, actions.reload)
                    }
                }
                if (state.loading && state.mode == RadioMode.DISCOVER) LinearProgressIndicator(Modifier.fillMaxWidth().testTag("radio-loading"), color = accent)
                if (state.partial && state.mode == RadioMode.DISCOVER) Text("Ein Teil der Sender konnte nicht geladen werden. Erneut laden ergänzt die Auswahl.", color = Color.White.copy(.7f), fontSize = 11.sp)
                if (shown.isEmpty() && !state.loading) {
                    Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                        Text(when (state.mode) {
                            RadioMode.FAVORITES -> "Noch keine passenden Favoriten. Mit dem Stern kannst du Sender speichern."
                            RadioMode.RECENT -> "Hier erscheinen deine zuletzt gehörten Sender."
                            RadioMode.DISCOVER -> if (state.error.isBlank()) "Keine passenden Sender gefunden. Passe die Filter an." else "Öffne Favoriten oder versuche es erneut."
                        }, color = Color.White.copy(.8f), modifier = Modifier.padding(18.dp), fontSize = if (isTv) 17.sp else 13.sp)
                    }
                } else {
                    LazyColumn(Modifier.weight(1f).fillMaxWidth().testTag("radio-stations"), state = list,
                        verticalArrangement = Arrangement.spacedBy(5.dp), contentPadding = PaddingValues(vertical = 7.dp)) {
                        itemsIndexed(shown, key = { _, station -> station.uuid }) { index, station ->
                            RadioStationRow(station, station.uuid in favorites, playback.station?.uuid == station.uuid,
                                accent, isTv, Modifier.then(v111RememberFocus(memory, station.uuid, index, isTv)),
                                { actions.play(station) }, { actions.favorite(station) })
                        }
                        if (state.mode == RadioMode.DISCOVER && state.more) item {
                            OutlinedButton(actions.more, Modifier.fillMaxWidth().v114FocusRing().testTag("radio-more"), enabled = !state.loading) { Text("Weitere Sender laden") }
                        }
                        if (state.cached && state.mode == RadioMode.DISCOVER) item {
                            Text("Gespeicherte Senderliste", color = Color.White.copy(.55f), fontSize = 11.sp)
                        }
                    }
                }
            }
        }
        Spacer(Modifier.height(if (isTv) 10.dp else 5.dp))
        RadioPlayerBar(playback, favorites, isTv, accent, actions)
    }

    picker?.let { type ->
        val all = when (type) {
            "country" -> listOf(RadioOption("", "Weltweit")) + state.countries
            "language" -> listOf(RadioOption("", "Alle Sprachen")) + state.languages
            else -> listOf(RadioOption("", "Alle Musikrichtungen & Themen")) + radioCategories.map { RadioOption(it.id, it.label) }
        }
        val selected = when (type) { "country" -> state.query.countryCode; "language" -> state.query.language; else -> state.query.categoryId }
        RadioPicker(when (type) { "country" -> "Land auswählen"; "language" -> "Sprache auswählen"; else -> "Musik & Themen" }, all, selected,
            isTv, accent, { picker = null }) { option ->
            actions.query(when (type) { "country" -> state.query.copy(countryCode = option.id); "language" -> state.query.copy(language = option.id); else -> state.query.copy(categoryId = option.id) })
            picker = null
        }
    }
    if (search) RadioSearchDialog("Sender suchen", state.query.name, isTv, accent, { search = false }) {
        actions.query(state.query.copy(name = it)); search = false
    }
}

@Composable
private fun RadioFilter(label: String, tag: String, modifier: Modifier, isTv: Boolean, onClick: () -> Unit) {
    OutlinedButton(onClick, modifier.height(44.dp).v114FocusRing().testTag(tag), contentPadding = PaddingValues(horizontal = 9.dp),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = Color(0xF20B111C), contentColor = Color.White)) {
        Text(label, maxLines = 1, overflow = TextOverflow.Ellipsis, fontSize = if (isTv) 13.sp else 11.sp)
    }
}

@Composable
private fun RadioTextButton(label: String, tag: String, accent: Color, onClick: () -> Unit) {
    TextButton(onClick, Modifier.v114FocusRing().testTag(tag), colors = ButtonDefaults.textButtonColors(contentColor = accent)) {
        Text(label, maxLines = 1, fontSize = 12.sp)
    }
}

@Composable
private fun RadioStationRow(station: RadioStation, favorite: Boolean, current: Boolean, accent: Color, isTv: Boolean,
    focus: Modifier, play: () -> Unit, save: () -> Unit) {
    Surface(Modifier.fillMaxWidth().height(if (isTv) 73.dp else 58.dp), color = if (current) Color(0xF2223043) else Color(0xF20C1420), shape = RoundedCornerShape(12.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Row(Modifier.weight(1f).fillMaxHeight().then(focus).v114FocusRing().testTag("radio-station-${station.uuid}")
                .clickable(role = Role.Button, onClick = play).padding(horizontal = 12.dp),
                verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                RadioLogo(station, Modifier.size(if (isTv) 48.dp else 38.dp), accent)
                Column(Modifier.weight(1f)) {
                    Text(station.name, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Color.White,
                        fontWeight = FontWeight.Bold, fontSize = if (isTv) 18.sp else 14.sp)
                    Text(station.description, maxLines = 1, overflow = TextOverflow.Ellipsis, color = Color.White.copy(.7f), fontSize = if (isTv) 12.sp else 10.sp)
                }
                if (current) Icon(Icons.Default.VolumeUp, "Aktueller Sender", tint = accent, modifier = Modifier.size(20.dp))
            }
            IconButton(save, Modifier.v114FocusRing().testTag("radio-favorite-${station.uuid}")) {
                Icon(if (favorite) Icons.Default.Star else Icons.Default.StarBorder,
                    if (favorite) "Favorit entfernen" else "Als Favorit speichern", tint = if (favorite) accent else Color.White)
            }
        }
    }
}

@Composable
private fun RadioLogo(station: RadioStation, modifier: Modifier, accent: Color) {
    Box(modifier.background(Color(0xFF1B2533), RoundedCornerShape(9.dp)), contentAlignment = Alignment.Center) {
        Icon(Icons.Default.Radio, null, tint = accent.copy(.7f), modifier = Modifier.fillMaxSize(.5f))
        if (station.logo.isNotBlank()) AsyncImage(station.logo, null, modifier = Modifier.fillMaxSize().padding(4.dp), contentScale = ContentScale.Fit)
    }
}

@Composable
private fun RadioPlayerBar(state: RadioPlaybackState, favorites: Set<String>, isTv: Boolean, accent: Color, actions: RadioActions) {
    Surface(Modifier.fillMaxWidth().height(if (isTv) 94.dp else 76.dp).testTag("radio-player"), color = Color(0xF509111D), contentColor = Color.White, shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, accent.copy(.35f))) {
        Row(Modifier.padding(horizontal = 12.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            val station = state.station
            if (station != null) RadioLogo(station, Modifier.size(if (isTv) 52.dp else 40.dp), accent)
            Column(Modifier.weight(1f)) {
                Text(station?.name ?: "Dein Radio. Weltweit.", color = Color.White, fontWeight = FontWeight.Bold,
                    fontSize = if (isTv) 19.sp else 14.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                Text(when { state.error.isNotBlank() -> state.error; state.buffering -> "Verbinde mit dem Sender …";
                    state.song.isNotBlank() -> state.song; state.playing -> "Live-Radio";
                    station != null -> "Pausiert"; else -> "Wähle einen Sender aus." },
                    color = Color.White.copy(.75f), fontSize = if (isTv) 13.sp else 11.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
            }
            if (station != null) IconButton({ actions.favorite(station) }, Modifier.v114FocusRing().testTag("radio-player-favorite")) {
                Icon(if (station.uuid in favorites) Icons.Default.Star else Icons.Default.StarBorder, "Favorit", tint = accent)
            }
            IconButton(actions.previous, Modifier.v114FocusRing().testTag("radio-previous"), enabled = state.previous) { Icon(Icons.Default.SkipPrevious, "Vorheriger Sender") }
            IconButton(actions.toggle, Modifier.v114FocusRing().testTag("radio-play-pause"), enabled = station != null && state.ready) {
                Icon(if (state.playing || state.buffering) Icons.Default.Pause else Icons.Default.PlayArrow,
                    if (state.playing || state.buffering) "Pause" else if (state.error.isNotBlank()) "Erneut versuchen" else "Abspielen")
            }
            IconButton(actions.next, Modifier.v114FocusRing().testTag("radio-next"), enabled = state.next) { Icon(Icons.Default.SkipNext, "Nächster Sender") }
            IconButton(actions.stop, Modifier.v114FocusRing().testTag("radio-stop"), enabled = station != null) { Icon(Icons.Default.Stop, "Radio stoppen") }
        }
    }
}

@Composable
private fun RadioPicker(title: String, options: List<RadioOption>, selected: String, isTv: Boolean, accent: Color,
    dismiss: () -> Unit, choose: (RadioOption) -> Unit) {
    var filter by remember { mutableStateOf("") }
    var keyboard by remember { mutableStateOf(false) }
    val shown = remember(options, filter) { options.filter { radioNormalized(it.label).contains(radioNormalized(filter)) || it.id.contains(filter, true) } }
    Dialog(dismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(Modifier.fillMaxWidth(if (isTv) .65f else .85f).fillMaxHeight(.87f).testTag("radio-picker"),
            color = Color(0xFF0B1421), contentColor = Color.White, shape = RoundedCornerShape(18.dp)) {
            Column(Modifier.padding(16.dp)) {
                Text(title, fontWeight = FontWeight.Bold, fontSize = 22.sp)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton({ keyboard = true }, Modifier.weight(1f).v114FocusRing()) { Text(filter.ifBlank { "Liste durchsuchen" }, maxLines = 1) }
                    TextButton(dismiss, Modifier.v114FocusRing().testTag("radio-picker-close")) { Text("Schließen") }
                }
                LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    items(shown, key = { it.id }) { option ->
                        OutlinedButton({ choose(option) }, Modifier.fillMaxWidth().height(48.dp).v114FocusRing().testTag("radio-option-${option.id}"),
                            colors = ButtonDefaults.outlinedButtonColors(containerColor = if (selected == option.id) accent.copy(.25f) else Color.Transparent)) {
                            Text(option.label, Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                            if (option.count > 0) Text(option.count.toString(), fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
    if (keyboard) RadioSearchDialog(title, filter, isTv, accent, { keyboard = false }) { filter = it; keyboard = false }
}

@Composable
private fun RadioSearchDialog(title: String, initial: String, isTv: Boolean, accent: Color, dismiss: () -> Unit, submit: (String) -> Unit) {
    if (isTv) V110TvKeyboardDialog(title, initial, accent, dismiss, onSubmit = submit)
    else {
        var value by remember { mutableStateOf(initial) }
        AlertDialog(onDismissRequest = dismiss, title = { Text(title) },
            text = { OutlinedTextField(value, { value = it.take(120) }, singleLine = true, label = { Text("Suchbegriff") }, modifier = Modifier.testTag("radio-search-field")) },
            confirmButton = { TextButton({ submit(value.trim()) }, Modifier.testTag("radio-search-submit")) { Text("Suchen") } },
            dismissButton = { TextButton(dismiss) { Text("Abbrechen") } })
    }
}
