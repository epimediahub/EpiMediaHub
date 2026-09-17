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
# Visible version.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 609', 'versionCode = 610', 'hotfix7 versionCode')
replace_once(gradle, 'versionName = "0.6.4.6"', 'versionName = "0.6.4.7"', 'hotfix7 versionName')

home = java / "ui/V044Home.kt"
home_text = home.read_text()
if "0.6.4.6" not in home_text:
    raise SystemExit("visible home version 0.6.4.6 not found")
home.write_text(home_text.replace("0.6.4.6", "0.6.4.7", 1))

# ---------------------------------------------------------------------------
# Playlist-isolated VOD/series library.
# The cinematic hub used persisted recent/continue/favorites globally, so after
# switching playlists it could still lead with content from the previous source.
# Also the catalog loaded up to 12 categories concurrently. On panels that reject
# category-specific API calls, every category could fall back to downloading the
# complete VOD/series list again. Load one source-scoped library and filter locally.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()

old_cache = '''    private val m3uCache = mutableMapOf<String, M3uParser.Result>()
    private var webAdmin: LocalWebAdmin? = null
'''
new_cache = '''    private val m3uCache = mutableMapOf<String, M3uParser.Result>()
    private val xtreamLibraryCache = java.util.concurrent.ConcurrentHashMap<String, List<MediaEntry>>()
    private var webAdmin: LocalWebAdmin? = null
'''
if old_cache not in s:
    raise SystemExit("ViewModel library cache anchor missing")
s = s.replace(old_cache, new_cache, 1)

# Persisted collections must belong to the active source. Legacy entries without a
# source id are only safe to show when there is a single playlist.
repls = [
    ('                favorites = prefs.loadFavoriteEntries(),\n',
     '                favorites = prefs.loadFavoriteEntries().filter { media -> media.sourceProfileId == it.active?.id || (media.sourceProfileId.isBlank() && it.playlists.size <= 1) },\n',
     'favorites source filter'),
    ('                continueWatching = prefs.loadContinue(),\n',
     '                continueWatching = prefs.loadContinue().filter { entry -> entry.media.sourceProfileId == it.active?.id || (entry.media.sourceProfileId.isBlank() && it.playlists.size <= 1) },\n',
     'continue source filter'),
    ('                recentlyWatched = prefs.loadRecentlyWatched(),\n',
     '                recentlyWatched = prefs.loadRecentlyWatched().filter { media -> media.sourceProfileId == it.active?.id || (media.sourceProfileId.isBlank() && it.playlists.size <= 1) },\n',
     'recent source filter'),
]
for old, new, label in repls:
    if old not in s:
        raise SystemExit(f"{label} anchor missing")
    s = s.replace(old, new, 1)

old_select = '''    fun selectPlaylist(id: String) {
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
    }
'''
new_select = '''    fun selectPlaylist(id: String) {
        val p = _ui.value.playlists.firstOrNull { it.id == id } ?: return
        prefs.activePlaylistId = id
        back.clear()
        m3uCache.clear()
        xtreamLibraryCache.clear()
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
            details = emptyMap(),
            detailLoading = emptySet(),
            contentFilterKind = null,
            favorites = emptyList(),
            continueWatching = emptyList(),
            recentlyWatched = emptyList(),
            error = ""
        ) }
        refreshCollections()
    }
'''
if old_select not in s:
    raise SystemExit("selectPlaylist full-reset anchor missing")
s = s.replace(old_select, new_select, 1)

old_m3u = '''    private suspend fun m3uResult(p: PlaylistProfile): M3uParser.Result {
        return m3uCache[p.id] ?: M3uParser.download(p.originalUrl).also { m3uCache[p.id] = it }
    }

    private fun loadCategories(kind: MediaKind) {
'''
new_m3u = '''    private suspend fun m3uResult(p: PlaylistProfile): M3uParser.Result {
        return m3uCache[p.id] ?: M3uParser.download(p.originalUrl).also { m3uCache[p.id] = it }
    }

    private fun xtreamLibrary(profile: PlaylistProfile, kind: MediaKind): List<MediaEntry> {
        val key = "${profile.id}|${kind.name}"
        xtreamLibraryCache[key]?.let { return it }
        val loaded = XtreamClient(profile).entries(kind).map { entry -> entry.copy(sourceProfileId = profile.id) }
        xtreamLibraryCache[key] = loaded
        return loaded
    }

    private fun loadCategories(kind: MediaKind) {
'''
if old_m3u not in s:
    raise SystemExit("xtreamLibrary helper anchor missing")
s = s.replace(old_m3u, new_m3u, 1)

