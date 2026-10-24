#!/usr/bin/env python3
"""EpiMediaHub 1.0.84: preserve SmartTube video across creator/back, resume by account,
match YouTube content cadence on TV, and seek 10 s tap / 30 s per held repeat.

Apply AFTER v1.0.83; fail closed if expected source differs. Do not alter EpiScene,
VPN, Fire-TV license, intro, or customer updater without a signed verified build.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
ui = root / "app/src/main/java/de/epimediahub/app/ui"
tests = root / "app/src/test/java/de/epimediahub/app/ui"

def once(path: Path, before: str, after: str) -> None:
    old = path.read_text(encoding="utf-8")
    count = old.count(before)
    if count != 1:
        raise SystemExit("STOP_V184_BASELINE_DRIFT " + path.name + " " + str(count) + " " + repr(before[:95]))
    path.write_text(old.replace(before, after, 1), encoding="utf-8")

gradle = root / "app/build.gradle.kts"
once(gradle, "versionCode = 1083", "versionCode = 1084")
once(gradle, 'versionName = "1.0.83"', 'versionName = "1.0.84"')
for filename in ("V184SmartTubeResume.kt", "V184SmartTubeSeekPolicy.kt"):
    shutil.copy2(here / filename, ui / filename)
tests.mkdir(parents=True, exist_ok=True)
shutil.copy2(here / "V184SmartTubeResumeTest.kt", tests / "V184SmartTubeResumeTest.kt")

shell = ui / "V112SmartTubeShell.kt"
once(shell,
     "    var v179ChannelRequest by remember { mutableIntStateOf(0) }",
     """    var v179ChannelRequest by remember { mutableIntStateOf(0) }
    // A channel opened from playback is a nested screen: Back returns to THAT video.
    var v184ReturnPlayback by remember {
        mutableStateOf<Pair<V100SmartTubeVideo, V100SmartTubePlayback>?>(null)
    }
    var v184ReturnRows by remember { mutableStateOf<List<V100SmartTubeRow>>(emptyList()) }""")
once(shell,
     "        activePlayback = null // Releases player normally; no background content changes.",
     """        v184ReturnPlayback = activePlayback
        v184ReturnRows = rows
        activePlayback = null // Save position on disposal; the old PlayerView is released.""")
once(shell,
     "    fun nextVideoAfter(video: V100SmartTubeVideo): V100SmartTubeVideo? {",
     """    fun returnFromCreator() {
        v179ChannelRequest++ // Invalidate in-flight channel fetch before restoring the player.
        searchJob?.cancel()
        v179ChannelName = null
        val formerVideo = v184ReturnPlayback
        v184ReturnPlayback = null
        if (formerVideo != null) {
            rows = v184ReturnRows
            error = ""
            loading = false
            resolvingId = null
            activePlayback = formerVideo // New player seeks to saved local playback position.
        } else {
            reloadSection(selectedSection)
        }
        v184ReturnRows = emptyList()
    }

    fun nextVideoAfter(video: V100SmartTubeVideo): V100SmartTubeVideo? {""")
once(shell,
     """        if (v179ChannelName != null) {
            v179ChannelRequest++
            reloadSection(selectedSection)
        } else if (searchTitle.isNotBlank()) {""",
     """        if (v179ChannelName != null) {
            returnFromCreator()
        } else if (searchTitle.isNotBlank()) {""")
once(shell,
     """                        if (v179ChannelName != null) {
                            v179ChannelRequest++
                            reloadSection(selectedSection)
                        } else onBack()""",
     """                        if (v179ChannelName != null) {
                            returnFromCreator()
                        } else onBack()""")
# Opening another video from the creator page intentionally drops the old
# return target; its progress was already saved when it was detached.
once(shell,
     "                    activePlayback = video to playback",
     """                    if (v179ChannelName != null) {
                        v184ReturnPlayback = null
                        v184ReturnRows = emptyList()
                    }
                    activePlayback = video to playback""")

player = ui / "V112SmartTubePlayer.kt"
once(player,
     "        var lastReportAt = System.currentTimeMillis()",
     "        var lastReportAt = System.currentTimeMillis()\n        var lastResumeSaveAt = 0L")
once(player,
     "            val now = System.currentTimeMillis()",
     """            val now = System.currentTimeMillis()
            if (!video.live && player.isPlaying && now - lastResumeSaveAt >= 5_000L) {
                V184SmartTubeResume.save(context, historyAccountKey, video.videoId, positionMs, duration)
                lastResumeSaveAt = now
            }""")
