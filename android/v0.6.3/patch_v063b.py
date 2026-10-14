#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace not found: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace not found: {signature}")


def transform_function(text: str, signature: str, fn):
    a, b = function_span(text, signature)
    old = text[a:b]
    new = fn(old)
    if new == old:
        raise SystemExit(f"function transform made no change: {signature}")
    return text[:a] + new + text[b:]


def inject_profile_guard(block: str, value_name: str, profile_name: str = "p") -> str:
    success = f".onSuccess {{ {value_name} ->"
    if success not in block:
        raise SystemExit(f"success callback missing for {value_name}")
    block = block.replace(
        success,
        success + f"\n                if (_ui.value.active?.id != {profile_name}.id) return@onSuccess",
        1,
    )
    failure = ".onFailure { e ->"
    if failure in block:
        block = block.replace(
            failure,
            failure + f"\n                if (_ui.value.active?.id != {profile_name}.id) return@onFailure",
            1,
        )
    return block


# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 602', 'versionCode = 603', 'versionCode')
replace_once(gradle, 'versionName = "0.6.2"', 'versionName = "0.6.3"', 'versionName')
home = java / "ui/V044Home.kt"
home_text = home.read_text()
if "0.6.2" not in home_text:
    raise SystemExit("visible home version 0.6.2 not found")
home.write_text(home_text.replace("0.6.2", "0.6.3"))


# ---------------------------------------------------------------------------
# Bind a media item to the playlist that produced it.
# ---------------------------------------------------------------------------
models = java / "model/Models.kt"
s = models.read_text()
if 'val sourceProfileId: String = ""' not in s:
    anchor = '    val trailer: String = ""\n)'
    if anchor not in s:
        raise SystemExit("MediaEntry trailer anchor missing")
    s = s.replace(anchor, '    val trailer: String = "",\n    val sourceProfileId: String = ""\n)', 1)
# Keep resume/favorite identities separate for equal Xtream ids on different providers.
s = s.replace(
    ') { val resumeKey: String get() = "${kind.name}:$id" }',
    ') { val resumeKey: String get() = if (sourceProfileId.isBlank()) "${kind.name}:$id" else "$sourceProfileId:${kind.name}:$id" }',
    1,
)
models.write_text(s)

prefs = java / "data/PrefsRepository.kt"
s = prefs.read_text()
meta = 'put("year",m.year);put("duration",m.duration);put("cast",m.cast);put("director",m.director);put("genre",m.genre);put("releaseDate",m.releaseDate);put("trailer",m.trailer)'
if 'put("sourceProfileId",m.sourceProfileId)' not in s:
    if meta not in s:
        raise SystemExit("Prefs media metadata anchor missing")
    s = s.replace(meta, meta + ';put("sourceProfileId",m.sourceProfileId)', 1)
restore = 'releaseDate=o.optString("releaseDate"),trailer=o.optString("trailer")'
if 'sourceProfileId=o.optString("sourceProfileId")' not in s:
    if restore not in s:
        raise SystemExit("Prefs media restore anchor missing")
    s = s.replace(restore, restore + ',sourceProfileId=o.optString("sourceProfileId")', 1)
prefs.write_text(s)


# ---------------------------------------------------------------------------
# Playlist isolation in MainViewModel.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()

# Adding a new profile must not retain rows/items from the previous profile.
def patch_add(block: str) -> str:
    target = '                error = "",\n                epg = emptyMap()'
    if target not in block:
        raise SystemExit("addProfile state anchor missing")
    return block.replace(target, '''                loading = false,
                epgLoading = false,
                error = "",
                categories = emptyList(),
                items = emptyList(),
                searchResults = emptyList(),
                catalogRows = emptyMap(),
                catalogRowsLoading = false,
                epg = emptyMap()''', 1)
s = transform_function(s, '    private fun addProfile(', patch_add)

# Removing a profile also drops everything that belongs to it.
def patch_remove(block: str) -> str:
    target = '                screen = if (list.isEmpty()) Screen.AddPlaylist else Screen.Playlists,\n                epg = emptyMap()'
    if target not in block:
        raise SystemExit("removePlaylist state anchor missing")
    return block.replace(target, '''                screen = if (list.isEmpty()) Screen.AddPlaylist else Screen.Playlists,
                loading = false,
                epgLoading = false,
                categories = emptyList(),
                items = emptyList(),
                searchResults = emptyList(),
                catalogRows = emptyMap(),
                catalogRowsLoading = false,
                epg = emptyMap(),
                error = ""''', 1)
s = transform_function(s, '    fun removePlaylist(', patch_remove)

