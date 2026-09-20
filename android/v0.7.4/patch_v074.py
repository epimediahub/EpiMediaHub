#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace missing: {signature}")
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise SystemExit(f"closing brace missing: {signature}")


def replace_function(path: Path, signature: str, replacement: str):
    text = path.read_text()
    start, end = function_span(text, signature)
    path.write_text(text[:start] + replacement.rstrip() + text[end:])


# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
build = root / "app/build.gradle.kts"
s = build.read_text()
require_once(s, 'versionCode = 703', 'v0.7.3 versionCode')
require_once(s, 'versionName = "0.7.3"', 'v0.7.3 versionName')
build.write_text(
    s.replace('versionCode = 703', 'versionCode = 704', 1)
     .replace('versionName = "0.7.3"', 'versionName = "0.7.4"', 1)
)

home = java / "ui/V070Home.kt"
s = home.read_text()
if "0.7.3" not in s:
    raise SystemExit("visible v0.7.3 marker missing")
home.write_text(s.replace("0.7.3", "0.7.4"))

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.3", "EpiMediaHub-Android/0.7.4"))


# ---------------------------------------------------------------------------
# Live-TV zapping: use the same direction mapping in ExoPlayer and LibVLC,
# accept D-pad plus real CHANNEL/PAGE keys, and identify the prepared Xtream
# channel by stable ID instead of the mutable resume key.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
old_index = '        val currentIndex = channels.indexOfFirst { it.resumeKey == item.resumeKey }'
if s.count(old_index) != 2:
    raise SystemExit(f"live current-index anchors: expected 2, found {s.count(old_index)}")
new_index = '''        val currentIndex = channels.indexOfFirst { candidate ->
            candidate.id == item.id &&
                (candidate.sourceProfileId == item.sourceProfileId ||
                    candidate.sourceProfileId.isBlank() ||
                    item.sourceProfileId.isBlank())
        }'''
s = s.replace(old_index, new_index)

old_vlc_keys = '''                    KeyEvent.KEYCODE_DPAD_UP -> switchLiveBy(-1)
                    KeyEvent.KEYCODE_DPAD_DOWN -> switchLiveBy(1)
                    KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT -> true'''
new_vlc_keys = '''                    KeyEvent.KEYCODE_DPAD_UP,
                    KeyEvent.KEYCODE_CHANNEL_UP,
                    KeyEvent.KEYCODE_PAGE_UP -> switchLiveBy(1)
                    KeyEvent.KEYCODE_DPAD_DOWN,
                    KeyEvent.KEYCODE_CHANNEL_DOWN,
                    KeyEvent.KEYCODE_PAGE_DOWN -> switchLiveBy(-1)
                    KeyEvent.KEYCODE_DPAD_LEFT -> switchLiveBy(-1)
                    KeyEvent.KEYCODE_DPAD_RIGHT -> switchLiveBy(1)'''
require_once(s, old_vlc_keys, 'LibVLC live keys')
s = s.replace(old_vlc_keys, new_vlc_keys, 1)

require_once(
    s,
    'KeyEvent.KEYCODE_DPAD_LEFT -> if (item.kind == MediaKind.LIVE) true else if (isEpisode && prev) previousEpisode() else { seekBy(-10_000L); true }',
    'Exo live left key',
)
s = s.replace(
    'KeyEvent.KEYCODE_DPAD_LEFT -> if (item.kind == MediaKind.LIVE) true else if (isEpisode && prev) previousEpisode() else { seekBy(-10_000L); true }',
    'KeyEvent.KEYCODE_DPAD_LEFT -> if (item.kind == MediaKind.LIVE) switchLiveBy(-1) else if (isEpisode && prev) previousEpisode() else { seekBy(-10_000L); true }',
    1,
)
require_once(
    s,
    'KeyEvent.KEYCODE_DPAD_RIGHT -> if (item.kind == MediaKind.LIVE) true else if (isEpisode && next) nextEpisode() else { seekBy(10_000L); true }',
    'Exo live right key',
)
s = s.replace(
    'KeyEvent.KEYCODE_DPAD_RIGHT -> if (item.kind == MediaKind.LIVE) true else if (isEpisode && next) nextEpisode() else { seekBy(10_000L); true }',
    'KeyEvent.KEYCODE_DPAD_RIGHT -> if (item.kind == MediaKind.LIVE) switchLiveBy(1) else if (isEpisode && next) nextEpisode() else { seekBy(10_000L); true }',
    1,
)

