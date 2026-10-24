package de.epimediahub.app.ui

import android.content.Context
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage

/** A TV-remote navigable drawer over the currently mounted video.
 * Read-only until a separately reviewed authenticated comment-posting flow exists.
 */
@Composable
internal fun V183SmartTubeCommentsDrawer(
    videoId: String,
    commentsKey: String,
    metadataLoading: Boolean,
    context: Context,
    isTv: Boolean,
    onClose: () -> Unit
) {
    BackHandler(onBack = onClose)
    val closeFocus = remember { FocusRequester() }
    var comments by remember(videoId) { mutableStateOf<List<V183Comment>>(emptyList()) }
    var nextKey by remember(videoId) { mutableStateOf("") }
    var pageCount by remember(videoId) { mutableIntStateOf(0) }
    var busy by remember(videoId) { mutableStateOf(false) }
    var error by remember(videoId) { mutableStateOf("") }
    var loaded by remember(videoId) { mutableStateOf(false) }

    LaunchedEffect(Unit) {
        runCatching { closeFocus.requestFocus() }
    }

    LaunchedEffect(videoId, commentsKey, pageCount, metadataLoading) {
        if (metadataLoading || commentsKey.isBlank() && pageCount == 0) return@LaunchedEffect
        val key = if (pageCount == 0) commentsKey else nextKey
        if (key.isBlank()) return@LaunchedEffect
        busy = true
        error = ""
        V183SmartTubeSocial.comments(context, key)
            .onSuccess { page ->
                comments = (comments + page.items).distinctBy { it.id }
                nextKey = page.nextKey.takeIf { it != key }.orEmpty()
                loaded = true
            }.onFailure {
                error = "Kommentare konnten nicht geladen werden: " +
                    (it.message ?: "Verbindungsfehler").take(160)
                loaded = true
            }
        busy = false
    }

    Surface(
        modifier = Modifier
            .fillMaxWidth()
            .heightIn(max = if (isTv) 410.dp else 350.dp)
            .testTag("smarttube-comments-panel"),
        color = Color(0xF5141D2A),
        shape = RoundedCornerShape(topStart = 18.dp, topEnd = 18.dp)
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(
                horizontal = if (isTv) 26.dp else 14.dp,
                vertical = 12.dp
            )
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Kommentare zum Video",
                    modifier = Modifier.weight(1f),
                    fontSize = if (isTv) 22.sp else 18.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White
                )
                TextButton(
                    onClick = onClose,
                    modifier = Modifier.focusRequester(closeFocus)
                        .v114FocusRing().testTag("smarttube-close-comments")
                ) { Text("✕ Schließen", color = Color.White) }
            }

            if (metadataLoading || busy && comments.isEmpty()) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(21.dp), strokeWidth = 2.dp)
                    Spacer(Modifier.width(12.dp))
                    Text("Kommentare werden geladen …", color = Color.White)
                }
            } else if (commentsKey.isBlank()) {
                Text(
                    "Für dieses Video sind Kommentare nicht verfügbar oder deaktiviert.",
                    color = Color.LightGray,
                    modifier = Modifier.padding(vertical = 16.dp)
                )
            } else if (error.isNotBlank() && comments.isEmpty()) {
                Text(error, color = Color(0xFFFFD19D), modifier = Modifier.padding(vertical = 16.dp))
            } else if (loaded && comments.isEmpty()) {
                Text("Für dieses Video wurden keine Kommentare geliefert.",
                    color = Color.LightGray, modifier = Modifier.padding(vertical = 16.dp))
            }

            if (comments.isNotEmpty()) {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().weight(1f, fill = false),
                    contentPadding = PaddingValues(bottom = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(9.dp)
                ) {
                    itemsIndexed(comments, key = { index, c -> c.id + "-" + index }) { _, item ->
                        Row(
                            modifier = Modifier.fillMaxWidth()
                                .background(Color(0xFF233142), RoundedCornerShape(10.dp))
                                .v114FocusRing()
                                .focusable()
                                .padding(10.dp),
                            verticalAlignment = Alignment.Top
                        ) {
                            if (item.avatar.isNotBlank()) {
                                AsyncImage(
                                    model = item.avatar,
                                    contentDescription = null,
                                    modifier = Modifier.size(35.dp),
                                    contentScale = ContentScale.Crop
                                )
                                Spacer(Modifier.width(10.dp))
                            }
                            Column {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text(item.author, color = Color.White,
                                        fontWeight = FontWeight.Bold,
                                        fontSize = if (isTv) 15.sp else 13.sp,
                                        maxLines = 1)
                                    Spacer(Modifier.width(10.dp))
                                    Text(item.date, color = Color.LightGray,
                                        fontSize = 11.sp, maxLines = 1)
                                }
                                Text(item.message, color = Color.White,
                                    fontSize = if (isTv) 14.sp else 12.sp,
                                    maxLines = 9, overflow = TextOverflow.Ellipsis)
                                if (item.likes.isNotBlank() || item.replies.isNotBlank()) {
                                    Text(
                                        (if (item.likes.isNotBlank()) "♥ " + item.likes + "   " else "") +
                                            (if (item.replies.isNotBlank()) "Antworten: " + item.replies else ""),
                                        color = Color(0xFFB6CADF), fontSize = 11.sp
                                    )
                                }
                            }
                        }
                    }
                    if (nextKey.isNotBlank() || busy) {
                        item {
                            TextButton(
                                enabled = !busy && nextKey.isNotBlank(),
                                onClick = { pageCount++ },
                                modifier = Modifier.v114FocusRing()
                                    .testTag("smarttube-more-comments")
                            ) {
                                Text(if (busy) "Lade Kommentare …" else "Mehr Kommentare laden",
                                    color = Color.White)
                            }
                        }
                    }
                    if (error.isNotBlank()) {
                        item { Text(error, color = Color(0xFFFFD19D)) }
                    }
                }
            }
        }
    }
}
