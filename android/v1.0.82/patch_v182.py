#!/usr/bin/env python3
"""EpiMediaHub 1.0.82 – SmartTube quality and creator channel in the BOTTOM TV player bar.

Apply immediately after v1.0.81. No edits to video/intro, IPTV, VPN, device
license or backend. Fail closed on unexpected baseline instead of silently
shipping a different layout.
"""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
ui = root / "app/src/main/java/de/epimediahub/app/ui"
tests = root / "app/src/test/java/de/epimediahub/app/ui"


def once(path: Path, old: str, new: str):
    source = path.read_text(encoding="utf-8")
    count = source.count(old)
    if count != 1:
        raise SystemExit(
            f"STOP_V182_BASELINE_DRIFT {path.name}: {old[:90]!r}, count={count}"
        )
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


gradle = root / "app/build.gradle.kts"
once(gradle, "versionCode = 1081", "versionCode = 1082")
once(gradle, 'versionName = "1.0.81"', 'versionName = "1.0.82"')

# Add a real programmatic entry point to the existing in-player suggestions.
# It opens the shelf WITHOUT replacing/unmounting the active PlayerView.
browse = ui / "V124SmartTubeBrowseLayer.kt"
once(
    browse,
    "    controlsShown: Boolean = false,",
    "    browseRequest: Int = 0,\n    controlsShown: Boolean = false,"
)
once(
    browse,
    "    val row = rememberLazyListState()\n",
    "    val row = rememberLazyListState()\n"
    "    LaunchedEffect(videoId, browseRequest) {\n"
    "        if (browseRequest > 0) browsing = true\n"
    "    }\n"
)

player = ui / "V112SmartTubePlayer.kt"
once(
    player,
    "import androidx.compose.foundation.background",
    "import androidx.compose.foundation.background\n"
    "import androidx.compose.foundation.horizontalScroll\n"
    "import androidx.compose.foundation.rememberScrollState"
)
once(
    player,
    "import androidx.compose.foundation.shape.CircleShape",
    "import androidx.compose.foundation.shape.CircleShape\n"
    "import androidx.compose.foundation.shape.RoundedCornerShape"
)
once(
    player,
    "    val v181QualityFocus = remember(video.videoId) { FocusRequester() }",
    "    val v181QualityFocus = remember(video.videoId) { FocusRequester() }\n"
    "    var v182BrowseRequest by remember(video.videoId) { mutableIntStateOf(0) }"
)
once(
    player,
    "        controlsShown = controlsVisible,",
    "        browseRequest = v182BrowseRequest,\n"
    "        controlsShown = controlsVisible,"
)

# v181 placed its real interactive buttons at the top-right after PlayerView.
# Remove only that block. Do not leave a second quality control in the corner.
source = player.read_text(encoding="utf-8")
top_anchor = "        if (!browsing && controlsVisible && player != null) {"
overlay_anchor = "        if (controlsVisible && !browsing && errorText.isBlank()) {"
error_anchor = "        if (errorText.isNotBlank() && !browsing) {"
if source.count(top_anchor) != 1 or source.count(overlay_anchor) != 1:
    raise SystemExit("STOP_V182_EXPECTED_V181_TOP_CONTROL_LAYOUT_MISSING")
a = source.index(top_anchor)
b = source.index(overlay_anchor, a)
old_top = source[a:b]
for required in (
    'testTag("smarttube-quality-button")',
    'testTag("smarttube-channel-button")',
    "showV176Quality = true",
    "onCreatorChannel"
):
    if required not in old_top:
        raise SystemExit("STOP_V182_TOP_BAR_UNEXPECTED: " + required)
source = source[:a] + source[b:]

# Reserve the bottommost band for the TV remote action row; keep the real
# video title, timeline and elapsed/total time above the buttons.
old_padding = "bottom = if (isTv) 30.dp else 18.dp"
if source.count(old_padding) != 1:
    raise SystemExit("STOP_V182_BOTTOM_TIMELINE_PADDING_DRIFT")
source = source.replace(
    old_padding, "bottom = if (isTv) 96.dp else 78.dp", 1
)

