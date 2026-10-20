#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
path = root / "app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
s = path.read_text()


def replace_once(old: str, new: str, label: str):
    global s
    count = s.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    s = s.replace(old, new, 1)


# Imports needed for the dedicated Live-TV station banner.
if 'import androidx.compose.ui.layout.ContentScale\n' not in s:
    replace_once('import androidx.compose.ui.input.key.onPreviewKeyEvent\n', 'import androidx.compose.ui.input.key.onPreviewKeyEvent\nimport androidx.compose.ui.layout.ContentScale\n', 'ContentScale import')
if 'import androidx.compose.ui.text.font.FontWeight\n' not in s:
    replace_once('import androidx.compose.ui.platform.LocalContext\n', 'import androidx.compose.ui.platform.LocalContext\nimport androidx.compose.ui.text.font.FontWeight\n', 'FontWeight import')
if 'import androidx.compose.ui.unit.sp\n' not in s:
    replace_once('import androidx.compose.ui.unit.dp\n', 'import androidx.compose.ui.unit.dp\nimport androidx.compose.ui.unit.sp\n', 'sp import')
if 'import coil.compose.AsyncImage\n' not in s:
    replace_once('import de.epimediahub.app.MainViewModel\n', 'import coil.compose.AsyncImage\nimport de.epimediahub.app.MainViewModel\n', 'AsyncImage import')
if 'import kotlinx.coroutines.delay\n' not in s:
    replace_once('import de.epimediahub.app.model.MediaKind\n', 'import de.epimediahub.app.model.MediaKind\nimport kotlinx.coroutines.delay\n', 'delay import')

# Bind the ExoPlayer instance and playback URL list to the playlist-aware resume key.
replace_once(
    '    val player = remember(item.id) { ExoPlayer.Builder(context).build() }\n',
    '    val player = remember(item.resumeKey) { ExoPlayer.Builder(context).build() }\n',
    'player remember key',
)
replace_once(
    '    val playbackUrls = remember(item.resumeKey, item.streamUrl, u.active?.id) { vm.playbackUrls(item) }\n',
    '    val playbackUrls = remember(item.resumeKey, item.streamUrl, u.active?.id, item.sourceProfileId) { vm.playbackUrls(item) }\n',
    'playback URLs remember key',
)
replace_once(
    '    var controls by remember { mutableStateOf(true) }\n    var playbackError by remember(item.resumeKey) { mutableStateOf("") }\n',
    '''    var controls by remember(item.resumeKey) { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()

    LaunchedEffect(item.resumeKey, controls) {
        if (item.kind == MediaKind.LIVE && controls) {
            delay(4500)
            controls = false
        }
    }
''',
    'Live banner state',
)
replace_once('    DisposableEffect(player, item.id) {\n', '    DisposableEffect(player, item.resumeKey) {\n', 'player DisposableEffect key')

# Current TV keymap: keep VOD/episode behaviour intact, but prevent Live TV from
# seeking when left/right is pressed and make OK control only our banner.
replace_once(
    '                    KeyEvent.KEYCODE_DPAD_LEFT -> if (isEpisode && prev) previousEpisode() else { seekBy(-10_000L); true }\n',
    '                    KeyEvent.KEYCODE_DPAD_LEFT -> if (item.kind == MediaKind.LIVE) true else if (isEpisode && prev) previousEpisode() else { seekBy(-10_000L); true }\n',
    'DPAD left Live guard',
)
replace_once(
    '                    KeyEvent.KEYCODE_DPAD_RIGHT -> if (isEpisode && next) nextEpisode() else { seekBy(10_000L); true }\n',
    '                    KeyEvent.KEYCODE_DPAD_RIGHT -> if (item.kind == MediaKind.LIVE) true else if (isEpisode && next) nextEpisode() else { seekBy(10_000L); true }\n',
    'DPAD right Live guard',
)
replace_once(
    '''                    KeyEvent.KEYCODE_DPAD_CENTER,
                    KeyEvent.KEYCODE_ENTER -> { controls = !controls; false }
''',
    '''                    KeyEvent.KEYCODE_DPAD_CENTER,
                    KeyEvent.KEYCODE_ENTER -> { controls = !controls; item.kind == MediaKind.LIVE }
''',
    'OK Live banner toggle',
)