old_exo_ud = '''                    KeyEvent.KEYCODE_DPAD_UP -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(1) else true}else{controls=true;false}
                    KeyEvent.KEYCODE_DPAD_DOWN -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(-1) else true}else{controls=false;false}'''
new_exo_ud = '''                    KeyEvent.KEYCODE_DPAD_UP -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(1) else true}else{controls=true;false}
                    KeyEvent.KEYCODE_DPAD_DOWN -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(-1) else true}else{controls=false;false}'''
require_once(s, old_exo_ud, 'Exo live up/down keys')
player.write_text(s.replace(old_exo_ud, new_exo_ud, 1))


# ---------------------------------------------------------------------------
# Live-TV category overview: load rows for Live too and remember the selected
# category without entering the old single-category screen.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
anchor = '    fun browserSelectedId(kind: MediaKind, categoryId: String): String = browseSelections[browseKey(kind, categoryId)].orEmpty()\n'
require_once(s, anchor, 'browser selected ID')
s = s.replace(
    anchor,
    anchor +
    '''\n    fun rememberLibraryCategory(kind: MediaKind, categoryId: String) {
        if (categoryId.isBlank()) lastLibraryCategory.remove(libraryKey(kind))
        else lastLibraryCategory[libraryKey(kind)] = categoryId
    }

    fun rememberedLibraryCategory(kind: MediaKind): String =
        lastLibraryCategory[libraryKey(kind)].orEmpty()
''',
    1,
)
old_loading = 'catalogRowsLoading = kind == MediaKind.MOVIE || kind == MediaKind.SERIES'
require_once(s, old_loading, 'catalogRows loading kinds')
s = s.replace(
    old_loading,
    'catalogRowsLoading = kind == MediaKind.MOVIE || kind == MediaKind.SERIES || kind == MediaKind.LIVE',
    1,
)
vm.write_text(s)

replace_function(
    vm,
    '    private fun loadCatalogRows(kind: MediaKind, categories: List<MediaCategory>)',
    r'''    private fun loadCatalogRows(kind: MediaKind, categories: List<MediaCategory>) {
        if (kind != MediaKind.MOVIE && kind != MediaKind.SERIES && kind != MediaKind.LIVE) return
        val profile = _ui.value.active ?: return
        if (categories.isEmpty()) {
            set { it.copy(catalogRowsLoading = false) }
            return
        }
        if (profile.type != PlaylistType.XTREAM && kind != MediaKind.LIVE) {
            set { it.copy(catalogRowsLoading = false) }
            return
        }
        viewModelScope.launch {
            val rows = runCatching {
                withContext(Dispatchers.IO) {
                    val all = when {
                        profile.type == PlaylistType.XTREAM ->
                            xtreamLibrary(profile, kind)
                        kind == MediaKind.LIVE ->
                            m3uResult(profile).entries.map { entry -> entry.copy(sourceProfileId = profile.id) }
                        else -> emptyList()
                    }
                    val byCategory = all.groupBy { entry -> entry.categoryId }
                    categories.mapNotNull { category ->
                        val row = if (category.id == "__all__") {
                            all
                        } else {
                            byCategory[category.id].orEmpty()
                        }
                        if (row.isEmpty()) null else category.id to row
                    }.toMap()
                }
            }.getOrDefault(emptyMap())
            if (_ui.value.contentFilterKind == kind && _ui.value.active?.id == profile.id) {
                set { it.copy(catalogRows = rows, catalogRowsLoading = false) }
            }
        }
    }'''
)


