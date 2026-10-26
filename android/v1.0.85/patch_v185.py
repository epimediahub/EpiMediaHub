#!/usr/bin/env python3
"""v1.0.85 private QA: 50-fps sports stream priority + original short synced intro.

No upstream connection probes, no duplicate IPTV sessions, no changes to EpiScene,
SmartTube, VPN or VOD frame-rate policy. Apply only AFTER v1.0.84.
Fail closed on every source anchor change. Never modify the public updater here.
"""
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
ui = root / "app/src/main/java/de/epimediahub/app/ui"
tests = root / "app/src/test/java/de/epimediahub/app/ui"
app = root / "app/src/main"

def once(file: Path, before: str, after: str) -> None:
    original = file.read_text(encoding="utf-8")
    if original.count(before) != 1:
        raise SystemExit("STOP_V185_SOURCE_DRIFT " + file.name +
                         " count=" + str(original.count(before)) + " anchor=" + repr(before[:90]))
    file.write_text(original.replace(before, after, 1), encoding="utf-8")

def once_main(file: Path, before: str, after: str) -> None:
    """Match only the standard ExoPlayer root, not the separate VLC composable."""
    source = file.read_text(encoding="utf-8")
    anchor = "fun PlayerScreen("
    if source.count(anchor) != 1:
        raise SystemExit("STOP_V185_PLAYER_ROOT_NOT_UNIQUE")
    split = source.index(anchor)
    prefix, main = source[:split], source[split:]
    if main.count(before) != 1:
        raise SystemExit("STOP_V185_PLAYER_SOURCE_DRIFT " + str(main.count(before)) + " " + repr(before[:90]))
    file.write_text(prefix + main.replace(before, after, 1), encoding="utf-8")

version = root / "app/build.gradle.kts"
once(version, "versionCode = 1084", "versionCode = 1085")
once(version, 'versionName = "1.0.84"', 'versionName = "1.0.85"')
shutil.copy2(here / "V185SportPriority.kt", ui / "V185SportPriority.kt")
tests.mkdir(parents=True, exist_ok=True)
shutil.copy2(here / "V185SportPriorityTest.kt", tests / "V185SportPriorityTest.kt")

# Applies the chosen variant BEFORE media connections are opened, not by
# starting both 25fps and 50fps streams to compare them.
vm = root / "app/src/main/java/de/epimediahub/app/MainViewModel.kt"
once(vm,
'''    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {
''',
'''    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {
        // Conservatively prefer ONE 50-fps variant only when the same profile
        // has a uniquely matching channel. Unknown/ambiguous stays unchanged.
        if (item.kind == MediaKind.LIVE) {
            val preferred = de.epimediahub.app.ui.V185SportPriority.preferred(item, episodeList, _ui.value.active?.id.orEmpty())
            if (preferred.id != item.id || preferred.sourceProfileId != item.sourceProfileId) {
                play(preferred, episodeList)
                return
            }
        }
''')

# Player remote/channel zapping uses switchLiveChannel(), not play().
# Resolve the single safe 50-fps variant before preparing a stream, and
# recurse exactly once only when a different unique variant was selected.
once(vm,
'''    fun switchLiveChannel(item: MediaEntry, channelList: List<MediaEntry>) {
        if (item.kind != MediaKind.LIVE || channelList.isEmpty()) return
''',
'''    fun switchLiveChannel(item: MediaEntry, channelList: List<MediaEntry>) {
        if (item.kind != MediaKind.LIVE || channelList.isEmpty()) return
        val v185Preferred = de.epimediahub.app.ui.V185SportPriority.preferred(
            item, channelList, _ui.value.active?.id.orEmpty())
        if (v185Preferred.id != item.id ||
            v185Preferred.sourceProfileId != item.sourceProfileId) {
            switchLiveChannel(v185Preferred, channelList)
            return
        }
''')

player = ui / "PlayerScreen.kt"
once(player,
'''    val httpFactory = playbackEngine.first
    val player = playbackEngine.second
    DisposableEffect(capture)''',
'''    val httpFactory = playbackEngine.first
    val player = playbackEngine.second
    var v185MeasuredFps by remember(item.resumeKey) { mutableIntStateOf(0) }
    // Read the already-running standard player, with no extra provider request.
    // Require three stable observations before remembering a live channel FPS.
    LaunchedEffect(player, item.resumeKey) {
        if (item.kind == MediaKind.LIVE) {
            V185SportPriority.initialize(context)
            var previous = 0
            var consecutive = 0
            while (true) {
                val snapshot = V122ActiveVideo.snapshot()
                val candidate = if (player.isPlaying && (snapshot?.rendered ?: 0) >= 90)
                    V185SportPriority.classify(snapshot?.measuredFps ?: 0f) else 0
                if (candidate == previous && candidate != 0) consecutive++ else {
                    previous = candidate
                    consecutive = if (candidate > 0) 1 else 0
                }
                if (consecutive >= 3 && v185MeasuredFps != candidate) {
                    v185MeasuredFps = candidate
                    V185SportPriority.recordMeasured(context, item, candidate, u.active?.id.orEmpty())
                }
                delay(2_000L)
            }
        }
    }
    DisposableEffect(capture)''')

