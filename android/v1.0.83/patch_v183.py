#!/usr/bin/env python3
"""EpiMediaHub 1.0.83 – real YouTube creator avatar/subscribers/channel/comments.

Apply after 1.0.82; fail on unexpected patch baseline. Preserve 34s intro,
IPTV, VPN, Fire TV activation, EpiScene and signing.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
ui = root / "app/src/main/java/de/epimediahub/app/ui"

def once(file: Path, old: str, new: str):
    s = file.read_text(encoding="utf-8")
    if s.count(old) != 1:
        raise SystemExit(f"STOP_V183_BASELINE_DRIFT {file.name} count={s.count(old)}: {old[:95]!r}")
    file.write_text(s.replace(old, new, 1), encoding="utf-8")

gradle = root / "app/build.gradle.kts"
once(gradle, "versionCode = 1082", "versionCode = 1083")
once(gradle, 'versionName = "1.0.82"', 'versionName = "1.0.83"')

for name in ("V183SmartTubeSocial.kt", "V183SmartTubeCommentsDrawer.kt"):
    shutil.copy2(here / name, ui / name)

player = ui / "V112SmartTubePlayer.kt"
once(player,
     "import androidx.compose.ui.platform.LocalContext",
     "import androidx.compose.ui.platform.LocalContext\n"
     "import androidx.compose.ui.layout.ContentScale\n"
     "import androidx.compose.ui.draw.clip\n"
     "import coil.compose.AsyncImage")
once(player,
     "    var v182BrowseRequest by remember(video.videoId) { mutableIntStateOf(0) }",
     """    var v182BrowseRequest by remember(video.videoId) { mutableIntStateOf(0) }
    var showV183Comments by remember(video.videoId) { mutableStateOf(false) }
    var v183Creator by remember(video.videoId) { mutableStateOf<V183CreatorDetails?>(null) }
    var v183CreatorLoading by remember(video.videoId) { mutableStateOf(true) }
    LaunchedEffect(video.videoId) {
        v183CreatorLoading = true
        V183SmartTubeSocial.creator(context, video.videoId)
            .onSuccess { v183Creator = it }
            .onFailure { v183Creator = null }
        v183CreatorLoading = false
    }""")
once(player,
     "        browseRequest = v182BrowseRequest,",
     """        browseRequest = v182BrowseRequest,
        commentsShown = showV183Comments,
        onCloseComments = { showV183Comments = false },""")
once(player,
     "        showV179PlayerMenu, video.videoId) {",
     "        showV179PlayerMenu, showV183Comments, video.videoId) {")
once(player,
     "            !showV176Quality && !showV179PlayerMenu) {",
     "            !showV176Quality && !showV179PlayerMenu && !showV183Comments) {")

# Identity block now has the real channel avatar and current subscriber count.
# Avoid spurious zeros when YouTube does not expose subscriber counts.
source = player.read_text(encoding="utf-8")
start_tag = '                            .testTag("smarttube-channel-identity")'
finish = '                if (!video.live) {'
a = source.index(start_tag)
b = source.index(finish, a)
old_identity = source[a:b]
if '"▶  " + video.author' not in old_identity or 'onCreatorChannel' not in old_identity:
    raise SystemExit("STOP_V183_OLD_CHANNEL_IDENTITY_NOT_FOUND")
new_identity = '''                            .testTag("smarttube-channel-identity")
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            val avatar = v183Creator?.avatar.orEmpty()
                            if (avatar.isNotBlank()) {
                                AsyncImage(
                                    model = avatar,
                                    contentDescription = "Kanalbild",
                                    contentScale = ContentScale.Crop,
                                    modifier = Modifier.size(if (isTv) 38.dp else 30.dp)
                                        .clip(CircleShape)
                                )
                                Spacer(Modifier.width(9.dp))
                            }
                            Column(Modifier.widthIn(max = if (isTv) 150.dp else 130.dp)) {
                                Text(
                                    v183Creator?.channelName?.takeIf { it.isNotBlank() }
                                        ?: video.author,
                                    color = Color.White,
                                    fontWeight = FontWeight.Bold,
                                    fontSize = if (isTv) 15.sp else 12.sp,
                                    maxLines = 1, overflow = TextOverflow.Ellipsis
                                )
                                Text(
                                    v183Creator?.subscribers?.takeIf { it.isNotBlank() }
                                        ?.let { "$it Abonnenten" }
                                        ?: if (v183CreatorLoading) "Abonnenten werden geladen …"
                                           else "Abonnenten nicht verfügbar",
                                    color = Color(0xFFBBD0E5),
                                    fontSize = if (isTv) 12.sp else 10.sp,
                                    maxLines = 1
                                )
                            }
                        }
                    }
                }

'''
source = source[:a] + new_identity + source[b:]
# ±10s is already in the large central playback controls; avoid pushing
# the essential creator/channel/comments buttons off the right edge of a TV.
seek_start = source.find('                if (!video.live) {\n                    TextButton(', source.index('testTag("smarttube-channel-identity")'))
quality_start = source.find('                TextButton(\n                    onClick = { showV176Quality = true }', seek_start)
if seek_start < 0 or quality_start < 0 or 'smarttube-bottom-seek' not in source[seek_start:quality_start]:
    raise SystemExit("STOP_V183_BOTTOM_SEEK_LAYOUT_CHANGED")
source = source[:seek_start] + source[quality_start:]
source = source.replace('horizontal = if (isTv) 32.dp else 10.dp',
                        'horizontal = if (isTv) 12.dp else 10.dp', 1)
if source.count('testTag("smarttube-channel-identity")') != 1:
    raise SystemExit("STOP_V183_DUPLICATE_CHANNEL_IDENTITY")
# The creator's name is not always in home/search results; metadata may be.
source = source.replace(
    'if (video.author.isNotBlank()) {\n                    TextButton(\n                        onClick = onCreatorChannel,',
    'if (video.author.isNotBlank() || v183Creator?.channelId?.isNotBlank() == true) {\n                    TextButton(\n                        onClick = onCreatorChannel,',
    1)
source = source.replace(
    'if (video.author.isNotBlank()) {\n                    TextButton(\n                        onClick = onCreatorChannel,',
    'if (video.author.isNotBlank() || v183Creator?.channelId?.isNotBlank() == true) {\n                    TextButton(\n                        onClick = onCreatorChannel,',
    1)
button_anchor = '''                TextButton(
                    onClick = { v182BrowseRequest++ },'''
if source.count(button_anchor) != 1:
    raise SystemExit("STOP_V183_MORE_VIDEOS_BUTTON_NOT_FOUND")
comments_button = '''                TextButton(
                    onClick = { showV183Comments = true; controlsVisible = true },
                    modifier = Modifier
                        .background(Color(0xFF1B2B40), RoundedCornerShape(18.dp))
                        .v114FocusRing()
                        .testTag("smarttube-comments-button")
                ) {
                    Text("▤ Kommentare", color = Color.White,
                        fontSize = if (isTv) 14.sp else 12.sp, maxLines = 1)
                }

'''
source = source.replace(button_anchor, comments_button + button_anchor, 1)

# Keep the currently playing Media3 surface mounted while opening comments.
drawer = '''        if (showV183Comments) {
            Box(
                Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                    .testTag("smarttube-comments-layer")
            ) {
                V183SmartTubeCommentsDrawer(
                    videoId = video.videoId,
                    commentsKey = v183Creator?.commentsKey.orEmpty(),
                    metadataLoading = v183CreatorLoading,
                    context = context,
                    isTv = isTv,
                    onClose = { showV183Comments = false }
                )
            }
        }

'''
error_anchor = '''        if (errorText.isNotBlank() && !browsing) {'''
if source.count(error_anchor) != 1:
    raise SystemExit("STOP_V183_PLAYER_ERROR_ANCHOR_NOT_FOUND")
source = source.replace(error_anchor, drawer + error_anchor, 1)
if not source.index('testTag("smarttube-comments-layer")') > source.index('testTag("smarttube-comments-button")'):
    raise SystemExit("STOP_V183_COMMENT_DRAWER_Z_ORDER")
player.write_text(source, encoding="utf-8")

# Important: the outer TV remote dispatcher must not open the suggestion shelf
# when comments are being navigated, and Back closes comments before the player.
browse = ui / "V124SmartTubeBrowseLayer.kt"
once(browse,
     "    browseRequest: Int = 0,\n    controlsShown: Boolean = false,",
     "    browseRequest: Int = 0,\n"
     "    commentsShown: Boolean = false,\n"
     "    onCloseComments: () -> Unit = {},\n"
     "    controlsShown: Boolean = false,")
once(browse,
     "        when {\n            browsing -> close()",
     "        when {\n            commentsShown -> onCloseComments()\n"
     "            browsing -> close()")
once(browse,
     "                browsing -> false",
     "                browsing -> false\n"
     "                commentsShown -> false")

# Previous channel action inexplicably ignored some author-empty videos even
# though the actual channel ID can be obtained from video metadata.
shell = ui / "V112SmartTubeShell.kt"
once(shell, "        if (video.author.isBlank()) return",
     "        if (video.videoId.isBlank()) return")

assert 'testTag("smarttube-comments-button")' in player.read_text()
assert 'testTag("smarttube-channel-identity")' in player.read_text()
assert 'commentsShown -> onCloseComments()' in browse.read_text()
assert 'V183SmartTubeSocial.creator(context, video.videoId)' in player.read_text()
print("V183_REAL_CREATOR_AVATAR_SUBSCRIBERS_CHANNEL_AND_COMMENTS_READY")
print("V183_APPROVED_INTRO_FIRETV_LICENSE_IPTV_VPN_UNCHANGED")
