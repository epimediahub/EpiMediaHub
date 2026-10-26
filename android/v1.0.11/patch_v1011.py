#!/usr/bin/env python3
import os
import re
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))

def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace not found: {signature}")

def replace_in_function(path: Path, signature: str, old: str, new: str, label: str):
    text = path.read_text()
    a, b = function_span(text, signature)
    fn = text[a:b]
    count = fn.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor in function, found {count}")
    fn = fn.replace(old, new, 1)
    path.write_text(text[:a] + fn + text[b:])

# ---------------------------------------------------------------------------
# Version + SmartTube v1.0.11 source.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1010", "versionCode = 1011", "versionCode")
replace_once(gradle, 'versionName = "1.0.10"', 'versionName = "1.0.11"', "versionName")

for relative in (
    "ui/Screens.kt",
    "ui/V078DashboardPairingGate.kt",
    "ui/V083Home.kt",
    "data/V070WeatherClient.kt",
):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("1.0.10", "1.0.11"))

shutil.copyfile(here / "V111MenuMemory.kt", java / "ui/V111MenuMemory.kt")
shutil.copyfile(here / "V111SmartTubeShell.kt", java / "ui/V111SmartTubeShell.kt")
shutil.copyfile(here / "V111SmartTubePlayer.kt", java / "ui/V111SmartTubePlayer.kt")

home = java / "ui/V083Home.kt"
replace_once(
    home,
    "        V110SmartTubeShell(\n",
    "        V111SmartTubeShell(\n",
    "SmartTube v1.0.11 route",
)

# ---------------------------------------------------------------------------
# Global Back-navigation memory.
# Home: restore the exact last tile instead of always forcing tile 0.
# ---------------------------------------------------------------------------
hs = home.read_text()
state_anchor = '    val firstFocus = remember { FocusRequester() }\n'
if state_anchor not in hs:
    raise SystemExit("home firstFocus anchor missing")
hs = hs.replace(
    state_anchor,
    state_anchor + '    val homeMenuKey = "home-main"\n',
    1,
)
hs = hs.replace(
    '''        if (isTv) {
            delay(80L)
            runCatching { firstFocus.requestFocus() }
        }
''',
    '''        if (isTv && V111MenuMemory.id(homeMenuKey).isBlank()) {
            delay(80L)
            runCatching { firstFocus.requestFocus() }
        }
''',
    1,
)
old_home_modifier = '''                                    modifier = Modifier.weight(1f)
                                        .fillMaxHeight()
                                        .then(
                                            if (index == 0) Modifier.focusRequester(firstFocus)
                                            else Modifier
                                        ),
'''
new_home_modifier = '''                                    modifier = Modifier.weight(1f)
                                        .fillMaxHeight()
                                        .then(
                                            v111RememberFocus(
                                                menuKey = homeMenuKey,
                                                itemId = tile.title,
                                                index = index,
                                                enabled = isTv
                                            )
                                        )
                                        .then(
                                            if (index == 0 && V111MenuMemory.id(homeMenuKey).isBlank())
                                                Modifier.focusRequester(firstFocus)
                                            else Modifier
                                        ),
'''
if old_home_modifier not in hs:
    raise SystemExit("home tile modifier anchor missing")
hs = hs.replace(old_home_modifier, new_home_modifier, 1)
home.write_text(hs)

# ---------------------------------------------------------------------------
# Movies / Series: remember vertical row and each horizontal shelf position.
# ---------------------------------------------------------------------------
hub = java / "ui/V060CinematicHub.kt"
h = hub.read_text()
if "val contentState = rememberLazyListState()" not in h:
    raise SystemExit("cinematic content state anchor missing")
h = h.replace(
    "    val contentState = rememberLazyListState()\n",
    '    val contentState = v111RememberLazyListState("cinematic-main:" + kind.name)\n',
    1,
)

row_sig = "private fun V060PosterRow("
a, b = function_span(h, row_sig)
row_fn = h[a:b]
if 'val rowState = v111RememberLazyListState(' not in row_fn:
    row_fn = row_fn.replace(
        '    Column(Modifier.fillMaxWidth()) {\n',
        '    val rowKey = "cinematic-row:" + title\n'
        '    val rowState = v111RememberLazyListState(rowKey)\n'
        '    Column(Modifier.fillMaxWidth()) {\n',
        1,
    )
    row_fn = row_fn.replace(
        '        LazyRow(\n',
        '        LazyRow(\n            state = rowState,\n',
        1,
    )
    row_fn = row_fn.replace(
        '            items(entries.take(24), key = { it.resumeKey }) { item -> V060Poster(item, accent, isTv) { onItem(item) } }',
        '''            itemsIndexed(entries.take(24), key = { _, item -> item.resumeKey }) { index, item ->
                V060Poster(
                    item,
                    accent,
                    isTv,
                    rememberedFocus = v111RememberFocus(rowKey, item.resumeKey, index, isTv)
                ) { onItem(item) }
            }''',
        1,
    )
h = h[:a] + row_fn + h[b:]

# Poster accepts the remembered-focus modifier. Later visual patches keep this
# function, so this is a stable place to restore exact movie/series focus.
a, b = function_span(h, "private fun V060Poster(")
poster = h[a:b]
poster = poster.replace(
    "private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, onClick: () -> Unit)",
    "private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, rememberedFocus: Modifier = Modifier, onClick: () -> Unit)",
    1,
)
poster = poster.replace(
    ".shadow(shadow, shape)\n            .onFocusChanged",
    ".shadow(shadow, shape)\n            .then(rememberedFocus)\n            .onFocusChanged",
    1,
)
h = h[:a] + poster + h[b:]
hub.write_text(h)