once_main(player,
'''    val nowProgramme = V163EpgBanner(vm, item, u.epg[item.id].orEmpty())
    LaunchedEffect(nowProgramme) {''',
'''    val nowProgramme = V163EpgBanner(vm, item, u.epg[item.id].orEmpty())
    // Re-evaluate when the playing FPS becomes known; a cached remember would
    // keep the alternative button invisible even after normal playback taught us.
    val v185Alternative = if (item.kind == MediaKind.LIVE)
        V185SportPriority.recommendedAlternative(item, episodeList, u.active?.id.orEmpty())
    else null
    LaunchedEffect(nowProgramme) {''')
# A separate 50 FPS button is shown ONLY when a known or named unique
# alternative exists in the already loaded channel list.
once(player,
'''                    TextButton(onClick = { showPlaybackInfo = true }, modifier = Modifier.v114FocusRing()) {
                        Text("Info · Menü", color = Color.White)
                    }
                    TextButton(onClick = {
                        manualPlayerChoice = true
                        useVlc = true
                    },''',
'''                    TextButton(onClick = { showPlaybackInfo = true }, modifier = Modifier.v114FocusRing()) {
                        Text("Info · Menü", color = Color.White)
                    }
                    if (v185Alternative != null && v185MeasuredFps != 50) {
                        TextButton(
                            onClick = { vm.switchLiveChannel(v185Alternative, episodeList) },
                            modifier = Modifier.v114FocusRing()
                        ) { Text("50 FPS · Alternative", color = Color(0xFF72E8D3)) }
                    }
                    TextButton(onClick = {
                        manualPlayerChoice = true
                        useVlc = true
                    },''')

once_main(player,
'''                            if (nowProgramme.isNotBlank()) nowProgramme else "Jetzt live",
                            color = Color.White.copy(alpha = .75f),
                            fontSize = 14.sp,
                            maxLines = 1
                        )
''',
'''                            if (nowProgramme.isNotBlank()) nowProgramme else "Jetzt live",
                            color = Color.White.copy(alpha = .75f),
                            fontSize = 14.sp,
                            maxLines = 1
                        )
                        Text(
                            when (v185MeasuredFps) {
                                50 -> "50 fps · Flüssiger Sportmodus"
                                25 -> "25 fps · Für Sport möglichst 50-fps-Sender wählen"
                                else -> "Bildrate wird gemessen"
                            },
                            color = if (v185MeasuredFps == 50) Color(0xFF78E5D0)
                                else Color.White.copy(alpha = .70f),
                            fontSize = 12.sp,
                            maxLines = 1
                        )
''')

# Return to the ACTUAL original intro picture and its synchronised 17.5s
# score. The render includes conservative explanatory overlays for EpiScene.
intro = here / "epimedia_intro_v185.mp4"
if not intro.is_file() or intro.is_symlink() or intro.stat().st_size < 500_000:
    raise SystemExit("STOP_V185_SHORT_INTRO_NOT_RENDERED")
info = json.loads(subprocess.check_output([
    "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(intro)
], text=True))
video = next(s for s in info["streams"] if s["codec_type"] == "video")
audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
if not (abs(float(info["format"]["duration"]) - 17.5) < .07 and
        video["codec_name"] == "h264" and audio["codec_name"] == "aac" and
        video["width"] == 1280 and video["height"] == 720 and
        audio["sample_rate"] == "48000"):
    raise SystemExit("STOP_V185_SHORT_INTRO_FORMAT_OR_DURATION")
dest = app / "res/raw/epimedia_intro_v5.mp4"
if not dest.is_file():
    raise SystemExit("STOP_V185_PACKAGED_INTRO_RESOURCE_MISSING")
shutil.copy2(intro, dest)
introplayer = ui / "V161IntroVideo.kt"
once(introplayer, "delay(38_000L)", "delay(20_000L)")
if 'Player.STATE_ENDED' not in introplayer.read_text(encoding="utf-8"):
    raise SystemExit("STOP_V185_INTRO_END_EVENT_MISSING")

assert 'V170LiveCadencePolicy.matchingMode' in (ui / "V121VodSurface.kt").read_text()
assert 'cinemaVod = true' in (ui / "V116VodPlayer.kt").read_text()
assert 'V168VlcVodPlayer(' in player.read_text()
print("V185_SPORT_PRIORITY_AND_SHORT_SYNCED_INTRO_INSTALLED")
print("V185_INTRO_DURATION 17.5s ORIGINAL_PICTURE_COPY_AUDIO_HASH",
      hashlib.sha256(dest.read_bytes()).hexdigest())
print("NO_PUBLIC_UPDATER_CHANGE_NO_EXTRA_IPTV_CONNECTIONS")


# Read-only QA trace: prove whether channel zapping uses play() or a separate
# navigation route. Never log playlist metadata, stream URLs or credentials.
source_lines = vm.read_text(encoding="utf-8").splitlines()
for source_name in ("fun switchLiveChannel(", "fun play(", "fun openLiveChannels("):
    hits = [index for index, line in enumerate(source_lines) if source_name in line]
    print("V185_ROUTE_AUDIT", source_name, "hits", len(hits))
    for start in hits[:1]:
        for index in range(start, min(start + 34, len(source_lines))):
            print("V185_ROUTE", str(index + 1), source_lines[index])
