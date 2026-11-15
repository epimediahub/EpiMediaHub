#!/usr/bin/env python3
"""v1.0.79 private QA: SmartTube video quality and creator-channel in player.

Extends existing v1.0.77 Media3 adaptive-track control; adds channel navigation
backed by pinned SmartTube MediaServiceCore. No change to current 1.0.78 intro,
EpiScene, VPN, IPTV, app signatures, or public update distribution.
"""
from pathlib import Path
import os

root=Path(os.environ["PROJECT_ROOT"])
ui=root/"app/src/main/java/de/epimediahub/app/ui"
tests=root/"app/src/test/java/de/epimediahub/app/ui"

def once(file,old,new):
    code=file.read_text(encoding="utf-8")
    if code.count(old)!=1:
        raise SystemExit("v179: changed baseline: "+str(file)+", anchor count "+str(code.count(old))+" => "+old[:120])
    file.write_text(code.replace(old,new,1),encoding="utf-8")

gradle=root/"app/build.gradle.kts"
once(gradle,"versionCode = 1078","versionCode = 1079")
once(gradle,'versionName = "1.0.78"','versionName = "1.0.79"')

# Stable ID is optional because Home/Search/Related providers sometimes give just a
# creator name; use a one-time metadata lookup on action rather than guessing URLs.
data=ui/"V100SmartTubeCore.kt"
once(data,"    val live: Boolean\n)","    val live: Boolean,\n    val channelId: String = \"\"\n)")

feed=ui/"V124SmartTubeFeed.kt"
once(feed, "item.durationMs.coerceAtLeast(0L), item.isLive))",
     "item.durationMs.coerceAtLeast(0L), item.isLive,\n"
     "                        item.channelId?.trim().orEmpty()))")

core=ui/"V108SmartTubeCore.kt"
once(core,
'''    private suspend fun <T : Any> collect(source: Observable<T>, timeoutSeconds: Long = 20L): List<T> =''',
'''    /**
     * Open the actual creator channel within EpiMediaHub, never a fabricated
     * channel URL. Preserve user playlists and device app settings.
     */
    suspend fun creatorChannel(context: Context, video: V100SmartTubeVideo):
        Result<List<V100SmartTubeRow>> = withContext(Dispatchers.IO) {
        try {
            val youtube = manager(context)
            val resolvedId = video.channelId.takeIf(V179SmartTubeChannel::validId)
                ?: collect(youtube.mediaItemService
                    .getMetadataObserve(video.videoId).take(1), 12L)
                    .firstOrNull()?.channelId?.trim().orEmpty()
            val id = resolvedId.takeIf(V179SmartTubeChannel::validId)
                ?: error("Für dieses Video konnte keine eindeutige Creator-Kanal-ID ermittelt werden.")
            val groups = collectGroups(youtube.contentService.getChannelObserve(id).take(12))
            Result.success(mapGroups(groups))
        } catch (cancelled: CancellationException) { throw cancelled }
          catch (failure: Exception) { Result.failure(failure) }
    }

    private suspend fun <T : Any> collect(source: Observable<T>, timeoutSeconds: Long = 20L): List<T> =''')
once(core,
'''            live = item.isLive
        )
    }''',
'''            live = item.isLive,
            channelId = item.channelId?.trim().orEmpty()
        )
    }''')

shell=ui/"V112SmartTubeShell.kt"
once(shell,
'''    var activePlayback by remember {
        mutableStateOf<Pair<V100SmartTubeVideo, V100SmartTubePlayback>?>(null)
    }''',
'''    var activePlayback by remember {
        mutableStateOf<Pair<V100SmartTubeVideo, V100SmartTubePlayback>?>(null)
    }
    var v179ChannelName by remember { mutableStateOf<String?>(null) }
    var v179ChannelRequest by remember { mutableIntStateOf(0) }''')
once(shell,
'''    val hideWatched = searchTitle.isBlank() && selectedSection != V108SmartTubeSection.HISTORY &&''',
'''    val hideWatched = v179ChannelName == null && searchTitle.isBlank() &&
        selectedSection != V108SmartTubeSection.HISTORY &&''')