# Switching is a hard content boundary. Clear the navigation stack as well so Back
# cannot return into a browser screen belonging to another playlist.
a, b = function_span(s, '    fun selectPlaylist(')
select_impl = '''    fun selectPlaylist(id: String) {
        val p = _ui.value.playlists.firstOrNull { it.id == id } ?: return
        prefs.activePlaylistId = id
        back.clear()
        set { it.copy(
            active = p,
            screen = Screen.Home,
            loading = false,
            epgLoading = false,
            categories = emptyList(),
            items = emptyList(),
            searchResults = emptyList(),
            catalogRows = emptyMap(),
            catalogRowsLoading = false,
            epg = emptyMap(),
            error = ""
        ) }
    }'''
s = s[:a] + select_impl + s[b:]

# Catalog row loader: stamp entries and never publish a late response for a profile
# that has since been switched away from.
def patch_catalog(block: str) -> str:
    old = 'XtreamClient(profile).entries(kind, category.id).take(24)'
    if old not in block:
        raise SystemExit("catalog entries anchor missing")
    block = block.replace(old, 'XtreamClient(profile).entries(kind, category.id).map { it.copy(sourceProfileId = profile.id) }.take(24)', 1)
    old_cond = 'if (_ui.value.contentFilterKind == kind) set { it.copy(catalogRows = rows, catalogRowsLoading = false) }'
    if old_cond not in block:
        raise SystemExit("catalog publish guard anchor missing")
    return block.replace(old_cond, 'if (_ui.value.contentFilterKind == kind && _ui.value.active?.id == profile.id) set { it.copy(catalogRows = rows, catalogRowsLoading = false) }', 1)
s = transform_function(s, '    private fun loadCatalogRows(', patch_catalog)

# Category loading can finish after a profile change. Ignore it entirely in that case.
def patch_categories(block: str) -> str:
    return inject_profile_guard(block, 'categories')
s = transform_function(s, '    private fun loadCategories(', patch_categories)

# Media rows are stamped with their source profile and stale callbacks are ignored.
def patch_items(block: str) -> str:
    block = inject_profile_guard(block, 'entries')
    old = '                set { it.copy(loading = false, items = entries) }'
    if old not in block:
        raise SystemExit("loadItems publish anchor missing")
    return block.replace(old, '''                val boundEntries = entries.map { entry -> entry.copy(sourceProfileId = p.id) }
                set { it.copy(loading = false, items = boundEntries) }''', 1).replace(
        'if (kind == MediaKind.LIVE) loadLiveEpg(entries)',
        'if (kind == MediaKind.LIVE) loadLiveEpg(boundEntries)',
        1,
    )
s = transform_function(s, '    private fun loadItems(', patch_items)

def patch_episodes(block: str) -> str:
    block = inject_profile_guard(block, 'entries')
    old = '                set { it.copy(loading = false, items = entries) }'
    if old not in block:
        raise SystemExit("loadEpisodes publish anchor missing")
    return block.replace(old, '                set { it.copy(loading = false, items = entries.map { entry -> entry.copy(sourceProfileId = p.id) }) }', 1)
s = transform_function(s, '    private fun loadEpisodes(', patch_episodes)

# EPG responses are playlist-scoped too.
def patch_epg(block: str) -> str:
    success = '.onSuccess { map ->'
    if success not in block:
        raise SystemExit("loadLiveEpg success anchor missing")
    block = block.replace(success, success + '\n                if (_ui.value.active?.id != p.id) return@onSuccess', 1)
    failure = '.onFailure {'
    if failure in block:
        block = block.replace(failure, failure + '\n                if (_ui.value.active?.id != p.id) return@onFailure', 1)
    return block
s = transform_function(s, '    private fun loadLiveEpg(', patch_epg)

# Search results belong to the profile that initiated the query.
def patch_search(block: str) -> str:
    block = inject_profile_guard(block, 'results')
    old = '                set { it.copy(loading = false, searchResults = results) }'
    if old not in block:
        raise SystemExit("search publish anchor missing")
    return block.replace(old, '                set { it.copy(loading = false, searchResults = results.map { entry -> entry.copy(sourceProfileId = p.id) }) }', 1)
s = transform_function(s, '    fun search(', patch_search)

