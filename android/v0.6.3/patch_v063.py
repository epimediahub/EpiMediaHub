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


# ---------------------------------------------------------------------------
# Version metadata.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 602', 'versionCode = 603', 'versionCode')
replace_once(gradle, 'versionName = "0.6.2"', 'versionName = "0.6.3"', 'versionName')
home = java / "ui/V044Home.kt"
if "0.6.2" not in home.read_text():
    raise SystemExit("home version anchor missing")
home.write_text(home.read_text().replace("0.6.2", "0.6.3"))


# ---------------------------------------------------------------------------
# Bind every media item to the playlist/profile it came from. This prevents a
# stream id from playlist A from ever being combined with credentials from B.
# ---------------------------------------------------------------------------
models = java / "model/Models.kt"
s = models.read_text()
if 'val sourceProfileId: String = ""' not in s:
    anchor = '    val trailer: String = ""\n)'
    if anchor not in s:
        raise SystemExit("MediaEntry trailer anchor missing")
    s = s.replace(anchor, '    val trailer: String = "",\n    val sourceProfileId: String = ""\n)', 1)
old_resume = ') { val resumeKey: String get() = "${kind.name}:$id" }'
if old_resume in s:
    s = s.replace(old_resume, ') { val resumeKey: String get() = if (sourceProfileId.isBlank()) "${kind.name}:$id" else "$sourceProfileId:${kind.name}:$id" }', 1)
models.write_text(s)

prefs = java / "data/PrefsRepository.kt"
s = prefs.read_text()
old_meta = '        put("year",m.year);put("duration",m.duration);put("cast",m.cast);put("director",m.director);put("genre",m.genre);put("releaseDate",m.releaseDate);put("trailer",m.trailer)\n'
if old_meta not in s:
    raise SystemExit("Prefs metadata persistence anchor missing")
s = s.replace(old_meta, old_meta.rstrip('\n') + ';put("sourceProfileId",m.sourceProfileId)\n', 1)
old_restore = '        duration=o.optString("duration"),cast=o.optString("cast"),director=o.optString("director"),genre=o.optString("genre"),releaseDate=o.optString("releaseDate"),trailer=o.optString("trailer")\n'
if old_restore not in s:
    raise SystemExit("Prefs media restore anchor missing")
s = s.replace(old_restore, '        duration=o.optString("duration"),cast=o.optString("cast"),director=o.optString("director"),genre=o.optString("genre"),releaseDate=o.optString("releaseDate"),trailer=o.optString("trailer"),sourceProfileId=o.optString("sourceProfileId")\n', 1)
prefs.write_text(s)


# ---------------------------------------------------------------------------
# Playlist isolation. Clear old visual state on add/select/remove, stamp loaded
# media with the source profile id and ignore late async responses from a profile
# that is no longer active.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()

old_add = '''                screen = if (goHome) Screen.Home else it.screen,
                error = "",
                epg = emptyMap()
'''
new_add = '''                screen = if (goHome) Screen.Home else it.screen,
                loading = false,
                epgLoading = false,
                error = "",
                categories = emptyList(),
                items = emptyList(),
                searchResults = emptyList(),
                catalogRows = emptyMap(),
                catalogRowsLoading = false,
                epg = emptyMap()
'''
if old_add not in s:
    raise SystemExit("addProfile reset anchor missing")
s = s.replace(old_add, new_add, 1)

old_select = '        set { it.copy(active = p, screen = Screen.Home, categories = emptyList(), items = emptyList(), epg = emptyMap()) }\n'
new_select = '''        back.clear()
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
'''
if old_select not in s:
    raise SystemExit("selectPlaylist anchor missing")
s = s.replace(old_select, new_select, 1)

old_remove = '''                active = list.firstOrNull(),
                screen = if (list.isEmpty()) Screen.AddPlaylist else Screen.Playlists,
                epg = emptyMap()
'''
new_remove = '''                active = list.firstOrNull(),
                screen = if (list.isEmpty()) Screen.AddPlaylist else Screen.Playlists,
                loading = false,
                epgLoading = false,
                categories = emptyList(),
                items = emptyList(),
                searchResults = emptyList(),
                catalogRows = emptyMap(),
                catalogRowsLoading = false,
                epg = emptyMap(),
                error = ""
'''
if old_remove not in s:
    raise SystemExit("removePlaylist reset anchor missing")
s = s.replace(old_remove, new_remove, 1)

# Catalog rows: stamp entries and refuse to publish results after a profile switch.
old_catalog_fetch = 'category.id to runCatching { XtreamClient(profile).entries(kind, category.id).take(24) }.getOrDefault(emptyList())'
new_catalog_fetch = 'category.id to runCatching { XtreamClient(profile).entries(kind, category.id).map { it.copy(sourceProfileId = profile.id) }.take(24) }.getOrDefault(emptyList())'
if old_catalog_fetch not in s:
    raise SystemExit("catalog source binding anchor missing")