once(shell,
'''    fun reloadSection(section: V108SmartTubeSection = selectedSection) {
        searchJob?.cancel()''',
'''    fun reloadSection(section: V108SmartTubeSection = selectedSection) {
        v179ChannelName = null
        searchJob?.cancel()''')
once(shell,
'''    fun nextVideoAfter(video: V100SmartTubeVideo): V100SmartTubeVideo? {''',
'''    fun openCreator(video: V100SmartTubeVideo) {
        if (video.author.isBlank()) return
        playJob?.cancel()
        resolvingId = null
        activePlayback = null // Releases player normally; no background content changes.
        v179ChannelName = video.author
        v179ChannelRequest++
        loading = true
        error = ""
        rows = emptyList()
        // A creator profile is a browsable shelf, not an external browser.
        searchJob?.cancel()
        searchJob = scope.launch {
            val currentRequest = v179ChannelRequest
            V108SmartTubeCore.creatorChannel(context, video)
                .onSuccess { result ->
                    if (currentRequest == v179ChannelRequest && v179ChannelName != null) {
                        rows = result
                        error = if (result.isEmpty()) "Noch keine Videos für diesen Kanal verfügbar." else ""
                    }
                }
                .onFailure {
                    if (currentRequest == v179ChannelRequest && v179ChannelName != null) {
                        error = "Creator-Kanal konnte nicht geöffnet werden: " +
                            (it.message ?: "Unbekannter Fehler")
                    }
                }
            if (currentRequest == v179ChannelRequest) loading = false
        }
    }

    fun nextVideoAfter(video: V100SmartTubeVideo): V100SmartTubeVideo? {''')
once(shell,
'''    LaunchedEffect(selectedSection, generation, authReady, auth.accountKey) {
        if (!authReady || searchTitle.isNotBlank()) return@LaunchedEffect''',
'''    LaunchedEffect(selectedSection, generation, authReady, auth.accountKey) {
        if (!authReady || searchTitle.isNotBlank() || v179ChannelName != null) return@LaunchedEffect''')
once(shell,
'''            onBack = ::closePlayback,''',
'''            onBack = ::closePlayback,
            onCreatorChannel = { openCreator(video) },''')
once(shell,
'''    BackHandler {
        if (searchTitle.isNotBlank()) {''',
'''    BackHandler {
        if (v179ChannelName != null) {
            v179ChannelRequest++
            reloadSection(selectedSection)
        } else if (searchTitle.isNotBlank()) {''')
once(shell,
'''                    onClick = onBack
                )
                Spacer(Modifier.width(if (isTv) 14.dp else 8.dp))''',
'''                    onClick = {
                        if (v179ChannelName != null) {
                            v179ChannelRequest++
                            reloadSection(selectedSection)
                        } else onBack()
                    }
                )
                Spacer(Modifier.width(if (isTv) 14.dp else 8.dp))''')
once(shell,
'''                        if (searchTitle.isNotBlank()) searchTitle else selectedSection.label,''',
'''                        v179ChannelName?.let { "Kanal · " + it }
                            ?: if (searchTitle.isNotBlank()) searchTitle else selectedSection.label,''')

# Top-right direct controls use existing overlays and channel callback; the
# D-pad MENU key opens first-party settings with quality and creator shortcuts.
player=ui/"V112SmartTubePlayer.kt"
once(player,
'''    historyAccountKey: String,''',
'''    onCreatorChannel: () -> Unit = {},
    historyAccountKey: String,''')
once(player,
'''    var showV176Quality by remember(video.videoId) { mutableStateOf(false) }''',
'''    var showV176Quality by remember(video.videoId) { mutableStateOf(false) }
    var showV179PlayerMenu by remember(video.videoId) { mutableStateOf(false) }''')