# ---------------------------------------------------------------------------
# Live TV already remembers selected category/channel IDs. Persist the scroll
# states too so returning never redraws from the top before focus restoration.
# ---------------------------------------------------------------------------
live = java / "ui/V076LiveTv.kt"
ls = live.read_text()
ls = ls.replace(
    "    val railState = rememberLazyListState()\n",
    '    val railState = v111RememberLazyListState("livetv-categories")\n',
    1,
)
ls = ls.replace(
    "    val state = rememberLazyListState()\n",
    '    val state = v111RememberLazyListState("livetv-channels:" + selectedId)\n',
    1,
)
live.write_text(ls)

# ---------------------------------------------------------------------------
# Private skin browser: remember overview/category and scroll position.
# ---------------------------------------------------------------------------
themes = java / "ui/V079Themes.kt"
ts = themes.read_text()
ts = ts.replace(
    '    var selectedGroupId by rememberSaveable { mutableStateOf<String?>(null) }\n',
    '''    var selectedGroupId by rememberSaveable {
        mutableStateOf<String?>(V111MenuMemory.text("themes-group").takeIf { it.isNotBlank() })
    }
''',
    1,
)
ts = ts.replace(
    'selectedGroupId = item.group.id',
    'selectedGroupId = item.group.id; V111MenuMemory.rememberText("themes-group", item.group.id)',
)
# Two major LazyColumns: selected group and category overview.
needle = '''                LazyColumn(
                    Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
'''
first = ts.find(needle)
if first >= 0:
    ts = ts[:first] + ts[first:].replace(
        needle,
        '''                LazyColumn(
                    state = v111RememberLazyListState("themes-detail:" + selected.group.id),
                    modifier = Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
''',
        1,
    )
second = ts.find(needle)
if second >= 0:
    ts = ts[:second] + ts[second:].replace(
        needle,
        '''                LazyColumn(
                    state = v111RememberLazyListState("themes-overview"),
                    modifier = Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
''',
        1,
    )
themes.write_text(ts)

# ---------------------------------------------------------------------------
# Generic library/search/settings/list menus: preserve list positions.
# ---------------------------------------------------------------------------
screens = java / "ui/V035Screens.kt"
if screens.exists():
    # Search
    text = screens.read_text()
    for signature, key in [
        ("fun V035SearchScreen(", "search-results"),
        ("fun V035FavoritesScreen(", "favorites-results"),
    ]:
        a, b = function_span(text, signature)
        fn = text[a:b]
        if "LazyColumn(" in fn and "v111RememberLazyListState" not in fn:
            fn = fn.replace(
                "LazyColumn(",
                f'LazyColumn(state = v111RememberLazyListState("{key}"), ',
                1,
            )
        text = text[:a] + fn + text[b:]
    screens.write_text(text)

# Playlist/settings screens live in Screens.kt in the reconstructed project.
base_screens = java / "ui/Screens.kt"
if base_screens.exists():
    text = base_screens.read_text()
    for signature, key in [
        ("fun PlaylistsScreen(", "playlists"),
        ("fun SettingsScreen(", "settings"),
        ("fun FavoritesScreen(", "favorites"),
        ("fun ContinueWatchingScreen(", "continue-watching"),
    ]:
        if signature not in text:
            continue
        a, b = function_span(text, signature)
        fn = text[a:b]
        if "LazyColumn(" in fn and "v111RememberLazyListState" not in fn:
            fn = fn.replace(
                "LazyColumn(",
                f'LazyColumn(state=v111RememberLazyListState("{key}"),',
                1,
            )
        text = text[:a] + fn + text[b:]
    base_screens.write_text(text)

# Mediathek provider/list pages.
parity = java / "ui/ParityScreens.kt"
if parity.exists():
    text = parity.read_text()
    for signature, key in [
        ("fun ParityMediathekDirectoryScreen(", "mediathek-providers"),
        ("fun ParityEpgGridScreen(", "epg-grid"),
    ]:
        if signature not in text:
            continue
        a, b = function_span(text, signature)
        fn = text[a:b]
        if "LazyColumn(" in fn and "v111RememberLazyListState" not in fn:
            fn = fn.replace(
                "LazyColumn(",
                f'LazyColumn(state = v111RememberLazyListState("{key}"), ',
                1,
            )
        text = text[:a] + fn + text[b:]
    parity.write_text(text)

checks = [
    (gradle, "versionCode = 1011"),
    (gradle, 'versionName = "1.0.11"'),
    (home, "V111SmartTubeShell("),
    (home, "v111RememberFocus("),
    (hub, 'v111RememberLazyListState("cinematic-main:" + kind.name)'),
    (hub, 'v111RememberLazyListState(rowKey)'),
    (live, 'v111RememberLazyListState("livetv-categories")'),
    (themes, 'v111RememberLazyListState("themes-overview")'),
    (java / "ui/V111SmartTubeShell.kt", "V111SmartTubePlayer("),
    (java / "ui/V111SmartTubePlayer.kt", "v111FormatPlaybackTime"),
    (java / "ui/V111MenuMemory.kt", "v111RememberFocus"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v1.0.11 marker {marker} in {path}")

print("Android 1.0.11 YouTube-style SmartTube UI and global Back focus memory applied")
