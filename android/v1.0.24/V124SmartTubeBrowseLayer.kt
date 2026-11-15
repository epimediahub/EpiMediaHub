@file:OptIn(androidx.compose.ui.ExperimentalComposeUiApi::class)

package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.InputMode
import androidx.compose.ui.input.key.*
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalInputModeManager
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import kotlinx.coroutines.delay

/** Browsing only changes focus/UI state. The video surface and player stay mounted. */
@Composable
internal fun V124SmartTubeBrowseLayer(
    videoId: String, isTv: Boolean, accent: Color,
    videos: List<V100SmartTubeVideo>, loading: Boolean, error: String,
    resolvingId: String?, onVideo: (V100SmartTubeVideo) -> Unit, onRetry: () -> Unit,
    onTogglePlayback: () -> Unit, onSeek: (Long) -> Unit, onShowControls: () -> Unit,
    onExit: () -> Unit, content: @Composable BoxScope.(Boolean) -> Unit
) {
    var browsing by remember(videoId) { mutableStateOf(false) }
    var focusedId by remember(videoId) { mutableStateOf<String?>(null) }
    val remote = remember { FocusRequester() }
    val first = remember { FocusRequester() }
    val empty = remember { FocusRequester() }
    val mode = LocalInputModeManager.current
    val row = rememberLazyListState()
    fun close() { browsing = false; onShowControls() }
    BackHandler { if (browsing) close() else onExit() }
    LaunchedEffect(videoId, browsing, videos.isEmpty(), focusedId?.let { id -> videos.any { it.videoId == id } }) {
        if (isTv) mode.requestInputMode(InputMode.Keyboard)
        if (!browsing) {
            focusedId = null
            remote.requestFocus()
        } else if (focusedId == null || videos.none { it.videoId == focusedId }) {
            if (videos.isNotEmpty()) row.scrollToItem(0)
            // Wait for the first lazy item after opening or after the async result arrives.
            delay(80L)
            if (videos.isEmpty()) empty.requestFocus() else first.requestFocus()
        }
    }
    Box(Modifier.fillMaxSize().background(Color.Black)
        .focusRequester(remote)
        .onPreviewKeyEvent { event ->
            if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
            val repeated = event.nativeKeyEvent.repeatCount > 0
            when {
                event.key == Key.MediaPlayPause -> { if (!repeated) onTogglePlayback(); true }
                browsing && event.key == Key.DirectionUp -> { if (!repeated) close(); true }
                browsing -> false // The focused card owns OK and Left/Right; never seek behind it.
                event.key == Key.DirectionDown -> { if (!repeated) browsing = true; true }
                event.key == Key.DirectionUp -> { onShowControls(); true }
                event.key == Key.DirectionLeft -> { onSeek(-10_000L); true }
                event.key == Key.DirectionRight -> { onSeek(10_000L); true }
                event.key == Key.DirectionCenter || event.key == Key.Enter || event.key == Key.NumPadEnter -> {
                    if (!repeated) onTogglePlayback(); true
                }
                else -> false
            }
        }.focusable().testTag("smarttube-player-remote")) {
        content(browsing)
        if (!browsing && !isTv) {
            TextButton(onClick = { browsing = true }, modifier = Modifier.align(Alignment.TopEnd).padding(12.dp)) {
                Text("Weitere Videos", color = Color.White)
            }
        }
        if (browsing) {
            val compact = LocalConfiguration.current.screenHeightDp < 420
            val cardWidth = if (isTv && !compact) 232.dp else 176.dp
            val imageHeight = if (isTv && !compact) 130.dp else 99.dp
            Surface(Modifier.align(Alignment.BottomCenter).fillMaxWidth().testTag("smarttube-video-shelf"),
                color = Color(0xF5101721), border = BorderStroke(1.dp, Color(0xFF344657)),
                shape = RoundedCornerShape(topStart = 16.dp, topEnd = 16.dp)) {
                Column(Modifier.padding(vertical = if (compact) 10.dp else 16.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(Modifier.fillMaxWidth().padding(horizontal = 24.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text("Weitere Videos", Modifier.weight(1f), color = Color.White,
                            fontSize = if (compact) 19.sp else 23.sp, fontWeight = FontWeight.Bold)
                        if (loading || resolvingId != null) CircularProgressIndicator(
                            Modifier.padding(end = 12.dp).size(20.dp), color = accent, strokeWidth = 2.dp)
                        Text(if (isTv) "↑ oder Zurück · Schließen" else "Wiedergabe läuft weiter",
                            color = Color(0xFFB2C1D2), fontSize = 12.sp)
                    }
                    if (error.isNotBlank()) Text(error, Modifier.padding(horizontal = 24.dp),
                        color = Color(0xFFFFD59A), fontSize = 13.sp, maxLines = 2, overflow = TextOverflow.Ellipsis)
                    if (videos.isEmpty()) {
                        Column(Modifier.fillMaxWidth().padding(horizontal = 24.dp)) {
                            Text(if (loading) "Passende Videos werden geladen …" else "Momentan keine weiteren ungesehenen Videos verfügbar.",
                                color = Color.LightGray, fontSize = 14.sp)
                            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                TextButton(onClick = ::close, modifier = Modifier.focusRequester(empty)
                                    .v114FocusRing().testTag("smarttube-shelf-close")) { Text("Zur Wiedergabe", color = Color.White) }
                                if (!loading) TextButton(onClick = onRetry, modifier = Modifier.v114FocusRing()
                                    .testTag("smarttube-shelf-retry")) { Text("Erneut laden", color = Color.White) }
                            }
                        }
                    } else {
                        LazyRow(state = row, contentPadding = PaddingValues(horizontal = 24.dp, vertical = 4.dp),
                            horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                            itemsIndexed(videos, key = { _, video -> video.videoId }) { index, video ->
                                var focused by remember { mutableStateOf(false) }
                                Surface(onClick = { if (resolvingId == null) onVideo(video) },
                                    modifier = Modifier.width(cardWidth)
                                        .then(if (index == 0) Modifier.focusRequester(first) else Modifier)
                                        .onFocusChanged { focused = it.isFocused; if (it.isFocused) focusedId = video.videoId }
                                        .testTag("smarttube-suggestion-${video.videoId}"),
                                    color = if (focused) Color(0xFF263A51) else Color(0xFF182431),
                                    shape = RoundedCornerShape(10.dp),
                                    border = BorderStroke(if (focused) 3.dp else 1.dp, if (focused) Color.White else Color(0xFF3A4B5E))) {
                                    Column {
                                        Box(Modifier.fillMaxWidth().height(imageHeight).background(Color(0xFF29394A))) {
                                            if (video.image.isNotBlank()) AsyncImage(video.image, video.title,
                                                Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                                            else Text("▶", Modifier.align(Alignment.Center), color = Color.White, fontSize = 30.sp)
                                            if (resolvingId == video.videoId) CircularProgressIndicator(
                                                Modifier.align(Alignment.Center).size(30.dp), color = Color.White)
                                            if (video.live) Text("LIVE", Modifier.align(Alignment.BottomStart).padding(8.dp)
                                                .background(Color(0xFFBA2626)).padding(horizontal = 5.dp), color = Color.White, fontSize = 11.sp)
                                        }
                                        Column(Modifier.padding(10.dp)) {
                                            Text(video.title, color = Color.White, fontSize = if (compact) 13.sp else 15.sp,
                                                lineHeight = if (compact) 17.sp else 20.sp, fontWeight = FontWeight.SemiBold,
                                                maxLines = 2, minLines = 2, overflow = TextOverflow.Ellipsis)
                                            Text(video.author, color = Color(0xFFB3C3D5), fontSize = 12.sp, maxLines = 1,
                                                overflow = TextOverflow.Ellipsis)
                                        }
                                    }
                                }
                            }
                        }
                        if (!isTv) TextButton(onClick = ::close, modifier = Modifier.align(Alignment.End).padding(end = 20.dp)) {
                            Text("Schließen", color = Color.White)
                        }
                    }
                }
            }
        }
    }
}
