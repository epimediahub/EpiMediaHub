#!/usr/bin/env python3
"""Real SmartTube recommendations and a D-pad video shelf over continuing playback."""
import os
from pathlib import Path
import shutil

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent


def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f"{path}: expected one anchor, got {text.count(old)}: {old[:110]}"
    path.write_text(text.replace(old, new, 1))


gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1023", "versionCode = 1024")
replace_once(gradle, 'versionName = "1.0.23"', 'versionName = "1.0.24"')
for path in java.rglob("*.kt"):
    text = path.read_text()
    if "1.0.23" in text:
        path.write_text(text.replace("1.0.23", "1.0.24"))
for name in ("V108SmartTubeCore.kt", "V112SmartTubeSuggestions.kt", "V112SmartTubeWatchHistory.kt",
             "V124SmartTubeFeed.kt", "V124SmartTubeBrowseLayer.kt"):
    shutil.copyfile(here / name, java / "ui" / name)

shell = java / "ui/V112SmartTubeShell.kt"
replace_once(shell, '    var watchedRevision by remember { mutableIntStateOf(0) }', '''    var watchedRevision by remember { mutableIntStateOf(0) }
    var recommendationsDirty by remember { mutableStateOf(false) }
    var authReady by remember { mutableStateOf(false) }
    var playJob by remember { mutableStateOf<Job?>(null) }
    var playbackAccountKey by remember { mutableStateOf("guest") }
    val activeVideoId = activePlayback?.first?.videoId
    var relatedRows by remember(activeVideoId, playbackAccountKey) { mutableStateOf<List<V100SmartTubeRow>>(emptyList()) }
    var relatedLoading by remember(activeVideoId) { mutableStateOf(true) }
    var relatedError by remember(activeVideoId) { mutableStateOf("") }
    var relatedRevision by remember { mutableIntStateOf(0) }

    LaunchedEffect(activeVideoId, playbackAccountKey, relatedRevision) {
        val id = activeVideoId ?: return@LaunchedEffect
        relatedLoading = true
        relatedError = ""
        V108SmartTubeCore.related(context, id, playbackAccountKey)
            .onSuccess {
                relatedRows = it
                watched = withContext(Dispatchers.IO) { V112SmartTubeWatchHistory.watched(context, playbackAccountKey) }
            }
            .onFailure { relatedError = "Passende Videos konnten nicht geladen werden. Bitte erneut versuchen." }
        relatedLoading = false
    }

    fun closePlayback() {
        playJob?.cancel()
        resolvingId = null
        activePlayback = null
    }''')
replace_once(shell, '''        scope.launch {
            V108SmartTubeCore.resolvePlayback(context, video)''', '''        val accountKey = auth.accountKey
        playJob = scope.launch {
            V108SmartTubeCore.resolvePlayback(context, video)''')
replace_once(shell, '''                    activePlayback = video to playback''', '''                    if (accountKey == auth.accountKey) {
                        playbackAccountKey = accountKey
                        activePlayback = video to playback
                    }''')
replace_once(shell, '''    fun nextVideoAfter(video: V100SmartTubeVideo): V100SmartTubeVideo? =
        V112SmartTubeSuggestions.next(rows, video.videoId, if (hideWatched) watched else emptySet())''', '''    fun nextVideoAfter(video: V100SmartTubeVideo): V100SmartTubeVideo? {
        val queued = V112SmartTubeSuggestions.next(rows, video.videoId, if (hideWatched) watched else emptySet())
        val related = V112SmartTubeSuggestions.related(relatedRows, video.videoId, watched).firstOrNull()
        return if (selectedSection == V108SmartTubeSection.PLAYLISTS) queued ?: related else related ?: queued
    }''')
replace_once(shell, '''    LaunchedEffect(Unit) {
        auth = V108SmartTubeCore.authState(context)
    }''', '''    LaunchedEffect(Unit) {
        auth = V108SmartTubeCore.authState(context)
        authReady = true
    }''')
replace_once(shell, '''    LaunchedEffect(auth.accountKey) {
        watched =''', '''    LaunchedEffect(auth.accountKey) {
        rows = emptyList()
        watched =''')
replace_once(shell, '''    LaunchedEffect(activePlayback == null, watchedRevision) {
        if (activePlayback == null && watchedRevision > 0 && hideWatched) {''', '''    LaunchedEffect(activePlayback == null, recommendationsDirty, watchedRevision) {
        if (activePlayback == null && recommendationsDirty && hideWatched) {
            recommendationsDirty = false''')