# Route Live TV through the same category-overview surface as movies/series.
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
old_route = 'is Screen.Categories -> if (s.kind == de.epimediahub.app.model.MediaKind.MOVIE || s.kind == de.epimediahub.app.model.MediaKind.SERIES) V060CinematicHubScreen(vm, s.kind, accent, isTv) else CategoryScreen(vm, s.kind, accent, isTv)'
require_once(s, old_route, 'category route')
app.write_text(
    s.replace(
        old_route,
        'is Screen.Categories -> if (s.kind == de.epimediahub.app.model.MediaKind.MOVIE || s.kind == de.epimediahub.app.model.MediaKind.SERIES || s.kind == de.epimediahub.app.model.MediaKind.LIVE) V060CinematicHubScreen(vm, s.kind, accent, isTv) else CategoryScreen(vm, s.kind, accent, isTv)',
        1,
    )
)


# Cinematic category hub now also handles Live TV and restores rail focus.
hub = java / "ui/V060CinematicHub.kt"
s = hub.read_text()
if 'import androidx.compose.ui.focus.FocusRequester\n' not in s:
    require_once(s, 'import androidx.compose.ui.focus.onFocusChanged\n', 'focus import anchor')
    s = s.replace(
        'import androidx.compose.ui.focus.onFocusChanged\n',
        'import androidx.compose.ui.focus.FocusRequester\nimport androidx.compose.ui.focus.focusRequester\nimport androidx.compose.ui.focus.onFocusChanged\n',
        1,
    )
if 'import kotlinx.coroutines.delay\n' not in s:
    require_once(s, 'import kotlinx.coroutines.launch\n', 'coroutine import anchor')
    s = s.replace('import kotlinx.coroutines.launch\n', 'import kotlinx.coroutines.delay\nimport kotlinx.coroutines.launch\n', 1)

old_recent = '    val recent = u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }'
require_once(s, old_recent, 'recent row')
s = s.replace(
    old_recent,
    '    val recent = if (kind == MediaKind.LIVE) emptyList() else u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }',
    1,
)
old_continue = '    val continueItems = u.continueWatching.filter { it.media.kind == kind || (kind == MediaKind.SERIES && it.media.kind == MediaKind.EPISODE) }'
require_once(s, old_continue, 'continue row')
s = s.replace(
    old_continue,
    '    val continueItems = if (kind == MediaKind.LIVE) emptyList() else u.continueWatching.filter { it.media.kind == kind || (kind == MediaKind.SERIES && it.media.kind == MediaKind.EPISODE) }',
    1,
)
require_once(s, '    val hero = recent.firstOrNull() ?: firstCatalog', 'hero')
s = s.replace(
    '    val hero = recent.firstOrNull() ?: firstCatalog',
    '    val hero = if (kind == MediaKind.LIVE) null else recent.firstOrNull() ?: firstCatalog',
    1,
)
require_once(s, '    var selectedCategoryId by remember(kind, u.active?.id) { mutableStateOf("") }', 'selected category state')
s = s.replace(
    '    var selectedCategoryId by remember(kind, u.active?.id) { mutableStateOf("") }',
    '    var selectedCategoryId by remember(kind, u.active?.id) { mutableStateOf(vm.rememberedLibraryCategory(kind)) }',
    1,
)

category_index_anchor = '''    val categoryStartIndex =
        (if (hero != null) 1 else 0) +
        1 +
        (if (continueItems.isNotEmpty()) 1 else 0) +
        (if (recent.isNotEmpty()) 1 else 0)

    BackHandler { vm.back() }'''
