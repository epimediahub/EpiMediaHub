#!/usr/bin/env python3
"""v1.0.81 SmartTube controls: visible overlay above PlayerView + remote-first focus.

Apply AFTER v1.0.80. This release intentionally refuses the old v180 intro;
the final 34s v2 movie with the ORIGINAL EpiMediaHub brand-logo finale is required.
"""
from pathlib import Path
import os

root = Path(os.environ["PROJECT_ROOT"])
ui = root / "app/src/main/java/de/epimediahub/app/ui"

def once(path: Path, old: str, new: str):
    source = path.read_text(encoding="utf-8")
    occurrences = source.count(old)
    if occurrences != 1:
        raise SystemExit(f"STOP_V181_BASELINE_DRIFT {path.name}: {old[:75]!r}, count {occurrences}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")

gradle = root / "app/build.gradle.kts"
once(gradle, "versionCode = 1080", "versionCode = 1081")
once(gradle, 'versionName = "1.0.80"', 'versionName = "1.0.81"')

browse = ui / "V124SmartTubeBrowseLayer.kt"
once(browse,
     "    onQuality: () -> Unit = {},",
     "    onQuality: () -> Unit = {},\n"
     "    controlsShown: Boolean = false,\n"
     "    onHideControls: () -> Unit = {},")
once(browse,
     "    BackHandler { if (browsing) close() else onExit() }",
     "    BackHandler {\n"
     "        when {\n"
     "            browsing -> close()\n"
     "            controlsShown -> onHideControls()\n"
     "            else -> onExit()\n"
     "        }\n"
     "    }")
once(browse,
     "    LaunchedEffect(videoId, browsing, videos.isEmpty(), focusedId?.let { id -> videos.any { it.videoId == id } }) {",
     "    LaunchedEffect(videoId, browsing, controlsShown, videos.isEmpty(), focusedId?.let { id -> videos.any { it.videoId == id } }) {")
once(browse,
     "        if (!browsing) {\n            focusedId = null\n            remote.requestFocus()\n        }",
     "        if (!browsing) {\n            focusedId = null\n            if (!controlsShown) remote.requestFocus()\n        }")
head = "    Box(Modifier.fillMaxSize().background(Color.Black)\n        .focusRequester(remote)\n        .onPreviewKeyEvent { event ->"
start = browse.read_text(encoding="utf-8")
pos = start.find(head)
if pos == -1:
    raise SystemExit("STOP_V181_BROWSE_REMOTE_ANCHOR_MISSING")
key_start = start.index("        .onPreviewKeyEvent { event ->", pos)
key_end = start.index("        }.focusable().testTag", key_start)
key_new = """        .onPreviewKeyEvent { event ->
            if (event.type != KeyEventType.KeyDown) return@onPreviewKeyEvent false
            val repeated = event.nativeKeyEvent.repeatCount > 0
            when {
                browsing && event.key == Key.DirectionUp -> {
                    if (!repeated) close()
                    true
                }
                browsing -> false
                event.nativeKeyEvent.keyCode == android.view.KeyEvent.KEYCODE_MENU -> {
                    if (!repeated) { onShowControls(); onQuality() }
                    true
                }
                event.key == Key.MediaPlayPause -> {
                    if (!repeated) onTogglePlayback()
                    true
                }
                // First OK or any D-pad direction must OPEN the actual player mask.
                // Do not seek, pause, or move to a shelf behind a hidden mask.
                !controlsShown && event.key in setOf(
                    Key.DirectionCenter, Key.Enter, Key.NumPadEnter,
                    Key.DirectionUp, Key.DirectionDown,
                    Key.DirectionLeft, Key.DirectionRight
                ) -> {
                    if (!repeated) onShowControls()
                    true
                }
                // A second DOWN can still open the existing recommendations shelf.
                // While controls are visible the focused Compose buttons own
                // Left/Right/OK. Never steal button OK for playback toggling.
                controlsShown -> false
                else -> false
            }
"""
updated = start[:key_start] + key_new + start[key_end:]
browse.write_text(updated, encoding="utf-8")

player = ui / "V112SmartTubePlayer.kt"
once(player,
     "import androidx.compose.ui.platform.LocalContext",
     "import androidx.compose.ui.platform.LocalContext\n"
     "import androidx.compose.ui.platform.testTag")
once(player,
     "    var controlsVisible by remember(video.videoId) { mutableStateOf(true) }",
     "    var controlsVisible by remember(video.videoId) { mutableStateOf(true) }\n"
     "    val v181QualityFocus = remember(video.videoId) { FocusRequester() }")

# The v176/v179 quality + creator controls were laid out BEFORE the AndroidView.
# SurfaceView / PlayerView was then rendered ON TOP, hiding all options.
source = player.read_text(encoding="utf-8")
block_start = "        if (!browsing && controlsVisible && player != null) {"
player_box = "        if (player != null) {"
if source.count(block_start) != 1:
    raise SystemExit("STOP_V181_TOP_BUTTONS_ANCHOR_MISSING")
a = source.index(block_start)
b = source.index(player_box, a)
options_block = source[a:b]
if 'onCreatorChannel' not in options_block or 'showV176Quality' not in options_block:
    raise SystemExit("STOP_V181_QUALITY_CREATOR_NOT_IN_TOP_ROW")
source = source[:a] + source[b:]
post_video_anchor = "        if (controlsVisible && !browsing && errorText.isBlank()) {"
if source.count(post_video_anchor) != 1:
    raise SystemExit("STOP_V181_VIDEO_OVERLAY_ANCHOR_MISSING")
