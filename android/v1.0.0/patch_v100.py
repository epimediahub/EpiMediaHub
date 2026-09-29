#!/usr/bin/env python3
"""Android 1.0.0 development patch: header safe-zone, playlist quick action,
SmartTube in-app shell, and rotating recently-added cinema focus."""
import os
import shutil
import re
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))

# ---------------------------------------------------------------------------
# Version 1.0.0 development baseline.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 909", "versionCode = 1000", "versionCode")
replace_once(gradle, 'versionName = "0.9.9"', 'versionName = "1.0.0"', "versionName")
for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("0.9.9", "1.0.0"))

# ---------------------------------------------------------------------------
# SmartTube integration shell.
#
# This is deliberately an internal screen, not an external-app launcher.
# The shell becomes the stable EpiMediaHub route while SmartTube core is
# integrated behind it on the development branch.
# ---------------------------------------------------------------------------
shutil.copyfile(here / "V100SmartTubeShell.kt", java / "ui/V100SmartTubeShell.kt")
shutil.copyfile(here / "V100SmartTubeCore.kt", java / "ui/V100SmartTubeCore.kt")
shutil.copyfile(here / "V100MediathekBranding.kt", java / "ui/V100MediathekBranding.kt")

home = java / "ui/V083Home.kt"
h = home.read_text()
if "import androidx.compose.foundation.shape.CircleShape" not in h:
    replace_once(
        home,
        "import androidx.compose.foundation.shape.RoundedCornerShape\n",
        "import androidx.compose.foundation.shape.CircleShape\nimport androidx.compose.foundation.shape.RoundedCornerShape\n",
        "home CircleShape import",
    )
    h = home.read_text()

state_anchor = '''    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var weather by remember { mutableStateOf<V070WeatherSnapshot?>(V070WeatherClient.cached(context)) }
'''
if state_anchor not in h:
    raise SystemExit("home state anchor missing")
h = h.replace(
    state_anchor,
    state_anchor + '''    var smartTubeOpen by remember { mutableStateOf(false) }

    if (smartTubeOpen) {
        V100SmartTubeShell(
            vm = vm,
            accent = accent,
            isTv = isTv,
            onBack = { smartTubeOpen = false }
        )
        return
    }

''',
    1,
)

old_playlist = '''        V083Tile(
            "PLAYLISTS",
            if (u.playlists.size > 1) "${u.playlists.size} Profile · wechseln" else "Verwalten · hinzufügen",
            R.drawable.icon_playlist
        ) {
            vm.navigate(Screen.Playlists)
        },
'''
if old_playlist not in h:
    raise SystemExit("home playlist tile anchor missing")
h = h.replace(
    old_playlist,
    '''        V083Tile(
            "SMARTTUBE",
            "YouTube · integriert · TV optimiert",
            R.drawable.icon_playlist
        ) {
            smartTubeOpen = true
        },
''',
    1,
)

header_call = '''                weather = weather,
                modifier = Modifier.fillMaxWidth().height(headerHeight)
'''
if header_call not in h:
    raise SystemExit("home header call anchor missing")
h = h.replace(
    header_call,
    '''                weather = weather,
                showPlaylistSwitch = u.playlists.size > 1,
                onPlaylistSwitch = { vm.navigate(Screen.Playlists) },
                modifier = Modifier.fillMaxWidth().height(headerHeight)
''',
    1,
)

header_sig = '''    now: Long,
    weather: V070WeatherSnapshot?,
    modifier: Modifier = Modifier
) {
'''
if header_sig not in h:
    raise SystemExit("home header signature anchor missing")
h = h.replace(
    header_sig,
    '''    now: Long,
    weather: V070WeatherSnapshot?,
    showPlaylistSwitch: Boolean,
    onPlaylistSwitch: () -> Unit,
    modifier: Modifier = Modifier
) {
''',
    1,
)

# Keep weather/time/date inside a fixed header safe-zone above large skin marks.
old_clock = '''            Column(
                Modifier.align(Alignment.BottomCenter)
                    .padding(bottom = if (isTv) 8.dp else 2.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
'''
if old_clock not in h:
    raise SystemExit("home clock block anchor missing")
