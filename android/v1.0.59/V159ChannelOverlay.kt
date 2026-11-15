package de.epimediahub.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

/**
 * Select from the channels already in the active Live category.
 * Showing this overlay never starts a second stream; selection does.
 */
@Composable
internal fun V159ChannelOverlay(
    channels: List<MediaEntry>,
    current: MediaEntry,
    isTv: Boolean,
    onChoose: (MediaEntry) -> Unit,
    onDismiss: () -> Unit
) {
    val live = remember(channels) { channels.filter { it.kind == MediaKind.LIVE } }
    val selected = live.indexOfFirst { it.id == current.id &&
        (it.sourceProfileId == current.sourceProfileId ||
         it.sourceProfileId.isBlank() || current.sourceProfileId.isBlank()) }.coerceAtLeast(0)
    val state = rememberLazyListState(initialFirstVisibleItemIndex = selected)
    val initialFocus = remember(current.resumeKey) { FocusRequester() }

    Dialog(onDismissRequest = onDismiss, properties = DialogProperties(usePlatformDefaultWidth = false)) {
        Surface(
            modifier = Modifier.fillMaxWidth(if (isTv) .64f else .94f).fillMaxHeight(.86f).testTag("live-channel-dialog"),
            shape = MaterialTheme.shapes.large,
            color = Color(0xF20B111B)
        ) {
            Column(Modifier.fillMaxSize().padding(16.dp)) {
                Text("Kanalliste", color = Color.White, fontSize = if (isTv) 25.sp else 20.sp)
                Spacer(Modifier.height(10.dp))
                if (live.isEmpty()) {
                    Text("Keine Sender in dieser Kategorie", color = Color.White)
                } else {
                    LazyColumn(state = state, modifier = Modifier.weight(1f)) {
                        itemsIndexed(live, key = { _, channel -> channel.sourceProfileId + ":" + channel.id }) { index, channel ->
                            val active = index == selected
                            TextButton(
                                onClick = { onChoose(channel) },
                                modifier = Modifier.fillMaxWidth().heightIn(min = if (isTv) 54.dp else 44.dp)
                                    .then(if (active) Modifier.focusRequester(initialFocus) else Modifier)
                                    .testTag("live-channel-choice-" + index),
                                colors = ButtonDefaults.textButtonColors(
                                    contentColor = if (active) Color(0xFFFFD47B) else Color.White
                                )
                            ) {
                                Text((if (active) "▶  " else "") + channel.name, maxLines = 1,
                                    overflow = TextOverflow.Ellipsis, modifier = Modifier.fillMaxWidth())
                            }
                        }
                    }
                }
                TextButton(onClick = onDismiss, modifier = Modifier.testTag("live-channel-close")) {
                    Text("Schließen", color = Color.White)
                }
            }
        }
    }
    LaunchedEffect(current.resumeKey, live.size) {
        if (live.isNotEmpty()) {
            state.scrollToItem(selected)
            runCatching { initialFocus.requestFocus() }
        }
    }
}