require_once(s, category_index_anchor, 'category start index')
s = s.replace(
    category_index_anchor,
    '''    val categoryStartIndex =
        (if (hero != null) 1 else 0) +
        1 +
        (if (continueItems.isNotEmpty()) 1 else 0) +
        (if (recent.isNotEmpty()) 1 else 0)

    LaunchedEffect(visibleCategories, selectedCategoryId, categoryStartIndex) {
        if (selectedCategoryId.isNotBlank()) {
            val index = visibleCategories.indexOfFirst { it.id == selectedCategoryId }
            if (index >= 0) contentState.scrollToItem(categoryStartIndex + index)
        }
    }

    BackHandler { vm.back() }''',
    1,
)

require_once(s, '        EpiTopBar(if (kind == MediaKind.MOVIE) "FILME" else "SERIEN", R.drawable.brand_header, { vm.back() })', 'hub title')
s = s.replace(
    '        EpiTopBar(if (kind == MediaKind.MOVIE) "FILME" else "SERIEN", R.drawable.brand_header, { vm.back() })',
    '        EpiTopBar(when (kind) { MediaKind.LIVE -> "LIVE TV"; MediaKind.MOVIE -> "FILME"; else -> "SERIEN" }, R.drawable.brand_header, { vm.back() })',
    1,
)
require_once(s, '                        if (kind == MediaKind.MOVIE) "Filme werden geladen …" else "Serien werden geladen …",', 'loading label')
s = s.replace(
    '                        if (kind == MediaKind.MOVIE) "Filme werden geladen …" else "Serien werden geladen …",',
    '                        when (kind) { MediaKind.LIVE -> "Sender werden geladen …"; MediaKind.MOVIE -> "Filme werden geladen …"; else -> "Serien werden geladen …" },',
    1,
)

old_overview = '''                        onOverview = {
                            selectedCategoryId = ""
                            scope.launch { contentState.animateScrollToItem(0) }
                        },
                        onCategory = { index, category ->
                            selectedCategoryId = category.id
                            scope.launch { contentState.animateScrollToItem(categoryStartIndex + index) }
                        }'''
new_overview = '''                        onOverview = {
                            selectedCategoryId = ""
                            vm.rememberLibraryCategory(kind, "")
                            scope.launch { contentState.animateScrollToItem(0) }
                        },
                        onCategory = { index, category ->
                            selectedCategoryId = category.id
                            vm.rememberLibraryCategory(kind, category.id)
                            scope.launch { contentState.animateScrollToItem(categoryStartIndex + index) }
                        }'''
require_once(s, old_overview, 'category rail callbacks')
s = s.replace(old_overview, new_overview, 1)

old_actions = '''                            V060Action("Suchen", Icons.Default.Search, accent) { vm.openKindSearch(kind) }
                            V060Action("Zuletzt gesehen", Icons.Default.History, accent) { vm.navigate(Screen.RecentlyWatched) }
                            V060Action("Favoriten", Icons.Default.FavoriteBorder, accent) { vm.openKindFavorites(kind) }'''
new_actions = '''                            V060Action("Suchen", Icons.Default.Search, accent) { vm.openKindSearch(kind) }
                            if (kind != MediaKind.LIVE) {
                                V060Action("Zuletzt gesehen", Icons.Default.History, accent) { vm.navigate(Screen.RecentlyWatched) }
                            }
                            V060Action("Favoriten", Icons.Default.FavoriteBorder, accent) { vm.openKindFavorites(kind) }'''
require_once(s, old_actions, 'hub actions')
s = s.replace(old_actions, new_actions, 1)

old_categories = '''                    items(visibleCategories, key = { "category:" + it.id }) { category ->
                        V060PosterRow(category.name.uppercase(), u.catalogRows[category.id].orEmpty(), accent, isTv, onMore = { vm.switchLibraryCategory(kind, category) }) {
                            vm.navigate(Screen.Details(it))
                        }
                    }
                    if (visibleCategories.isNotEmpty()) {
                        item(key = "all-categories") {
                            TextButton(
                                onClick = { vm.switchLibraryCategory(kind, visibleCategories.first()) },
                                modifier = Modifier.padding(horizontal = if (isTv) 28.dp else 14.dp)
                            ) {
                                Text("Alle Kategorien öffnen", color = accent, fontWeight = FontWeight.Black)
                            }
                        }
                    }'''