h = h.replace(
    old_clock,
    '''            Column(
                Modifier.align(Alignment.TopCenter)
                    .padding(top = if (isTv) 10.dp else 2.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
''',
    1,
)

# Playlist switching becomes a compact round quick action below profile/version.
version_block = '''            Text(
                if (isTv) "ANDROID TV · 1.0.0" else "ANDROID MOBILE · 1.0.0",
                color = Color.White.copy(.45f),
                fontSize = if (isTv) 11.sp else 9.sp,
                fontWeight = FontWeight.Bold
            )
'''
if version_block not in h:
    raise SystemExit("home version block anchor missing")
h = h.replace(
    version_block,
    version_block + '''            if (showPlaylistSwitch) {
                Spacer(Modifier.height(if (isTv) 8.dp else 4.dp))
                var playlistFocused by remember { mutableStateOf(false) }
                Surface(
                    modifier = Modifier
                        .size(if (isTv) 42.dp else 34.dp)
                        .onFocusChanged { playlistFocused = it.isFocused }
                        .focusable()
                        .clickable(onClick = onPlaylistSwitch),
                    color = if (playlistFocused) accent.copy(.90f) else Color(0xC71A222C),
                    shape = CircleShape,
                    border = androidx.compose.foundation.BorderStroke(
                        if (playlistFocused) 2.dp else 1.dp,
                        if (playlistFocused) Color.White else Color.White.copy(.20f)
                    )
                ) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text(
                            "↔",
                            color = Color.White,
                            fontSize = if (isTv) 20.sp else 16.sp,
                            fontWeight = FontWeight.Black
                        )
                    }
                }
            }
''',
    1,
)
home.write_text(h)

# ---------------------------------------------------------------------------
# Movies/series: the synthetic "__recently_added__" feed already comes from
# Xtream's added timestamp. Give it a dedicated row and make "Heute im Fokus"
# rotate through those newest titles every four seconds.
# ---------------------------------------------------------------------------
hub = java / "ui/V060CinematicHub.kt"
s = hub.read_text()

# Replace only the variable declaration slice, tolerant of formatting changes
# introduced by the 0.8/0.9 patches.
recent_match = re.search(r'^\s{4}val recent = .*$', s, re.M)
continue_match = re.search(r'^\s{4}val continueItems = .*$', s, re.M)
visible_match = re.search(r'^\s{4}val visibleCategories = .*$', s, re.M)
first_match = re.search(r'^\s{4}val firstCatalog = .*$', s, re.M)
hero_match = re.search(r'^\s{4}val hero = .*$', s, re.M)
if not all((recent_match, continue_match, visible_match, first_match, hero_match)):
    fn = s.find("fun V060CinematicHubScreen")
    raise SystemExit("cinematic variable declarations missing: " + s[fn:fn + 1800])

slice_start = recent_match.start()
slice_end = hero_match.end()
new_vars = '''    val recent = u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }
    val continueItems = u.continueWatching.filter { it.media.kind == kind || (kind == MediaKind.SERIES && it.media.kind == MediaKind.EPISODE) }
    val newest = u.catalogRows["__recently_added__"].orEmpty().sortedByDescending { it.addedAt }
    val visibleCategories = u.categories.filter {
        it.id != "__recently_added__" &&
            it.id !in u.hiddenCategoryIds &&
            u.catalogRows[it.id].orEmpty().isNotEmpty()
    }
    val firstCatalog = visibleCategories.asSequence().mapNotNull { u.catalogRows[it.id]?.firstOrNull() }.firstOrNull()
    var heroIndex by remember(kind, u.active?.id) { mutableIntStateOf(0) }
    LaunchedEffect(kind, u.active?.id, newest.size) {
        heroIndex = 0
        while (newest.size > 1) {
            delay(4_000L)
            heroIndex = (heroIndex + 1) % newest.size
        }
    }
    val hero = newest.getOrNull(heroIndex) ?: recent.firstOrNull() ?: firstCatalog'''
s = s[:slice_start] + new_vars + s[slice_end:]