options_block = options_block.replace(
    "Modifier.align(Alignment.TopEnd).padding(top = 14.dp, end = 20.dp)",
    "Modifier.align(Alignment.TopEnd).padding(top = 14.dp, end = 20.dp)"
    ".background(Color.Black.copy(alpha = .82f))"
)
options_block = options_block.replace(
    "TextButton(onClick = { showV176Quality = true })",
    "TextButton(onClick = { showV176Quality = true },\n"
    "                    modifier = Modifier.focusRequester(v181QualityFocus)"
    ".testTag(\"smarttube-quality-button\"))"
)
options_block = options_block.replace(
    "TextButton(onClick = onCreatorChannel)",
    "TextButton(onClick = onCreatorChannel,\n"
    "                        modifier = Modifier.testTag(\"smarttube-channel-button\"))"
)
options_block = options_block.replace(
    "            Row(\n",
    "            Row(\n", 1)
source = source.replace(post_video_anchor, options_block + "\n" + post_video_anchor, 1)
player.write_text(source, encoding="utf-8")

# Keep player focus on a real option when the remote opens the mask.
once(player,
'''    LaunchedEffect(controlsVisible, isPlaying, video.videoId) {
        if (controlsVisible && isPlaying) {
            delay(4_500L)
            controlsVisible = false
        }
    }''',
'''    LaunchedEffect(controlsVisible, isPlaying, showV176Quality,
        showV179PlayerMenu, video.videoId) {
        if (controlsVisible && isPlaying &&
            !showV176Quality && !showV179PlayerMenu) {
            delay(20_000L)
            controlsVisible = false
        }
    }
    LaunchedEffect(controlsVisible, video.videoId) {
        delay(100L) // Compose must attach the remote-focus target first.
        runCatching {
            if (controlsVisible) v181QualityFocus.requestFocus()
            # Hidden-mask focus returns to V124 remote input layer.
        }
    }''')
once(player,
'''        onSeek = ::seekBy, onShowControls = { controlsVisible = true },
        onQuality = { showV179PlayerMenu = true },''',
'''        onSeek = ::seekBy, onShowControls = { controlsVisible = true },
        onQuality = { showV179PlayerMenu = true; controlsVisible = true },
        controlsShown = controlsVisible,
        onHideControls = { controlsVisible = false },''')

# Outer browse handler owns the first opening key. Once the mask is visible,
# stop the nested player container from swallowing OK/D-pad focused actions.
# No nested onPreviewKeyEvent handler exists in V112SmartTubePlayer.
# V124SmartTubeBrowseLayer owns D-pad/OK and yields when controls show.

source = player.read_text(encoding="utf-8")
assert source.index("AndroidView(") < source.index('testTag("smarttube-quality-button")')
assert 'testTag("smarttube-channel-button")' in source
assert "controlsShown = controlsVisible" in source
assert "v181QualityFocus.requestFocus()" in source
assert "controlsShown -> false" in browse.read_text(encoding="utf-8")
assert "onCreatorChannel()" in source
print("V181_SMARTTUBE_VISIBLE_FOCUSABLE_REMOTE_PLAYER_MASK_READY")

# The user-approved new 34-second concept is a SEPARATE movie, not a cropped
# section of the old v178/v180 intro. This must never silently substitute it.
import hashlib
import json
import re
import shutil
import subprocess
approved = Path(__file__).resolve().parent / "EpiMediaHub_EpiScene_34s_v2_ORIGINAL_LOGO.mp4"
checksum = approved.with_suffix(".sha256")
if os.environ.get("EPIMEDIA_V181_PRIVATE_SOURCE_ONLY") == "1":
    print("PRIVATE_KOTLIN_COMPILE_ONLY_NEW_APPROVED_INTRO_NOT_INCLUDED_NOT_RELEASABLE")
    raise SystemExit(0)
if not approved.is_file() or not checksum.is_file():
    raise SystemExit(
        "STOP_V181_APPROVED_NEW_34S_INTRO_MISSING: "
        "EpiMediaHub_EpiScene_34s_v2_ORIGINAL_LOGO.mp4 and its SHA-256 required; "
        "NEVER substitute old v178/v180 footage"
    )
sha256 = hashlib.sha256(approved.read_bytes()).hexdigest()
if not re.fullmatch(r"[0-9a-f]{64}", checksum.read_text(encoding="ascii").strip()):
    raise SystemExit("STOP_V181_APPROVED_SOURCE_HASH_FORMAT")
if sha256 != checksum.read_text(encoding="ascii").strip():
    raise SystemExit("STOP_V181_APPROVED_NEW_34S_SOURCE_HASH_MISMATCH")
info = json.loads(subprocess.check_output([
    "ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json",
    str(approved)
], text=True))
if abs(float(info["format"]["duration"]) - 34.0) > 0.09:
    raise SystemExit("STOP_V181_APPROVED_NEW_34S_DURATION_MISMATCH")
video_stream = next(s for s in info["streams"] if s["codec_type"] == "video")
audio_stream = next(s for s in info["streams"] if s["codec_type"] == "audio")
if (video_stream["width"], video_stream["height"]) != (1280,720):
    raise SystemExit("STOP_V181_APPROVED_NEW_34S_DIMENSIONS_MISMATCH")
if video_stream["codec_name"] != "h264" or audio_stream["codec_name"] != "aac":
    raise SystemExit("STOP_V181_APPROVED_NEW_34S_CODECS_MISMATCH")
shutil.copy2(approved, root / "app/src/main/res/raw/epimedia_intro_v5.mp4")
print("V181_APPROVED_NEW_EPI_SCENE_34S_VIDEO_INCLUDED_UNCROPPED", sha256)

print("V181_INTRO_NOT_REPLACED_WITH_OLD_V180_CROPPED_VIDEO")