new_categories = '''                    items(visibleCategories, key = { "category:" + it.id }) { category ->
                        val entries = u.catalogRows[category.id].orEmpty()
                        val openCategory: (() -> Unit)? =
                            if (kind == MediaKind.LIVE) null else ({ vm.switchLibraryCategory(kind, category) })
                        V060PosterRow(category.name.uppercase(), entries, accent, isTv, onMore = openCategory) { item ->
                            if (kind == MediaKind.LIVE) {
                                vm.rememberLibraryCategory(kind, category.id)
                                vm.play(item, entries)
                            } else {
                                vm.navigate(Screen.Details(item))
                            }
                        }
                    }
                    if (kind != MediaKind.LIVE && visibleCategories.isNotEmpty()) {
                        item(key = "all-categories") {
                            TextButton(
                                onClick = { vm.switchLibraryCategory(kind, visibleCategories.first()) },
                                modifier = Modifier.padding(horizontal = if (isTv) 28.dp else 14.dp)
                            ) {
                                Text("Alle Kategorien öffnen", color = accent, fontWeight = FontWeight.Black)
                            }
                        }
                    }'''
require_once(s, old_categories, 'category rows')
s = s.replace(old_categories, new_categories, 1)

hub.write_text(s)

replace_function(
    hub,
    'private fun V071CategoryRail(',
    r'''private fun V071CategoryRail(
    categories: List<MediaCategory>,
    selectedId: String,
    accent: Color,
    onOverview: () -> Unit,
    onCategory: (Int, MediaCategory) -> Unit
) {
    val railState = rememberLazyListState()
    val selectedFocus = remember(selectedId, categories.size) { FocusRequester() }
    val selectedIndex = if (selectedId.isBlank()) 0 else {
        val index = categories.indexOfFirst { it.id == selectedId }
        if (index >= 0) index + 1 else 0
    }

    LaunchedEffect(selectedId, categories.size) {
        railState.scrollToItem(selectedIndex.coerceAtLeast(0))
        delay(90)
        runCatching { selectedFocus.requestFocus() }
    }

    Column(
        Modifier.width(226.dp).fillMaxHeight().background(Color.Black.copy(.18f))
            .padding(start = 16.dp, end = 12.dp, top = 10.dp, bottom = 14.dp)
    ) {
        Text("KATEGORIEN", color = Color.White.copy(.55f), fontSize = 11.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp))
        LazyColumn(
            Modifier.fillMaxSize(),
            state = railState,
            verticalArrangement = Arrangement.spacedBy(5.dp),
            contentPadding = PaddingValues(bottom = 18.dp)
        ) {
            item(key = "rail-overview") {
                V071CategoryRailItem(
                    title = "Übersicht",
                    selected = selectedId.isBlank(),
                    accent = accent,
                    modifier = if (selectedId.isBlank()) Modifier.focusRequester(selectedFocus) else Modifier,
                    onClick = onOverview
                )
            }
            itemsIndexed(categories, key = { _, category -> "rail:" + category.id }) { index, category ->
                val selected = selectedId == category.id
                V071CategoryRailItem(
                    title = category.name,
                    selected = selected,
                    accent = accent,
                    modifier = if (selected) Modifier.focusRequester(selectedFocus) else Modifier,
                    onClick = { onCategory(index, category) }
                )
            }
        }
    }
}'''
)