old_catalog = '''        viewModelScope.launch {
            val rows = runCatching {
                withContext(Dispatchers.IO) {
                    coroutineScope {
                        categories.take(12).map { category ->
                            async {
                                category.id to runCatching { XtreamClient(profile).entries(kind, category.id).map { it.copy(sourceProfileId = profile.id) }.take(24) }.getOrDefault(emptyList())
                            }
                        }.awaitAll().filter { it.second.isNotEmpty() }.toMap()
                    }
                }
            }.getOrDefault(emptyMap())
            if (_ui.value.contentFilterKind == kind && _ui.value.active?.id == profile.id) set { it.copy(catalogRows = rows, catalogRowsLoading = false) }
        }
'''
new_catalog = '''        viewModelScope.launch {
            val rows = runCatching {
                withContext(Dispatchers.IO) {
                    val all = xtreamLibrary(profile, kind)
                    categories.take(12).mapNotNull { category ->
                        val row = if (category.id == "__all__") {
                            all.take(24)
                        } else {
                            all.asSequence().filter { entry -> entry.categoryId == category.id }.take(24).toList()
                        }
                        if (row.isEmpty()) null else category.id to row
                    }.toMap()
                }
            }.getOrDefault(emptyMap())
            if (_ui.value.contentFilterKind == kind && _ui.value.active?.id == profile.id) set { it.copy(catalogRows = rows, catalogRowsLoading = false) }
        }
'''
if old_catalog not in s:
    raise SystemExit("catalog multi-request anchor missing")
s = s.replace(old_catalog, new_catalog, 1)

old_items = '''                    if (p.type == PlaylistType.XTREAM) {
                        XtreamClient(p).entries(kind, cat)
                    } else {
                        m3uResult(p).entries.filter { it.categoryId == cat }
                    }
'''
new_items = '''                    if (p.type == PlaylistType.XTREAM) {
                        if (kind == MediaKind.MOVIE || kind == MediaKind.SERIES) {
                            val all = xtreamLibrary(p, kind)
                            if (cat == "__all__") all else all.filter { entry -> entry.categoryId == cat }
                        } else {
                            XtreamClient(p).entries(kind, cat)
                        }
                    } else {
                        m3uResult(p).entries.filter { it.categoryId == cat }
                    }
'''
if old_items not in s:
    raise SystemExit("loadItems Xtream anchor missing")
s = s.replace(old_items, new_items, 1)

old_details_profile = '''        val profile = state.active ?: return
        if (profile.type != PlaylistType.XTREAM) return
'''
new_details_profile = '''        val profile = state.playlists.firstOrNull { it.id == item.sourceProfileId } ?: state.active ?: return
        if (profile.type != PlaylistType.XTREAM) return
'''
if old_details_profile not in s:
    raise SystemExit("details source profile anchor missing")
s = s.replace(old_details_profile, new_details_profile, 1)

old_details_publish = '''            val enriched = runCatching {
                withContext(Dispatchers.IO) { XtreamClient(profile).details(item) }
            }.getOrNull()
            set {
                it.copy(
                    details = if (enriched != null) it.details + (key to enriched) else it.details,
                    detailLoading = it.detailLoading - key
                )
            }
'''
new_details_publish = '''            val enriched = runCatching {
                withContext(Dispatchers.IO) { XtreamClient(profile).details(item) }
            }.getOrNull()
            if (_ui.value.active?.id != profile.id) {
                set { it.copy(detailLoading = it.detailLoading - key) }
                return@launch
            }
            set {
                it.copy(
                    details = if (enriched != null) it.details + (key to enriched.copy(sourceProfileId = profile.id)) else it.details,
                    detailLoading = it.detailLoading - key
                )
            }
'''
if old_details_publish not in s:
    raise SystemExit("details stale publish anchor missing")
s = s.replace(old_details_publish, new_details_publish, 1)

vm.write_text(s)

# Sanity.
checks = [
    (gradle, 'versionName = "0.6.4.7"'),
    (gradle, 'versionCode = 610'),
    (vm, 'private val xtreamLibraryCache = java.util.concurrent.ConcurrentHashMap<String, List<MediaEntry>>()'),
    (vm, 'private fun xtreamLibrary(profile: PlaylistProfile, kind: MediaKind)'),
    (vm, 'xtreamLibraryCache.clear()'),
    (vm, 'refreshCollections()'),
    (vm, 'contentFilterKind = null'),
    (vm, 'val all = xtreamLibrary(profile, kind)'),
    (vm, 'all.asSequence().filter { entry -> entry.categoryId == category.id }.take(24).toList()'),
    (vm, 'if (kind == MediaKind.MOVIE || kind == MediaKind.SERIES)'),
    (vm, 'state.playlists.firstOrNull { it.id == item.sourceProfileId }'),
    (vm, 'if (_ui.value.active?.id != profile.id)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix7 marker {marker} in {path}")

print("Android v0.6.4.7 playlist-isolated VOD/series catalog hotfix applied")