index_match = re.search(
    r'    val categoryStartIndex =\n(?:        .*\n){1,8}',
    s,
)
if not index_match:
    raise SystemExit("cinematic category index anchor missing")
old_index_block = index_match.group(0)
# Stop at the blank line following the arithmetic expression if the regex
# captured more than the expression.
parts = old_index_block.split("\n")
kept = []
for line in parts:
    if kept and line == "":
        break
    kept.append(line)
old_index_block = "\n".join(kept)
new_index = '''    val categoryStartIndex =
        (if (hero != null) 1 else 0) +
        1 +
        (if (newest.isNotEmpty()) 1 else 0) +
        (if (continueItems.isNotEmpty()) 1 else 0) +
        (if (recent.isNotEmpty()) 1 else 0)'''
s = s.replace(old_index_block, new_index, 1)

# Fixed key prevents the whole hero row from being recreated as a different list
# item every four seconds.
if 'item(key = "hero:" + featured.resumeKey)' in s:
    s = s.replace('item(key = "hero:" + featured.resumeKey)', 'item(key = "hero-focus")', 1)
elif 'item(key = "hero:${featured.resumeKey}")' in s:
    s = s.replace('item(key = "hero:${featured.resumeKey}")', 'item(key = "hero-focus")', 1)
else:
    raise SystemExit("cinematic hero key anchor missing")

actions_end = '''                    if (continueItems.isNotEmpty()) {
'''
if actions_end not in s:
    raise SystemExit("cinematic actions/new row anchor missing")
newest_row = '''                    if (newest.isNotEmpty()) {
                        item(key = "recently-added") {
                            V060PosterRow(
                                "ZULETZT HINZUGEFÜGT",
                                newest,
                                accent,
                                isTv,
                                onMore = {
                                    vm.switchLibraryCategory(
                                        kind,
                                        MediaCategory("__recently_added__", "Zuletzt hinzugefügt")
                                    )
                                }
                            ) {
                                vm.navigate(Screen.Details(it))
                            }
                        }
                    }
'''
s = s.replace(actions_end, newest_row + actions_end, 1)
hub.write_text(s)

# ---------------------------------------------------------------------------
# Mediathek: keep the existing country -> provider hierarchy, make the country
# stage explicit, and add recognizable broadcaster marks to provider cards.
# ---------------------------------------------------------------------------
parity = java / "ui/ParityScreens.kt"
ps = parity.read_text()
if 'EpiTopBar("MEDIATHEK",' in ps:
    ps = ps.replace('EpiTopBar("MEDIATHEK",', 'EpiTopBar("MEDIATHEK · LÄNDER",', 1)

provider_title = 'Text(provider.label, color = Color.White, fontWeight = FontWeight.Black, fontSize = 19.sp)'
if provider_title not in ps:
    raise SystemExit("Mediathek provider title anchor missing")
ps = ps.replace(
    provider_title,
    '''V100BroadcasterLogo(provider.label, accent, isTv)
            Text(provider.label, color = Color.White, fontWeight = FontWeight.Black, fontSize = 19.sp)''',
    1,
)
parity.write_text(ps)

# Guards for the first 1.0.0 development slice.
checks = [
    (gradle, 'versionCode = 1000'),
    (gradle, 'versionName = "1.0.0"'),
    (home, '"SMARTTUBE"'),
    (home, 'showPlaylistSwitch = u.playlists.size > 1'),
    (home, 'Modifier.align(Alignment.TopCenter)'),
    (hub, 'val newest = u.catalogRows["__recently_added__"]'),
    (hub, 'delay(4_000L)'),
    (hub, '"ZULETZT HINZUGEFÜGT"'),
    (java / "ui/V100SmartTubeShell.kt", 'fun V100SmartTubeShell'),
    (java / "ui/V100SmartTubeCore.kt", "internal object V100SmartTubeCore"),
    (java / "ui/V100MediathekBranding.kt", "fun V100BroadcasterLogo"),
    (java / "ui/ParityScreens.kt", "V100BroadcasterLogo(provider.label, accent, isTv)"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 1.0.0 marker missing in {path}: {marker}")

print("Android 1.0.0 development slice applied")