replace_function(
    hub,
    'private fun V071CategoryRailItem(',
    r'''private fun V071CategoryRailItem(
    title: String,
    selected: Boolean,
    accent: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(11.dp)
    Surface(
        modifier = modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
        color = when {
            focused -> accent.copy(.28f)
            selected -> accent.copy(.16f)
            else -> Color.Transparent
        },
        shape = shape,
        border = BorderStroke(
            if (focused) 2.dp else 1.dp,
            when {
                focused -> Color.White
                selected -> accent.copy(.75f)
                else -> Color.Transparent
            }
        )
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 11.dp, vertical = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(
                Modifier.width(if (selected || focused) 4.dp else 2.dp).height(24.dp)
                    .background(if (selected || focused) accent else Color.White.copy(.18f), RoundedCornerShape(99.dp))
            )
            Spacer(Modifier.width(9.dp))
            Text(
                title,
                color = if (focused || selected) Color.White else Color.White.copy(.72f),
                fontSize = 13.sp,
                fontWeight = if (focused || selected) FontWeight.Black else FontWeight.SemiBold,
                maxLines = 2,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}'''
)

s = hub.read_text()
old_row_sig = 'private fun V060PosterRow(title: String, entries: List<MediaEntry>, accent: Color, isTv: Boolean, onMore: () -> Unit, onItem: (MediaEntry) -> Unit) {'
require_once(s, old_row_sig, 'poster row signature')
s = s.replace(
    old_row_sig,
    'private fun V060PosterRow(title: String, entries: List<MediaEntry>, accent: Color, isTv: Boolean, onMore: (() -> Unit)?, onItem: (MediaEntry) -> Unit) {',
    1,
)
old_more = '            TextButton(onClick = onMore) { Text("ALLE", color = accent, fontWeight = FontWeight.Black, fontSize = 12.sp) }'
require_once(s, old_more, 'poster row more')
s = s.replace(
    old_more,
    '            if (onMore != null) TextButton(onClick = onMore) { Text("ALLE", color = accent, fontWeight = FontWeight.Black, fontSize = 12.sp) }',
    1,
)
hub.write_text(s)


# ---------------------------------------------------------------------------
# Updater: compare the own-domain manifest with the GitHub release so a stale
# or temporarily unavailable domain manifest cannot block an update. APK
# downloads also retry the matching release asset.
# ---------------------------------------------------------------------------
updates = java / "data/UpdateManager.kt"
s = updates.read_text()
require_once(s, '    private const val MANIFEST_URL = "https://download.epimediahub.com/android/latest.json"\n', 'manifest URL')
s = s.replace(
    '    private const val MANIFEST_URL = "https://download.epimediahub.com/android/latest.json"\n',
    '    private const val MANIFEST_URL = "https://download.epimediahub.com/android/latest.json"\n'
    '    private const val RELEASE_API_URL = "https://api.github.com/repos/epimediahub/EpiMediaHub/releases/tags/v0.7.0-test"\n'
    '    private const val GITHUB_RELEASE_BASE = "https://github.com/epimediahub/EpiMediaHub/releases/download/v0.7.0-test"\n',
    1,
)
updates.write_text(s)

replace_function(
    updates,
    '    private fun fetchLatestInfo()',
    r'''    private fun fetchLatestInfo(): AppUpdateInfo {
        val manifest = runCatching {
            parseManifest(JSONObject(fetchJson(MANIFEST_URL)))
        }.getOrNull()
        val release = runCatching {
            parseRelease(JSONObject(fetchJson(RELEASE_API_URL, "application/vnd.github+json")))
        }.getOrNull()

        return when {
            manifest != null && release != null ->
                if (isNewer(release.version, manifest.version)) release else manifest
            manifest != null -> manifest
            release != null -> release
            else -> error("Update-Informationen konnten nicht geladen werden.")
        }
    }

    private fun githubFallbackUrl(primary: String): String {
        val clean = primary.substringBefore('?')
        val name = clean.substringAfterLast('/').takeIf { it.endsWith(".apk", ignoreCase = true) }
            ?: STABLE_APK_NAME
        return "$GITHUB_RELEASE_BASE/$name"
    }'''
)