replace_once(shell, '''    LaunchedEffect(selectedSection, generation) {
        if (searchTitle.isNotBlank()) return@LaunchedEffect''', '''    LaunchedEffect(selectedSection, generation, authReady, auth.accountKey) {
        if (!authReady || searchTitle.isNotBlank()) return@LaunchedEffect''')
replace_once(shell, '''                    rows = it
                    error = if (it.isEmpty()) {''', '''                    rows = it
                    watched = withContext(Dispatchers.IO) { V112SmartTubeWatchHistory.watched(context, auth.accountKey) }
                    error = if (it.isEmpty()) {''')
replace_once(shell, '''            onBack = { activePlayback = null },''', '''            onBack = ::closePlayback,
            suggestions = V112SmartTubeSuggestions.related(relatedRows, video.videoId, watched),
            suggestionsLoading = relatedLoading,
            suggestionsError = error.ifBlank { relatedError },
            resolvingId = resolvingId,
            onSelectVideo = ::play,
            onReloadSuggestions = { error = ""; relatedRevision++ },''')
replace_once(shell, '                if (next != null) play(next) else activePlayback = null',
    '                if (next != null) play(next) else closePlayback()')
replace_once(shell, '            historyAccountKey = auth.accountKey,', '            historyAccountKey = playbackAccountKey,')
replace_once(shell, '''            onProgress = { playedVideo, accountKey, position, duration, ended ->
                if (V112SmartTubeWatchRules''', '''            onProgress = { playedVideo, accountKey, position, duration, ended ->
                if (position > 0L && accountKey == auth.accountKey) recommendationsDirty = true
                if (V112SmartTubeWatchRules''')

player = java / "ui/V112SmartTubePlayer.kt"
replace_once(player, '    historyAccountKey: String,', '''    suggestions: List<V100SmartTubeVideo>, suggestionsLoading: Boolean, suggestionsError: String,
    resolvingId: String?, onSelectVideo: (V100SmartTubeVideo) -> Unit, onReloadSuggestions: () -> Unit,
    historyAccountKey: String,''')
replace_once(player, '    val remoteFocusRequester = remember { FocusRequester() }\n', '')
replace_once(player, '''    LaunchedEffect(player, video.videoId) {
        if (player != null) {
            runCatching { remoteFocusRequester.requestFocus() }
        }
    }

''', '')
replace_once(player, '''    BackHandler {
        runCatching { player?.stop() }
        onBack()
    }

''', '')
text = player.read_text()
start = text.index('    Box(\n        Modifier\n            .fillMaxSize()\n            .background(Color.Black)')
end = text.index('        if (player != null) {\n            AndroidView(', start)
text = text[:start] + '''    V124SmartTubeBrowseLayer(
        videoId = video.videoId, isTv = isTv, accent = accent,
        videos = suggestions, loading = suggestionsLoading, error = suggestionsError,
        resolvingId = resolvingId, onVideo = onSelectVideo, onRetry = onReloadSuggestions,
        onTogglePlayback = {
            player?.let { if (it.isPlaying) it.pause() else it.play() }
            controlsVisible = true
        },
        onSeek = ::seekBy, onShowControls = { controlsVisible = true },
        onExit = { runCatching { player?.stop() }; onBack() }
    ) { browsing ->
''' + text[end:]
player.write_text(text)
replace_once(player, '        if (controlsVisible && errorText.isBlank()) {',
    '        if (controlsVisible && !browsing && errorText.isBlank()) {')
replace_once(player, '        if (errorText.isNotBlank()) {', '        if (errorText.isNotBlank() && !browsing) {')
replace_once(player, '                            isFocusableInTouchMode = false',
    '                            isFocusableInTouchMode = false\n                            descendantFocusability = android.view.ViewGroup.FOCUS_BLOCK_DESCENDANTS')
replace_once(player, '"◀ 10 Sek.    OK Play/Pause    10 Sek. ▶"', '"◀ / ▶ 10 Sek.    OK Play/Pause    ↓ Weitere Videos"')
replace_once(player, 'if (isPlaying) "OK · Pause" else "OK · Wiedergabe"',
    'if (isPlaying) "OK · Pause    ↓ Weitere Videos" else "OK · Wiedergabe    ↓ Weitere Videos"')

tests = root / "app/src/test/java/de/epimediahub/app/ui"
for source in here.glob("*Test.kt"):
    shutil.copyfile(source, tests / source.name)
assert 'RadioPlaybackService.pauseForVideo()' in player.read_text()
assert 'Beliebt auf YouTube' not in (java / "ui/V108SmartTubeCore.kt").read_text()
print("Android 1.0.24: real related recommendations, persistent watched filter and in-player D-pad browsing installed")