once(player,
     "        onExit = { runCatching { player?.stop() }; onBack() }",
     """        onExit = {
            // Save BEFORE stop, otherwise ExoPlayer may reset position to zero.
            if (!video.live && player != null) {
                V184SmartTubeResume.save(context, historyAccountKey, video.videoId,
                    player.currentPosition, player.duration)
            }
            runCatching { player?.stop() }
            onBack()
        }""")
once(player,
     """                        endDispatched = true
                        reportProgress(video,""",
     """                        endDispatched = true
                        V184SmartTubeResume.clear(context, historyAccountKey, video.videoId)
                        reportProgress(video,""")
once(player,
     """                player.setMediaItem(item)
                player.prepare()""",
     """                player.setMediaItem(item)
                if (!video.live) {
                    val savedPosition = V184SmartTubeResume.read(context, historyAccountKey, video.videoId)
                    if (savedPosition > 0L) player.seekTo(savedPosition)
                }
                player.prepare()""")
once(player,
     """            onDispose {
                runCatching {
                    reportProgress(video,""",
     """            onDispose {
                if (!video.live && !endDispatched) {
                    // Leaving for a creator channel also saves exact progress.
                    V184SmartTubeResume.save(context, historyAccountKey, video.videoId,
                        player.currentPosition, player.duration)
                }
                runCatching {
                    reportProgress(video,""")
# Reuse proven Android TV cinema cadence controller, including HDMI mode restore
# when the view closes; no forced global 60 Hz and no changes to IPTV streams.
once(player, "PlayerView(it).apply {",
     "V121VideoView(it).apply {\n                            bind(player, isTv, cinemaVod = true)")
once(player, "update = { (it as? PlayerView)?.player = player },",
     "update = { (it as? V121VideoView)?.bind(player, isTv, cinemaVod = true) },")
once(player, "onRelease = { (it as? PlayerView)?.player = null },",
     "onRelease = { (it as? V121VideoView)?.close() },")
# Keep the existing PlayerView import harmless; retaining it is not required.

browse = ui / "V124SmartTubeBrowseLayer.kt"
once(browse,
     "    val row = rememberLazyListState()",
     """    val row = rememberLazyListState()
    // Remember a held seek even after the first tap makes playback controls visible.
    var v184HeldSeek by remember(videoId) { mutableIntStateOf(0) }""")
once(browse,
     """        .onPreviewKeyEvent { event ->
            if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false""",
     """        .onPreviewKeyEvent { event ->
            if (event.type == KeyEventType.KeyUp &&
                event.key in setOf(Key.DirectionLeft, Key.DirectionRight)) {
                v184HeldSeek = 0
                return@onPreviewKeyEvent false
            }
            if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false""")
once(browse,
     """                commentsShown -> false
                event.nativeKeyEvent.keyCode == android.view.KeyEvent.KEYCODE_MENU -> {""",
     """                commentsShown -> false
                // In fullscreen, D-pad Left/Right seeks instead of only opening
                // the controls. Existing focused buttons/comments still own D-pad.
                event.key in setOf(Key.DirectionLeft, Key.DirectionRight) &&
                    (!controlsShown || v184HeldSeek != 0) -> {
                    val direction = if (event.key == Key.DirectionLeft) -1 else 1
                    if (v184HeldSeek == 0 || v184HeldSeek == direction) {
                        v184HeldSeek = direction
                        onSeek(V184SmartTubeSeekPolicy.deltaMs(
                            direction, event.nativeKeyEvent.repeatCount))
                    }
                    true
                }
                event.nativeKeyEvent.keyCode == android.view.KeyEvent.KEYCODE_MENU -> {""")

assert 'v184ReturnPlayback = activePlayback' in shell.read_text()
assert shell.read_text().count("returnFromCreator()") == 2
assert 'V184SmartTubeResume.read' in player.read_text()
assert 'V184SmartTubeResume.clear' in player.read_text()
assert 'bind(player, isTv, cinemaVod = true)' in player.read_text()
assert 'V184SmartTubeSeekPolicy.deltaMs' in browse.read_text()
assert 'commentsShown -> false' in browse.read_text()
print("V184_CREATOR_BACK_RESUME_TV_CADENCE_10S_TAP_30S_REPEAT_INSTALLED")