bottom_bar = """
        // The main action row deliberately follows the timeline and is anchored
        // to the BOTTOM edge. It is composed AFTER AndroidView/PlayerView.
        if (controlsVisible && !browsing && errorText.isBlank()) {
            Row(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .background(Color.Black.copy(alpha = .87f))
                    .horizontalScroll(rememberScrollState())
                    .padding(
                        horizontal = if (isTv) 32.dp else 10.dp,
                        vertical = if (isTv) 12.dp else 7.dp
                    )
                    .testTag("smarttube-bottom-actions"),
                horizontalArrangement = Arrangement.spacedBy(if (isTv) 10.dp else 5.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (video.author.isNotBlank()) {
                    TextButton(
                        onClick = onCreatorChannel,
                        modifier = Modifier
                            .background(Color(0xFF1B2B40), RoundedCornerShape(18.dp))
                            .v114FocusRing()
                            .testTag("smarttube-channel-identity")
                    ) {
                        Text(
                            "▶  " + video.author,
                            color = Color.White,
                            fontSize = if (isTv) 14.sp else 12.sp,
                            fontWeight = FontWeight.SemiBold,
                            maxLines = 1
                        )
                    }
                }

                if (!video.live) {
                    TextButton(
                        onClick = { seekBy(-10_000L) },
                        modifier = Modifier
                            .background(Color(0xFF1B2B40), RoundedCornerShape(18.dp))
                            .v114FocusRing()
                            .testTag("smarttube-bottom-seek")
                    ) { Text("◀ 10 Sek.", color = Color.White, maxLines = 1) }
                }

                TextButton(
                    onClick = { showV176Quality = true },
                    modifier = Modifier
                        .focusRequester(v181QualityFocus)
                        .background(Color(0xFF1B2B40), RoundedCornerShape(18.dp))
                        .v114FocusRing()
                        .testTag("smarttube-quality-button")
                ) {
                    Text(
                        "⚙ Qualität: " + V176SmartTubeQuality.label(v176ChosenHeight),
                        color = Color.White,
                        fontSize = if (isTv) 14.sp else 12.sp,
                        maxLines = 1
                    )
                }

                if (video.author.isNotBlank()) {
                    TextButton(
                        onClick = onCreatorChannel,
                        modifier = Modifier
                            .background(Color(0xFF1B2B40), RoundedCornerShape(18.dp))
                            .v114FocusRing()
                            .testTag("smarttube-channel-button")
                    ) {
                        Text("▶ YouTube-Kanal", color = Color.White,
                            fontSize = if (isTv) 14.sp else 12.sp, maxLines = 1)
                    }
                }

                TextButton(
                    onClick = { v182BrowseRequest++ },
                    modifier = Modifier
                        .background(Color(0xFF1B2B40), RoundedCornerShape(18.dp))
                        .v114FocusRing()
                        .testTag("smarttube-more-videos-button")
                ) {
                    Text("☷ Weitere Videos", color = Color.White,
                        fontSize = if (isTv) 14.sp else 12.sp, maxLines = 1)
                }
            }
        }

"""
# Several playback failure helpers use this condition. The bottom bar belongs
# specifically AFTER the controls/timeline overlay, before its error Surface.
overlay_pos = source.index(overlay_anchor)
error_pos = source.find(error_anchor, overlay_pos + len(overlay_anchor))
if error_pos < 0:
    raise SystemExit("STOP_V182_PLAYER_ERROR_SURFACE_NOT_FOUND")
source = source[:error_pos] + bottom_bar + source[error_pos:]
if source.index("AndroidView(") > source.index('testTag("smarttube-bottom-actions")'):
    raise SystemExit("STOP_V182_BOTTOM_ACTIONS_BEHIND_SURFACE")
if source.count('testTag("smarttube-quality-button")') != 1:
    raise SystemExit("STOP_V182_DUPLICATE_QUALITY")
if source.count('testTag("smarttube-channel-button")') != 1:
    raise SystemExit("STOP_V182_DUPLICATE_CHANNEL")
if "Alignment.TopEnd).padding(top = 14.dp, end = 20.dp)" in source:
    raise SystemExit("STOP_V182_OLD_TOP_RIGHT_CONTROLS_REMAIN")
player.write_text(source, encoding="utf-8")

# Exercise the actual TV browsing contract through the existing compose suite.
test_path = tests / "V124SmartTubeBrowseTest.kt"
once(
    test_path,
    "    private var controlsShown by mutableStateOf(false)",
    "    private var controlsShown by mutableStateOf(false)\n"
    "    private var browseRequest by mutableIntStateOf(0)"
)
once(
    test_path,
    "        controlsShown=false\n",
    "        controlsShown=false\n        browseRequest=0\n"
)
once(
    test_path,
    "onShowControls={controlsShown=true},controlsShown=controlsShown,",
    "onShowControls={controlsShown=true},browseRequest=browseRequest,controlsShown=controlsShown,"
)
once(
    test_path,
    "    @Test fun firstOkAndArrowsOpenPlayerMaskWithoutUnexpectedSeekOrPause(){",
    """    @Test fun bottomMoreVideosOpensSuggestionsWithoutStoppingPlayback(){
        launch()
        compose.runOnIdle { browseRequest++ }
        settle()
        compose.onNodeWithTag("smarttube-video-shelf").assertIsDisplayed()
        compose.onNodeWithTag("smarttube-suggestion-one").assertIsFocused()
        assertEquals(1,mounts)
        assertEquals(0,unmounts)
        assertEquals(0L,seeked)
        assertEquals(0,toggled)
    }

    @Test fun firstOkAndArrowsOpenPlayerMaskWithoutUnexpectedSeekOrPause(){"""
)

assert "browseRequest = v182BrowseRequest" in player.read_text()
assert "if (browseRequest > 0) browsing = true" in browse.read_text()
assert "onCreatorChannel" in player.read_text()
assert "showV176Quality = true" in player.read_text()

print("V182_SMARTTUBE_REAL_BOTTOM_BUTTONS_INSTALLED: quality, creator, seek, more videos")
print("V182_EXISTING_34S_APPROVED_INTRO_AND_ALL_OTHER_MODULES_UNCHANGED")