s = s.replace(old_catalog_fetch, new_catalog_fetch, 1)
s = s.replace(
    '            if (_ui.value.contentFilterKind == kind) set { it.copy(catalogRows = rows, catalogRowsLoading = false) }\n',
    '            if (_ui.value.contentFilterKind == kind && _ui.value.active?.id == profile.id) set { it.copy(catalogRows = rows, catalogRowsLoading = false) }\n',
    1,
)

# Categories: only the profile that started the request may publish the result.
old_categories_success = '''            }.onSuccess { categories ->
                set { it.copy(loading = false, categories = categories) }
                loadCatalogRows(kind, categories)
            }.onFailure { e ->
                set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
'''
new_categories_success = '''            }.onSuccess { categories ->
                if (_ui.value.active?.id == p.id) {
                    set { it.copy(loading = false, categories = categories) }
                    loadCatalogRows(kind, categories)
                }
            }.onFailure { e ->
                if (_ui.value.active?.id == p.id) set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
'''
if old_categories_success not in s:
    raise SystemExit("loadCategories completion anchor missing")
s = s.replace(old_categories_success, new_categories_success, 1)

# Items: bind source id and suppress stale responses.
old_items_success = '''            }.onSuccess { entries ->
                set { it.copy(loading = false, items = entries) }
                if (kind == MediaKind.LIVE) loadLiveEpg(entries)
            }.onFailure { e ->
                set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
'''
new_items_success = '''            }.onSuccess { entries ->
                if (_ui.value.active?.id == p.id) {
                    val bound = entries.map { it.copy(sourceProfileId = p.id) }
                    set { it.copy(loading = false, items = bound) }
                    if (kind == MediaKind.LIVE) loadLiveEpg(bound)
                }
            }.onFailure { e ->
                if (_ui.value.active?.id == p.id) set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
'''
if old_items_success not in s:
    raise SystemExit("loadItems completion anchor missing")
s = s.replace(old_items_success, new_items_success, 1)

# Episodes: same source binding and stale response protection.
old_episode_success = '''            }.onSuccess { entries ->
                set { it.copy(loading = false, items = entries) }
            }.onFailure { e ->
                set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
'''
new_episode_success = '''            }.onSuccess { entries ->
                if (_ui.value.active?.id == p.id) {
                    set { it.copy(loading = false, items = entries.map { entry -> entry.copy(sourceProfileId = p.id) }) }
                }
            }.onFailure { e ->
                if (_ui.value.active?.id == p.id) set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
'''
if old_episode_success not in s:
    raise SystemExit("loadEpisodes completion anchor missing")
s = s.replace(old_episode_success, new_episode_success, 1)

# Search results are also playlist-bound.
old_search_success = '''            }.onSuccess { results ->
                set { it.copy(loading = false, searchResults = results) }
            }.onFailure { e ->
                set { it.copy(loading = false, error = e.message ?: "Suche fehlgeschlagen") }
            }
'''
new_search_success = '''            }.onSuccess { results ->
                if (_ui.value.active?.id == p.id) {
                    set { it.copy(loading = false, searchResults = results.map { entry -> entry.copy(sourceProfileId = p.id) }) }
                }
            }.onFailure { e ->
                if (_ui.value.active?.id == p.id) set { it.copy(loading = false, error = e.message ?: "Suche fehlgeschlagen") }
            }
'''
if old_search_success not in s:
    raise SystemExit("search completion anchor missing")
s = s.replace(old_search_success, new_search_success, 1)

# Episode sibling lookup during playback must retain the same source playlist.
old_siblings = 'withContext(Dispatchers.IO) { XtreamClient(profile).episodes(item.seriesId) }\n                }.getOrDefault(emptyList())'
new_siblings = 'withContext(Dispatchers.IO) { XtreamClient(profile).episodes(item.seriesId).map { it.copy(sourceProfileId = profile.id) } }\n                }.getOrDefault(emptyList())'
if old_siblings in s:
    s = s.replace(old_siblings, new_siblings, 1)

# Playback always resolves credentials from the media item source profile first.
old_playback = '''    fun playbackUrls(item: MediaEntry): List<String> {
        val profile = _ui.value.active
        return if (profile?.type == PlaylistType.XTREAM) {
            XtreamClient(profile).streamCandidates(item)
        } else {
            listOf(item.streamUrl).filter { it.isNotBlank() }
        }
    }
'''
new_playback = '''    fun playbackUrls(item: MediaEntry): List<String> {
        val sourceProfile = _ui.value.playlists.firstOrNull { it.id == item.sourceProfileId }
        val profile = sourceProfile ?: _ui.value.active
        return if (profile?.type == PlaylistType.XTREAM) {
            XtreamClient(profile).streamCandidates(item)
        } else {
            listOf(item.streamUrl).filter { it.isNotBlank() }
        }
    }
'''
if old_playback not in s:
    raise SystemExit("playback profile binding anchor missing")
