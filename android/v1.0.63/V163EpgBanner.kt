package de.epimediahub.app.ui

import androidx.compose.runtime.*
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.data.V163Epg
import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.delay

@Composable
internal fun v163EpgClock(key: String, events: List<EpgItem>): Long {
    var now by remember(key) { mutableLongStateOf(System.currentTimeMillis() / 1000L) }
    val latest by rememberUpdatedState(events)
    LaunchedEffect(key) {
        while (true) {
            val boundary = V163Epg.current(latest, now)?.end
            delay(boundary?.let { ((it - now) * 1000L + 100L).coerceIn(100L, 30_000L) } ?: 30_000L)
            now = System.currentTimeMillis() / 1000L
        }
    }
    return now
}

@Composable
internal fun V163EpgBanner(vm: MainViewModel, item: MediaEntry, events: List<EpgItem>): String {
    if (item.kind != MediaKind.LIVE) return ""
    val now = v163EpgClock(item.resumeKey, events)
    val current = V163Epg.current(events, now)
    LaunchedEffect(item.resumeKey, now) { vm.ensureEpg(item, priority = true) }
    return current?.title.orEmpty()
}
