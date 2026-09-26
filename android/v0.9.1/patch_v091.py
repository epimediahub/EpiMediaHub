#!/usr/bin/env python3
"""Android 0.9.1: season-based series browser and clean TV episode controls."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))

def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace missing: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace missing: {signature}")

def block_span(text: str, marker: str):
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f"block not found: {marker}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace missing: {marker}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace missing: {marker}")

gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 900', 'versionCode = 901', 'versionCode')
replace_once(gradle, 'versionName = "0.9.0"', 'versionName = "0.9.1"', 'versionName')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.9.0", "0.9.1"))

xtream = java / "data/XtreamClient.kt"
replace_once(
    xtream,
    '''                    kind = MediaKind.EPISODE,
                    image =''',
    '''                    kind = MediaKind.EPISODE,
                    categoryId = firstNonBlank(seriesInfo.optString("name"), seriesInfo.optString("title")),
                    image =''',
    'episode series title',
)

screens = java / "ui/Screens.kt"
ss = screens.read_text()
lazy_import = 'import androidx.compose.foundation.lazy.LazyColumn\n'
if 'import androidx.compose.foundation.lazy.LazyRow\n' not in ss:
    if lazy_import not in ss:
        raise SystemExit("LazyColumn import anchor missing")
    ss = ss.replace(lazy_import, lazy_import + 'import androidx.compose.foundation.lazy.LazyRow\n', 1)

a, b = function_span(ss, "fun EpisodesScreen(")
episodes_screen = r'''fun EpisodesScreen(vm:MainViewModel,series:MediaEntry,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    val orderedEpisodes = remember(u.items) {
        u.items.sortedWith(
            compareBy<MediaEntry> { it.season }
                .thenBy { it.episode }
                .thenBy { it.name }
        )
    }
    val seasons = remember(orderedEpisodes) { orderedEpisodes.map { it.season }.distinct() }
    var selectedSeason by remember(series.resumeKey, seasons) { mutableStateOf(seasons.firstOrNull()) }
    val visibleEpisodes = remember(orderedEpisodes, selectedSeason) {
        selectedSeason?.let { season -> orderedEpisodes.filter { it.season == season } }.orEmpty()
    }

    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar(series.name,R.drawable.brand_header,{vm.back()})
        LoadingOrError(u.loading,u.error)

        if(!u.loading && seasons.isEmpty()){
            EmptyState("Keine Episoden","Für diese Serie wurden keine Folgen geliefert.")
        } else if(seasons.isNotEmpty()){
            LazyRow(
                modifier=Modifier.fillMaxWidth(),
                contentPadding=PaddingValues(horizontal=14.dp,vertical=10.dp),
                horizontalArrangement=Arrangement.spacedBy(10.dp)
            ){
                items(seasons,key={it}){season->
                    FilterChip(
                        selected=selectedSeason==season,
                        onClick={selectedSeason=season},
                        label={Text(if(season<=0)"Spezialfolgen" else "Staffel $season",fontWeight=FontWeight.Bold)}
                    )
                }
            }

            LazyVerticalGrid(
                GridCells.Fixed(if(isTv)5 else 2),
                Modifier.fillMaxSize().padding(horizontal=14.dp,vertical=6.dp),
                horizontalArrangement=Arrangement.spacedBy(10.dp),
                verticalArrangement=Arrangement.spacedBy(10.dp)
            ){
                gridItems(visibleEpisodes,key={it.resumeKey}){e->
                    MediaCard(
                        e,
                        accent,
                        if(e.season<=0)"Spezial · Folge ${e.episode}" else "Staffel ${e.season} · Folge ${e.episode}",
                        onClick={vm.play(e,orderedEpisodes)}
                    )
                }
            }
        }
    }
}'''
ss = ss[:a] + episodes_screen + ss[b:]
screens.write_text(ss)

vm = java / "MainViewModel.kt"
vs = vm.read_text()
a, b = function_span(vs, "    fun skipEpisode(")
skip_episode = r'''    fun skipEpisode(current: MediaEntry, episodeList: List<MediaEntry>, direction: Int) {
        if (episodeList.isEmpty()) return
        val ordered = episodeList.sortedWith(
            compareBy<MediaEntry> { it.season }
                .thenBy { it.episode }
                .thenBy { it.name }
        )
        val currentIndex = ordered.indexOfFirst { it.resumeKey == current.resumeKey || it.id == current.id }
        if (currentIndex < 0) return
        val nextIndex = currentIndex + direction
        if (nextIndex !in ordered.indices) return
        set { it.copy(screen = Screen.Player(ordered[nextIndex], ordered)) }
    }'''
vs = vs[:a] + skip_episode + vs[b:]

old_siblings = 'XtreamClient(profile).episodes(item.seriesId).map { it.copy(sourceProfileId = profile.id) }'
if old_siblings in vs:
    vs = vs.replace(
        old_siblings,
        old_siblings + '.sortedWith(compareBy<MediaEntry> { it.season }.thenBy { it.episode }.thenBy { it.name })',
        1,
    )
vm.write_text(vs)

player = java / "ui/PlayerScreen.kt"

replace_once(
    player,
    '''    LaunchedEffect(item.resumeKey, controls) {
        if (item.kind == MediaKind.LIVE && controls) {
            delay(4500)
            controls = false
        }
    }''',
    '''    LaunchedEffect(item.resumeKey, controls) {
        if ((item.kind == MediaKind.LIVE || item.kind == MediaKind.EPISODE) && controls) {
            delay(if (item.kind == MediaKind.LIVE) 4500 else 3500)
            controls = false
        }
    }''',
    'episode controls auto-hide',
)

replace_once(
    player,
    'KeyEvent.KEYCODE_DPAD_LEFT -> if (item.kind == MediaKind.LIVE) switchLiveBy(-1) else if (isEpisode && prev) previousEpisode() else { seekBy(-10_000L); true }',
    'KeyEvent.KEYCODE_DPAD_LEFT -> if (item.kind == MediaKind.LIVE) switchLiveBy(-1) else { seekBy(-10_000L); true }',
    'left seek mapping',
)
replace_once(
    player,
    'KeyEvent.KEYCODE_DPAD_RIGHT -> if (item.kind == MediaKind.LIVE) switchLiveBy(1) else if (isEpisode && next) nextEpisode() else { seekBy(10_000L); true }',
    'KeyEvent.KEYCODE_DPAD_RIGHT -> if (item.kind == MediaKind.LIVE) switchLiveBy(1) else { seekBy(10_000L); true }',
    'right seek mapping',
)
replace_once(
    player,
    'KeyEvent.KEYCODE_DPAD_UP -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(1) else true}else{controls=true;false}',
    'KeyEvent.KEYCODE_DPAD_UP -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(1) else true}else if(isEpisode){controls=true;previousEpisode();true}else{controls=true;false}',
    'up episode mapping',
)
replace_once(
    player,
    'KeyEvent.KEYCODE_DPAD_DOWN -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(-1) else true}else{controls=false;false}',
    'KeyEvent.KEYCODE_DPAD_DOWN -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(-1) else true}else if(isEpisode){controls=true;nextEpisode();true}else{controls=false;false}',
    'down episode mapping',
)
replace_once(
    player,
    '''                    KeyEvent.KEYCODE_DPAD_CENTER,
                    KeyEvent.KEYCODE_ENTER -> { controls = !controls; item.kind == MediaKind.LIVE }''',
    '''                    KeyEvent.KEYCODE_DPAD_CENTER,
                    KeyEvent.KEYCODE_ENTER -> { controls = !controls; true }''',
    'TV OK overlay toggle',
)

p = player.read_text()
old_controller = 'useController = item.kind != MediaKind.LIVE'
old_auto = 'controllerAutoShow = item.kind != MediaKind.LIVE'
if p.count(old_controller) != 2 or p.count(old_auto) != 2:
    raise SystemExit(f"PlayerView controller anchors unexpected: use={p.count(old_controller)} auto={p.count(old_auto)}")
p = p.replace(old_controller, 'useController = item.kind != MediaKind.LIVE && !(isTv && item.kind == MediaKind.EPISODE)')
p = p.replace(old_auto, 'controllerAutoShow = item.kind != MediaKind.LIVE && !(isTv && item.kind == MediaKind.EPISODE)')
replace_hide = 'if (item.kind == MediaKind.LIVE) hideController()'
replace_hide_update = 'if (item.kind == MediaKind.LIVE) it.hideController()'
if p.count(replace_hide) != 1 or p.count(replace_hide_update) != 1:
    raise SystemExit("PlayerView hideController anchors missing")
p = p.replace(replace_hide, 'if (item.kind == MediaKind.LIVE || (isTv && item.kind == MediaKind.EPISODE)) hideController()', 1)
p = p.replace(replace_hide_update, 'if (item.kind == MediaKind.LIVE || (isTv && item.kind == MediaKind.EPISODE)) it.hideController()', 1)

a, b = block_span(p, '        if (isEpisode && controls) {')
episode_overlay = r'''        if (isEpisode && controls) {
            val seriesTitle = item.categoryId.ifBlank { "Serie" }
            Surface(
                modifier = Modifier
                    .align(Alignment.TopStart)
                    .padding(horizontal = 24.dp, vertical = 22.dp)
                    .widthIn(max = 620.dp),
                color = Color.Black.copy(alpha = .72f),
                shape = MaterialTheme.shapes.large,
                border = androidx.compose.foundation.BorderStroke(1.dp, accent.copy(alpha = .65f))
            ) {
                Column(Modifier.padding(horizontal = 20.dp, vertical = 14.dp)) {
                    Text(
                        seriesTitle,
                        color = Color.White,
                        fontWeight = FontWeight.Black,
                        fontSize = 20.sp,
                        maxLines = 1
                    )
                    Text(
                        if (item.season <= 0) "Spezial · Folge ${item.episode}" else "Staffel ${item.season} · Folge ${item.episode}",
                        color = accent,
                        fontWeight = FontWeight.Bold,
                        fontSize = 14.sp
                    )
                    if (item.name.isNotBlank() && !item.name.equals(seriesTitle, ignoreCase = true)) {
                        Text(
                            item.name,
                            color = Color.White.copy(alpha = .78f),
                            fontSize = 13.sp,
                            maxLines = 1
                        )
                    }
                }
            }
        }'''
p = p[:a] + episode_overlay + p[b:]

old_hint = '"←/→ Episode oder ±10 s   ·   1/3 Episode   ·   4/6 ±10 s   ·   5 Play/Pause"'
if old_hint in p:
    p = p.replace(old_hint, '"←/→ ±10 s   ·   ↑/↓ Folge   ·   OK Info   ·   5 Play/Pause"', 1)
player.write_text(p)

checks = [
    (gradle, 'versionCode = 901'),
    (gradle, 'versionName = "0.9.1"'),
    (screens, 'LazyRow('),
    (screens, 'Staffel $season'),
    (screens, 'vm.play(e,orderedEpisodes)'),
    (xtream, 'categoryId = firstNonBlank(seriesInfo.optString("name"), seriesInfo.optString("title"))'),
    (vm, 'val ordered = episodeList.sortedWith('),
    (player, 'delay(if (item.kind == MediaKind.LIVE) 4500 else 3500)'),
    (player, 'KeyEvent.KEYCODE_DPAD_LEFT -> if (item.kind == MediaKind.LIVE) switchLiveBy(-1) else { seekBy(-10_000L); true }'),
    (player, 'else if(isEpisode){controls=true;previousEpisode();true}'),
    (player, 'else if(isEpisode){controls=true;nextEpisode();true}'),
    (player, 'useController = item.kind != MediaKind.LIVE && !(isTv && item.kind == MediaKind.EPISODE)'),
    (player, 'val seriesTitle = item.categoryId.ifBlank { "Serie" }'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.1 marker missing in {path}: {marker}")

print("Android 0.9.1 season browser and clean episode player applied")