# Media3's transport controller must never appear for a linear Live-TV channel.
replace_once(
    '''            factory = {
                PlayerView(it).apply {
                    this.player = player
                    useController = true
                    controllerAutoShow = true
                }
            },
            update = { it.player = player },
            modifier = Modifier.fillMaxSize()
''',
    '''            factory = {
                PlayerView(it).apply {
                    this.player = player
                    useController = item.kind != MediaKind.LIVE
                    controllerAutoShow = item.kind != MediaKind.LIVE
                    if (item.kind == MediaKind.LIVE) hideController()
                }
            },
            update = {
                it.player = player
                it.useController = item.kind != MediaKind.LIVE
                it.controllerAutoShow = item.kind != MediaKind.LIVE
                if (item.kind == MediaKind.LIVE) it.hideController()
            },
            modifier = Modifier.fillMaxSize()
''',
    'PlayerView Live controller disable',
)

# Keep the useful remote hint for VOD/episodes only. It must not appear over Live TV.
replace_once(
    '        if (isTv && controls) {\n',
    '        if (isTv && controls && item.kind != MediaKind.LIVE) {\n',
    'TV help overlay Live exclusion',
)

# Dedicated station banner: channel logo, channel name and current EPG programme.
anchor = '        if (isEpisode && controls) {\n'
if anchor not in s:
    raise SystemExit('episode overlay anchor missing')
live_banner = '''        if (item.kind == MediaKind.LIVE && controls) {
            Surface(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(horizontal = 24.dp, vertical = 26.dp),
                color = Color(0xEA0A0F17),
                shape = MaterialTheme.shapes.large,
                border = androidx.compose.foundation.BorderStroke(1.dp, accent.copy(alpha = .85f))
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().height(92.dp).padding(horizontal = 18.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Surface(
                        modifier = Modifier.width(132.dp).fillMaxHeight(),
                        color = Color.White,
                        shape = MaterialTheme.shapes.medium
                    ) {
                        if (item.image.isNotBlank()) {
                            AsyncImage(
                                model = item.image,
                                contentDescription = item.name,
                                modifier = Modifier.fillMaxSize().padding(8.dp),
                                contentScale = ContentScale.Fit
                            )
                        } else {
                            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                Text("TV", color = accent, fontWeight = FontWeight.Black, fontSize = 24.sp)
                            }
                        }
                    }
                    Spacer(Modifier.width(18.dp))
                    Column(Modifier.weight(1f)) {
                        Text(item.name, color = Color.White, fontWeight = FontWeight.Black, fontSize = 22.sp, maxLines = 1)
                        Text(
                            if (nowProgramme.isNotBlank()) nowProgramme else "Jetzt live",
                            color = Color.White.copy(alpha = .75f),
                            fontSize = 14.sp,
                            maxLines = 1
                        )
                    }
                    Surface(color = accent.copy(alpha = .18f), shape = MaterialTheme.shapes.small) {
                        Text(
                            "LIVE",
                            color = accent,
                            fontWeight = FontWeight.Black,
                            fontSize = 12.sp,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp)
                        )
                    }
                }
            }
        }

'''
s = s.replace(anchor, live_banner + anchor, 1)

path.write_text(s)

# Regression assertions: default Live controller gone, station banner present,
# old TV help excluded from Live, and source profile participates in player identity.
final = path.read_text()
assert 'useController = item.kind != MediaKind.LIVE' in final
assert 'if (item.kind == MediaKind.LIVE) hideController()' in final
assert 'if (item.kind == MediaKind.LIVE && controls)' in final
assert 'if (isTv && controls && item.kind != MediaKind.LIVE)' in final
assert 'nowProgramme' in final
assert 'item.sourceProfileId' in final
assert 'KEYCODE_ENTER -> { controls = !controls; item.kind == MediaKind.LIVE }' in final
print("Android v0.6.3 Live-TV PlayerScreen patch applied")
