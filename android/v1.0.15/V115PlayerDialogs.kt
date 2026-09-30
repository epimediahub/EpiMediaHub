package de.epimediahub.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyListState
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import androidx.media3.common.C
import de.epimediahub.app.model.MediaEntry
import kotlinx.coroutines.delay

@Composable
internal fun V115TrackDialog(state: V115PlaybackUiState, isTv: Boolean, onDismiss: () -> Unit,
    onTrack: (V115TrackChoice) -> Unit, onOff: () -> Unit) {
    val audio = remember(state.tracks) { V115Tracks.choices(state.tracks, C.TRACK_TYPE_AUDIO) }
    val subtitles = remember(state.tracks) { V115Tracks.choices(state.tracks, C.TRACK_TYPE_TEXT) }
    val first = remember { FocusRequester() }
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        val inputMode = LocalInputModeManager.current
        Surface(Modifier.fillMaxWidth(if (isTv) .88f else .94f).widthIn(max = 980.dp).testTag("vod-track-dialog"),
            color = Color(0xFF151515), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Color.DarkGray)) {
            Column(Modifier.padding(if (isTv) 24.dp else 18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Text("Audio und Untertitel", color = Color.White, fontWeight = FontWeight.Bold, fontSize = if (isTv) 26.sp else 22.sp)
                @Composable fun AudioColumn(modifier: Modifier) {
                    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Tonspur / Sprache", color = Color.LightGray, fontSize = if (isTv) 20.sp else 17.sp)
                        if (audio.isEmpty()) Text("Der Anbieter hat noch keine auswählbare Tonspur gemeldet.", color = Color.LightGray, fontSize = 16.sp)
                        LazyColumn(Modifier.fillMaxWidth().heightIn(max = if (isTv) 270.dp else 155.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            items(audio.size) { index ->
                                val choice = audio[index]
                                V115Option(choice.label, choice.selected, isTv,
                                    Modifier.then(if (index == 0) Modifier.focusRequester(first) else Modifier).testTag("track-audio-$index")) { onTrack(choice) }
                            }
                        }
                    }
                }
                @Composable fun SubtitleColumn(modifier: Modifier) {
                    Column(modifier, verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Untertitel", color = Color.LightGray, fontSize = if (isTv) 20.sp else 17.sp)
                        LazyColumn(Modifier.fillMaxWidth().heightIn(max = if (isTv) 270.dp else 180.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                            item {
                                V115Option("Aus", state.subtitlesDisabled || subtitles.none { it.selected }, isTv,
                                    Modifier.then(if (audio.isEmpty()) Modifier.focusRequester(first) else Modifier).testTag("track-subtitles-off"), onOff)
                            }
                            items(subtitles.size) { index ->
                                val choice = subtitles[index]
                                V115Option(choice.label, choice.selected && !state.subtitlesDisabled, isTv, Modifier.testTag("track-subtitle-$index")) { onTrack(choice) }
                            }
                        }
                        if (subtitles.isEmpty()) Text("Für dieses Video wurden keine verfügbaren Untertitel angeboten.", color = Color.LightGray, fontSize = 16.sp)
                    }
                }
                if (isTv) Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(24.dp)) {
                    AudioColumn(Modifier.weight(1f)); SubtitleColumn(Modifier.weight(1f))
                } else Column(verticalArrangement = Arrangement.spacedBy(16.dp)) {
                    AudioColumn(Modifier.fillMaxWidth()); SubtitleColumn(Modifier.fillMaxWidth())
                }
                Text("Zeitmarken: SkipDB (skipdb.tv, ODbL 1.0), TheIntroDB (theintrodb.org), IntroDB (introdb.app). Serienzuordnung: TVmaze (tvmaze.com, CC BY-SA).",
                    color = Color.Gray, fontSize = if (isTv) 13.sp else 11.sp)
                TextButton(onClick = onDismiss, modifier = Modifier.v114FocusRing().testTag("vod-track-close")) { Text("Schließen", color = Color.White, fontSize = 18.sp) }
            }
        }
        LaunchedEffect(Unit) { if (isTv) { inputMode.requestInputMode(InputMode.Keyboard); delay(110L); runCatching { first.requestFocus() } } }
    }
}