once(player,
'''        onQuality = { showV176Quality = true },''',
'''        onQuality = { showV179PlayerMenu = true },''')
once(player,
'''            TextButton(onClick = { showV176Quality = true },
                modifier = Modifier.align(Alignment.TopCenter).padding(top = 14.dp)) {
                Text("Qualität · " + V176SmartTubeQuality.label(v176ChosenHeight),
                    color = Color.White)
            }''',
'''            Row(
                modifier = Modifier.align(Alignment.TopEnd).padding(top = 14.dp, end = 20.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                TextButton(onClick = { showV176Quality = true }) {
                    Text("⚙ Qualität · " + V176SmartTubeQuality.label(v176ChosenHeight),
                        color = Color.White)
                }
                if (video.author.isNotBlank()) {
                    TextButton(onClick = onCreatorChannel) {
                        Text("◎ Zum Kanal", color = Color.White)
                    }
                }
            }''')
once(player,
'''                    Text(
                        video.author,
                        color = Color.White.copy(alpha = .74f),
                        fontSize = if (isTv) 17.sp else 13.sp,
                        fontWeight = FontWeight.SemiBold,
                        maxLines = 1
                    )''',
'''                    TextButton(onClick = onCreatorChannel) {
                        Text(
                            video.author + "  › Kanal öffnen",
                            color = Color.White.copy(alpha = .94f),
                            fontSize = if (isTv) 17.sp else 13.sp,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1
                        )
                    }''')
once(player,
'''    if (showV176Quality) {
        V176SmartTubeQualityDialog''',
'''    if (showV179PlayerMenu) {
        AlertDialog(
            onDismissRequest = { showV179PlayerMenu = false },
            title = { Text("SmartTube · Player-Optionen") },
            text = {
                Column {
                    TextButton(onClick = {
                        showV179PlayerMenu = false
                        showV176Quality = true
                    }) { Text("Bildqualität · " + V176SmartTubeQuality.label(v176ChosenHeight)) }
                    if (video.author.isNotBlank()) {
                        TextButton(onClick = {
                            showV179PlayerMenu = false
                            onCreatorChannel()
                        }) { Text("Creator-Kanal · " + video.author) }
                    }
                }
            },
            confirmButton = {
                TextButton(onClick = { showV179PlayerMenu = false }) {
                    Text("Schließen")
                }
            }
        )
    }
    if (showV176Quality) {
        V176SmartTubeQualityDialog''')

# Additional helper validates YouTube's real UC channel IDs; no guessed search,
# no fabricated link or channel with a matching visible display name.
helper=ui/"V179SmartTubeChannel.kt"
helper.write_text('''package de.epimediahub.app.ui

/** A visible creator name alone is not a unique YouTube channel identity. */
internal object V179SmartTubeChannel {
    private val channelPattern = Regex("^UC[A-Za-z0-9_-]{22}$")
    fun validId(id: String): Boolean = channelPattern.matches(id)
}
''',encoding="utf-8")

tests.mkdir(parents=True,exist_ok=True)
(tests/"V179SmartTubeChannelTest.kt").write_text('''package de.epimediahub.app.ui

import org.junit.Assert.*
import org.junit.Test

class V179SmartTubeChannelTest {
    @Test fun creatorRequiresRealChannelId() {
        assertTrue(V179SmartTubeChannel.validId("UC_x5XG1OV2P6uZZ5FSM9Ttw"))
        assertFalse(V179SmartTubeChannel.validId(""))
        assertFalse(V179SmartTubeChannel.validId("author name"))
        assertFalse(V179SmartTubeChannel.validId("https://youtube.com/@creator"))
        assertFalse(V179SmartTubeChannel.validId("UC_etc/../traverse"))
    }

    @Test fun existingVideoDataDoesNotRequireChannelId() {
        val data = V100SmartTubeVideo("id","Title","Author","","",5_000L,false)
        assertEquals("",data.channelId)
    }
}
''',encoding="utf-8")

assert 'onCreatorChannel = { openCreator(video) }' in shell.read_text()
assert 'SKIP_ANALYSIS_REMOTE_URL' not in shell.read_text()
assert 'showV176Quality' in player.read_text()
assert 'KEYCODE_MENU' in (ui/"V124SmartTubeBrowseLayer.kt").read_text()
assert 'V179SmartTubeChannel' in core.read_text()
print("V179_SMARTTUBE_CREATOR_AND_IN_PLAYER_QUALITY_PATCHED: no intro/backend changes")