# Playback and episode sibling lookup resolve credentials from the item's own profile.
def patch_play(block: str) -> str:
    old = '        val profile = _ui.value.active'
    if old not in block:
        raise SystemExit("play profile anchor missing")
    block = block.replace(old, '''        val sourceProfile = _ui.value.playlists.firstOrNull { it.id == item.sourceProfileId }
        val profile = sourceProfile ?: _ui.value.active''', 1)
    old_siblings = 'withContext(Dispatchers.IO) { XtreamClient(profile).episodes(item.seriesId) }'
    if old_siblings in block:
        block = block.replace(old_siblings, 'withContext(Dispatchers.IO) { XtreamClient(profile).episodes(item.seriesId).map { it.copy(sourceProfileId = profile.id) } }', 1)
    return block
s = transform_function(s, '    fun play(', patch_play)

# v0.6.1 added this helper; make it source-profile aware.
a, b = function_span(s, '    fun playbackUrls(')
s = s[:a] + '''    fun playbackUrls(item: MediaEntry): List<String> {
        val sourceProfile = _ui.value.playlists.firstOrNull { it.id == item.sourceProfileId }
        val profile = sourceProfile ?: _ui.value.active
        return if (profile?.type == PlaylistType.XTREAM) {
            XtreamClient(profile).streamCandidates(item)
        } else {
            listOf(item.streamUrl).filter { it.isNotBlank() }
        }
    }''' + s[b:]

vm.write_text(s)


# ---------------------------------------------------------------------------
# Xtream: preserve existing candidates and add common extensionless variants.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()
old_live = '''                extensions.forEach { ext ->
                    urls += "$server/live/$user/$pass/$id.$ext"
                    urls += "$server/$user/$pass/$id.$ext"
                }
'''
if old_live not in s:
    raise SystemExit("Xtream live candidate loop missing")
s = s.replace(old_live, old_live + '''                urls += "$server/live/$user/$pass/$id"
                urls += "$server/$user/$pass/$id"
''', 1)
xtream.write_text(s)


# ---------------------------------------------------------------------------
# Live player: no VOD seek/play/pause controller. Show our own station banner.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
if 'import androidx.compose.ui.layout.ContentScale\n' not in s:
    s = s.replace('import androidx.compose.ui.input.key.onPreviewKeyEvent\n', 'import androidx.compose.ui.input.key.onPreviewKeyEvent\nimport androidx.compose.ui.layout.ContentScale\n', 1)
if 'import androidx.compose.ui.text.font.FontWeight\n' not in s:
    s = s.replace('import androidx.compose.ui.platform.LocalContext\n', 'import androidx.compose.ui.platform.LocalContext\nimport androidx.compose.ui.text.font.FontWeight\n', 1)
if 'import androidx.compose.ui.unit.sp\n' not in s:
    s = s.replace('import androidx.compose.ui.unit.dp\n', 'import androidx.compose.ui.unit.dp\nimport androidx.compose.ui.unit.sp\n', 1)
if 'import coil.compose.AsyncImage\n' not in s:
    s = s.replace('import de.epimediahub.app.MainViewModel\n', 'import coil.compose.AsyncImage\nimport de.epimediahub.app.MainViewModel\n', 1)
if 'import kotlinx.coroutines.delay\n' not in s:
    s = s.replace('import de.epimediahub.app.model.MediaKind\n', 'import de.epimediahub.app.model.MediaKind\nimport kotlinx.coroutines.delay\n', 1)

s = s.replace('val player=remember(item.id){ ExoPlayer.Builder(context).build() }', 'val player=remember(item.resumeKey){ ExoPlayer.Builder(context).build() }', 1)
s = s.replace('DisposableEffect(player,item.id){', 'DisposableEffect(player,item.resumeKey){', 1)

state = '''    val playbackUrls = remember(item.resumeKey, item.streamUrl, u.active?.id) { vm.playbackUrls(item) }
    var controls by remember { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
'''
if state not in s:
    raise SystemExit("Player v0.6.1 state anchor missing")
s = s.replace(state, '''    val playbackUrls = remember(item.resumeKey, item.streamUrl, u.active?.id, item.sourceProfileId) { vm.playbackUrls(item) }
    var controls by remember(item.resumeKey) { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()

    LaunchedEffect(item.resumeKey, controls) {
        if (item.kind == MediaKind.LIVE && controls) {
            delay(4500)
            controls = false
        }
    }
''', 1)

key_anchor = '                    KeyEvent.KEYCODE_DPAD_CENTER,KeyEvent.KEYCODE_ENTER -> {controls=!controls;false}\n'
if key_anchor not in s:
    raise SystemExit("Player OK key anchor missing")