@Composable
private fun V115Option(label: String, selected: Boolean, isTv: Boolean, modifier: Modifier, onClick: () -> Unit) {
    OutlinedButton(onClick = onClick, modifier = modifier.fillMaxWidth().heightIn(min = if (isTv) 54.dp else 48.dp).v114FocusRing(),
        border = BorderStroke(if (selected) 2.dp else 1.dp, if (selected) Color.White else Color.DarkGray), shape = RoundedCornerShape(6.dp),
        colors = ButtonDefaults.outlinedButtonColors(containerColor = if (selected) Color(0xFF343434) else Color.Transparent, contentColor = Color.White),
        contentPadding = PaddingValues(horizontal = 14.dp, vertical = 10.dp)) {
        Text((if (selected) "✓  " else "") + label, modifier = Modifier.weight(1f), fontSize = if (isTv) 18.sp else 16.sp)
    }
}

@Composable
internal fun V115EpisodeDialog(current: MediaEntry, episodes: List<MediaEntry>, season: Int, listState: LazyListState,
    isTv: Boolean, onDismiss: () -> Unit, onSeason: (Int) -> Unit, onEpisode: (MediaEntry) -> Unit) {
    val visible = episodes.filter { it.season == season }
    val first = remember(season) { FocusRequester() }
    val initialIndex = listState.firstVisibleItemIndex.coerceAtMost(visible.lastIndex.coerceAtLeast(0))
    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        val inputMode = LocalInputModeManager.current
        Surface(Modifier.fillMaxWidth(if (isTv) .80f else .94f).widthIn(max = 900.dp).testTag("vod-episode-dialog"),
            color = Color(0xFF151515), shape = RoundedCornerShape(12.dp), border = BorderStroke(1.dp, Color.DarkGray)) {
            Column(Modifier.padding(if (isTv) 24.dp else 18.dp), verticalArrangement = Arrangement.spacedBy(14.dp)) {
                Text(current.categoryId.ifBlank { "Folgen auswählen" }, color = Color.White, fontSize = if (isTv) 27.sp else 22.sp, fontWeight = FontWeight.Bold)
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    episodes.map { it.season }.distinct().sorted().forEach { s ->
                        OutlinedButton(onClick = { onSeason(s) }, modifier = Modifier.v114FocusRing().testTag("vod-season-$s"),
                            border = BorderStroke(if (season == s) 2.dp else 1.dp, if (season == s) Color.White else Color.Gray),
                            colors = ButtonDefaults.outlinedButtonColors(containerColor = if (season == s) Color(0xFF343434) else Color.Transparent)) {
                            Text(if (s == 0) "Extras" else "Staffel $s", color = Color.White, fontSize = if (isTv) 19.sp else 16.sp)
                        }
                    }
                }
                LazyColumn(Modifier.fillMaxWidth().heightIn(max = if (isTv) 285.dp else 370.dp).testTag("vod-episode-list"), state = listState,
                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    items(visible, key = { it.resumeKey }) { episode ->
                        val index = visible.indexOf(episode)
                        V115Option("Folge ${episode.episode} · ${episode.name}", episode.resumeKey == current.resumeKey, isTv,
                            Modifier.then(if (index == initialIndex) Modifier.focusRequester(first) else Modifier).testTag("vod-episode-${episode.season}-${episode.episode}")) { onEpisode(episode) }
                    }
                }
                TextButton(onClick = onDismiss, modifier = Modifier.v114FocusRing().testTag("vod-episode-close")) { Text("Schließen", color = Color.White, fontSize = 18.sp) }
            }
        }
        LaunchedEffect(season) { if (isTv) { inputMode.requestInputMode(InputMode.Keyboard); delay(110L); runCatching { first.requestFocus() } } }
    }
}