s = s.replace(old_playback, new_playback, 1)
vm.write_text(s)


# ---------------------------------------------------------------------------
# More tolerant Xtream live stream candidates. Some panels serve extensionless
# stream paths even though the API/M3U advertises ts/m3u8.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()
old_live_candidates = '''                extensions.forEach { ext ->
                    urls += "$server/live/$user/$pass/$id.$ext"
                    urls += "$server/$user/$pass/$id.$ext"
                }
'''
new_live_candidates = '''                extensions.forEach { ext ->
                    urls += "$server/live/$user/$pass/$id.$ext"
                    urls += "$server/$user/$pass/$id.$ext"
                }
                urls += "$server/live/$user/$pass/$id"
                urls += "$server/$user/$pass/$id"
'''
if old_live_candidates not in s:
    raise SystemExit("Xtream live candidate anchor missing")
s = s.replace(old_live_candidates, new_live_candidates, 1)
xtream.write_text(s)


# ---------------------------------------------------------------------------
# Live TV player: disable Media3's VOD controller completely and render a
# dedicated station banner with logo/name/current programme. OK toggles only
# this banner on Live TV. VOD/episodes keep the normal Media3 controls.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()

imports_anchor = 'import androidx.compose.ui.platform.LocalContext\n'
if 'import androidx.compose.ui.layout.ContentScale\n' not in s:
    s = s.replace(imports_anchor, 'import androidx.compose.ui.layout.ContentScale\n' + imports_anchor, 1)
if 'import androidx.compose.ui.text.font.FontWeight\n' not in s:
    s = s.replace('import androidx.compose.ui.unit.dp\n', 'import androidx.compose.ui.text.font.FontWeight\nimport androidx.compose.ui.unit.dp\nimport androidx.compose.ui.unit.sp\n', 1)
if 'import coil.compose.AsyncImage\n' not in s:
    s = s.replace('import de.epimediahub.app.MainViewModel\n', 'import coil.compose.AsyncImage\nimport de.epimediahub.app.MainViewModel\n', 1)
if 'import kotlinx.coroutines.delay\n' not in s:
    s = s.replace('import de.epimediahub.app.model.MediaKind\n', 'import de.epimediahub.app.model.MediaKind\nimport kotlinx.coroutines.delay\n', 1)

old_state = '''    val playbackUrls = remember(item.resumeKey, item.streamUrl, u.active?.id) { vm.playbackUrls(item) }
    var controls by remember { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
'''
new_state = '''    val playbackUrls = remember(item.resumeKey, item.streamUrl, u.active?.id, item.sourceProfileId) { vm.playbackUrls(item) }
    var controls by remember(item.resumeKey) { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()

    LaunchedEffect(item.resumeKey, controls) {
        if (item.kind == MediaKind.LIVE && controls) {
            delay(4500)
            controls = false
        }
    }
'''
if old_state not in s:
    raise SystemExit("Player state anchor missing")
s = s.replace(old_state, new_state, 1)

old_center = '                    KeyEvent.KEYCODE_DPAD_CENTER,KeyEvent.KEYCODE_ENTER -> {controls=!controls;false}\n'
new_center = '                    KeyEvent.KEYCODE_DPAD_CENTER,KeyEvent.KEYCODE_ENTER -> { controls=!controls; item.kind==MediaKind.LIVE }\n'
if old_center not in s:
    raise SystemExit("Player center key anchor missing")
s = s.replace(old_center, new_center, 1)

old_view = '''            factory={PlayerView(it).apply{this.player=player;useController=true;controllerAutoShow=true}},
            update={it.player=player},modifier=Modifier.fillMaxSize()
'''
new_view = '''            factory={PlayerView(it).apply{
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
'''
if old_view not in s:
    raise SystemExit("PlayerView controller anchor missing")
s = s.replace(old_view, new_view, 1)

banner_anchor = '''        if(item.kind==MediaKind.EPISODE && controls){
'''
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
if banner_anchor not in s:
    raise SystemExit("episode controls anchor missing")
s = s.replace(banner_anchor, live_banner + banner_anchor, 1)
player.write_text(s)


# Hard assertions for the three regressions fixed in this release.
assert 'sourceProfileId' in models.read_text()
assert 'catalogRows = emptyMap()' in vm.read_text()
assert 'sourceProfile ?: _ui.value.active' in vm.read_text()
assert 'urls += "$server/live/$user/$pass/$id"' in xtream.read_text()
assert 'useController=item.kind!=MediaKind.LIVE' in player.read_text()
assert 'if(item.kind==MediaKind.LIVE && controls)' in player.read_text()

print("Android v0.6.3 playlist isolation and Live-TV player patch applied")