replace_function(
    updates,
    '    suspend fun downloadApk(context: Context, info: AppUpdateInfo)',
    r'''    suspend fun downloadApk(context: Context, info: AppUpdateInfo): File = withContext(Dispatchers.IO) {
        val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: error("Download-Verzeichnis ist nicht verfügbar.")
        if (!dir.exists() && !dir.mkdirs()) error("Download-Verzeichnis konnte nicht erstellt werden.")

        val safeVersion = info.version.ifBlank { "latest" }.replace(Regex("[^A-Za-z0-9._-]"), "_")
        val target = File(dir, "EpiMediaHub-$safeVersion.apk")
        val partial = File(dir, "EpiMediaHub-$safeVersion.apk.part")

        if (target.isFile && target.length() >= 1024 * 1024) {
            if (info.sha256.isBlank() || sha256(target).equals(info.sha256, ignoreCase = true)) {
                return@withContext target
            }
            target.delete()
        }

        val primary = info.url.ifBlank { STABLE_APK_URL }
        val candidates = listOf(primary, githubFallbackUrl(primary)).distinct()
        var lastFailure: Throwable? = null

        for (candidate in candidates) {
            partial.delete()
            try {
                val conn = openGet(
                    candidate,
                    accept = "application/vnd.android.package-archive",
                    readTimeoutMs = 180000
                )
                try {
                    val code = conn.responseCode
                    if (code !in 200..299) error("Update-Download fehlgeschlagen (HTTP $code).")
                    val digest = MessageDigest.getInstance("SHA-256")
                    conn.inputStream.use { input ->
                        partial.outputStream().buffered(256 * 1024).use { output ->
                            val buffer = ByteArray(256 * 1024)
                            while (true) {
                                val read = input.read(buffer)
                                if (read <= 0) break
                                output.write(buffer, 0, read)
                                digest.update(buffer, 0, read)
                            }
                            output.flush()
                        }
                    }
                    if (partial.length() < 1024 * 1024) {
                        val length = partial.length()
                        partial.delete()
                        error("Update-Download ist unvollständig ($length Bytes).")
                    }
                    val actual = digest.digest().joinToString("") { "%02x".format(it) }
                    if (info.sha256.isNotBlank() && !actual.equals(info.sha256, ignoreCase = true)) {
                        partial.delete()
                        error("Sicherheitsprüfung fehlgeschlagen: SHA-256 stimmt nicht.")
                    }
                    if (target.exists()) target.delete()
                    if (!partial.renameTo(target)) {
                        partial.copyTo(target, overwrite = true)
                        partial.delete()
                    }
                    if (!target.isFile || target.length() < 1024 * 1024) {
                        target.delete()
                        error("Update-Datei konnte nicht gespeichert werden.")
                    }
                    return@withContext target
                } finally {
                    conn.disconnect()
                }
            } catch (failure: Throwable) {
                lastFailure = failure
                partial.delete()
            }
        }

        throw lastFailure ?: IllegalStateException("Update-Download fehlgeschlagen.")
    }'''
)


checks = [
    (build, 'versionName = "0.7.4"'),
    (build, 'versionCode = 704'),
    (player, 'KeyEvent.KEYCODE_CHANNEL_UP'),
    (player, 'if (item.kind == MediaKind.LIVE) switchLiveBy(1) else nextEpisode()'),
    (player, 'KeyEvent.KEYCODE_DPAD_RIGHT -> switchLiveBy(1)'),
    (vm, 'fun rememberedLibraryCategory(kind: MediaKind)'),
    (vm, 'kind == MediaKind.SERIES || kind == MediaKind.LIVE'),
    (hub, 'MediaKind.LIVE -> "LIVE TV"'),
    (hub, 'vm.rememberLibraryCategory(kind, category.id)'),
    (hub, 'Modifier.focusRequester(selectedFocus)'),
    (app, 's.kind == de.epimediahub.app.model.MediaKind.LIVE'),
    (updates, 'private const val RELEASE_API_URL'),
    (updates, 'private fun githubFallbackUrl(primary: String)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.4 marker {marker} in {path}")

print("Android v0.7.4 Live TV navigation, category overview and resilient updater applied")