s = s.replace(key_anchor, '''                    KeyEvent.KEYCODE_DPAD_LEFT -> if(item.kind==MediaKind.LIVE) true else if(prev){save();player.release();vm.skipEpisode(item,episodeList,-1);true}else false
                    KeyEvent.KEYCODE_DPAD_RIGHT -> if(item.kind==MediaKind.LIVE) true else if(next){save();player.release();vm.skipEpisode(item,episodeList,1);true}else false
                    KeyEvent.KEYCODE_DPAD_CENTER,KeyEvent.KEYCODE_ENTER -> { controls=!controls; item.kind==MediaKind.LIVE }
''', 1)
# Remove the older LEFT/RIGHT cases because the replacement above supplies both.
s = s.replace('                    KeyEvent.KEYCODE_DPAD_LEFT -> if(prev){save();player.release();vm.skipEpisode(item,episodeList,-1);true}else false\n', '', 1)
s = s.replace('                    KeyEvent.KEYCODE_DPAD_RIGHT -> if(next){save();player.release();vm.skipEpisode(item,episodeList,1);true}else false\n', '', 1)

view_anchor = '''            factory={PlayerView(it).apply{this.player=player;useController=true;controllerAutoShow=true}},
            update={it.player=player},modifier=Modifier.fillMaxSize()
'''
if view_anchor not in s:
    raise SystemExit("PlayerView controller anchor missing")
s = s.replace(view_anchor, '''            factory={PlayerView(it).apply{
                this.player=player
                useController=item.kind!=MediaKind.LIVE
                controllerAutoShow=item.kind!=MediaKind.LIVE
                if(item.kind==MediaKind.LIVE) hideController()
            }},
            update={
                it.player=player
                it.useController=item.kind!=MediaKind.LIVE
                it.controllerAutoShow=item.kind!=MediaKind.LIVE
                if(item.kind==MediaKind.LIVE) it.hideController()
            },modifier=Modifier.fillMaxSize()
''', 1)

episode_anchor = '        if(item.kind==MediaKind.EPISODE && controls){\n'
if episode_anchor not in s:
    raise SystemExit("episode overlay anchor missing")
live_banner = '''        if(item.kind==MediaKind.LIVE && controls){
            Surface(
                modifier=Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(horizontal=24.dp,vertical=26.dp),
                color=Color(0xEA0A0F17),
                shape=MaterialTheme.shapes.large,
                border=androidx.compose.foundation.BorderStroke(1.dp,accent.copy(.85f))
            ){
                Row(
                    Modifier.fillMaxWidth().height(92.dp).padding(horizontal=18.dp,vertical=12.dp),
                    verticalAlignment=Alignment.CenterVertically
                ){
                    Surface(
                        modifier=Modifier.width(132.dp).fillMaxHeight(),
                        color=Color.White,
                        shape=MaterialTheme.shapes.medium
                    ){
                        if(item.image.isNotBlank()) AsyncImage(
                            model=item.image,
                            contentDescription=item.name,
                            modifier=Modifier.fillMaxSize().padding(8.dp),
                            contentScale=ContentScale.Fit
                        ) else Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){
                            Text("TV",color=accent,fontWeight=FontWeight.Black,fontSize=24.sp)
                        }
                    }
                    Spacer(Modifier.width(18.dp))
                    Column(Modifier.weight(1f)){
                        Text(item.name,color=Color.White,fontWeight=FontWeight.Black,fontSize=22.sp,maxLines=1)
                        Text(if(nowProgramme.isNotBlank()) nowProgramme else "Jetzt live",color=Color.White.copy(.75f),fontSize=14.sp,maxLines=1)
                    }
                    Surface(color=accent.copy(.18f),shape=MaterialTheme.shapes.small){
                        Text("LIVE",color=accent,fontWeight=FontWeight.Black,fontSize=12.sp,modifier=Modifier.padding(horizontal=12.dp,vertical=7.dp))
                    }
                }
            }
        }

'''
s = s.replace(episode_anchor, live_banner + episode_anchor, 1)
player.write_text(s)


# ---------------------------------------------------------------------------
# Assertions. If one of the regression fixes is not really present, CI stops.
# ---------------------------------------------------------------------------
assert 'versionName = "0.6.3"' in gradle.read_text()
assert 'val sourceProfileId: String = ""' in models.read_text()
assert 'catalogRows = emptyMap()' in vm.read_text()
assert '_ui.value.active?.id != p.id' in vm.read_text()
assert 'sourceProfile ?: _ui.value.active' in vm.read_text()
assert 'sourceProfileId = profile.id' in vm.read_text()
assert 'urls += "$server/live/$user/$pass/$id"' in xtream.read_text()
assert 'useController=item.kind!=MediaKind.LIVE' in player.read_text()
assert 'if(item.kind==MediaKind.LIVE && controls)' in player.read_text()

print("Android v0.6.3 robust playlist-isolation/live-player patch applied")
