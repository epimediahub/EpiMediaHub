#!/usr/bin/env python3
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

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

def replace_function(path: Path, signature: str, replacement: str):
    text = path.read_text()
    start, end = function_span(text, signature)
    path.write_text(text[:start] + replacement + text[end:])

def ensure_import(path: Path, line: str):
    text = path.read_text()
    if line in text:
        return
    anchor = "package de.epimediahub.app.ui\n\n"
    if anchor not in text:
        raise SystemExit(f"package import anchor missing in {path}")
    path.write_text(text.replace(anchor, anchor + line + "\n", 1))

home = java / "ui/V083Home.kt"
hs = home.read_text()
hs = hs.replace('    val firstFocus = remember { FocusRequester() }\n', '')
hs = hs.replace('''    LaunchedEffect(isTv) {
        if (isTv) {
            delay(80L)
            runCatching { firstFocus.requestFocus() }
        }
    }

''', '')
hs = hs.replace(
'''                                    modifier = Modifier.weight(1f)
                                        .fillMaxHeight()
                                        .then(
                                            if (index == 0) Modifier.focusRequester(firstFocus)
                                            else Modifier
                                        ),
                                    onClick = tile.open
''',
'''                                    modifier = Modifier.weight(1f).fillMaxHeight(),
                                    onClick = tile.open
'''
)
hs = hs.replace(
'''    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
''',
'''    var focused by remember { mutableStateOf(false) }
    val focusRequester = remember { FocusRequester() }
    val homeMemoryKey = "home"
    LaunchedEffect(isTv, title) {
        if (isTv) {
            val remembered = V111MenuMemory.id(homeMemoryKey)
            if (remembered == title || (remembered.isBlank() && title == "LIVE TV")) {
                delay(90L)
                runCatching { focusRequester.requestFocus() }
            }
        }
    }
    val scale by animateFloatAsState(
''',
1
)
hs = hs.replace(
'''            .shadow(shadow, shape)
            .onFocusChanged { focused = it.isFocused }
''',
'''            .shadow(shadow, shape)
            .focusRequester(focusRequester)
            .onFocusChanged {
                focused = it.isFocused
                if (it.isFocused) V111MenuMemory.remember(homeMemoryKey, 0, title)
            }
''',
1
)
home.write_text(hs)

screens = java / "ui/V035Screens.kt"

replace_function(
    screens,
    "fun V035CategoryScreen(",
    r'''fun V035CategoryScreen(vm: MainViewModel, kind: MediaKind, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val memoryKey = "categories:" + u.active?.id.orEmpty() + ":" + kind.name
    val listState = rememberLazyListState()
    val focusRequester = remember { FocusRequester() }
    val rememberedIndex = V111MenuMemory.index(memoryKey)
    BackHandler { vm.back() }

    LaunchedEffect(u.categories.size, isTv) {
        if (isTv && u.categories.isNotEmpty()) {
            val index = rememberedIndex.coerceIn(0, u.categories.lastIndex)
            listState.scrollToItem(index)
            delay(70L)
            runCatching { focusRequester.requestFocus() }
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(sectionTitle35(kind), R.drawable.brand_header, { vm.back() })
        StatusLine35(u.loading, u.error, accent)
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(
                horizontal = if (isTv) 72.dp else 14.dp,
                vertical = 8.dp
            ),
            verticalArrangement = Arrangement.spacedBy(7.dp),
            contentPadding = PaddingValues(bottom = 24.dp)
        ) {
            itemsIndexed(u.categories, key = { _, it -> it.id }) { index, category ->
                CategoryListRow(
                    category.name,
                    accent,
                    modifier = Modifier
                        .then(if (isTv && index == rememberedIndex) Modifier.focusRequester(focusRequester) else Modifier)
                        .onFocusChanged {
                            if (it.isFocused) V111MenuMemory.remember(memoryKey, index, category.id)
                        }
                ) {
                    V111MenuMemory.remember(memoryKey, index, category.id)
                    vm.switchLibraryCategory(kind, category)
                }
            }
        }
    }
}'''
)

replace_function(
    screens,
    "fun V035SearchScreen(",
    r'''fun V035SearchScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val kind = u.contentFilterKind
    val memoryKey = "search:" + u.active?.id.orEmpty() + ":" + kind?.name.orEmpty()
    var query by remember { mutableStateOf(V111MenuMemory.text(memoryKey + ":query")) }
    val legacyFireTvKeyboard = remember { isTv && v110NeedsLegacyFireTvKeyboard() }
    var tvKeyboardOpen by remember(legacyFireTvKeyboard) { mutableStateOf(legacyFireTvKeyboard && query.isBlank()) }
    val listState = rememberLazyListState()
    val focusRequester = remember { FocusRequester() }
    val rememberedIndex = V111MenuMemory.index(memoryKey)
    BackHandler { vm.back() }

    LaunchedEffect(Unit) {
        if (query.length >= 2 && u.searchResults.isEmpty()) vm.search(query)
    }

    LaunchedEffect(u.searchResults.size, isTv) {
        if (isTv && u.searchResults.isNotEmpty()) {
            val index = rememberedIndex.coerceIn(0, u.searchResults.lastIndex)
            listState.scrollToItem(index)
            delay(70L)
            runCatching { focusRequester.requestFocus() }
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            (kind?.let { sectionTitle35(it) + " · " }.orEmpty()) + "SUCHE",
            R.drawable.brand_header,
            { vm.back() }
        )

        if (legacyFireTvKeyboard) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = 70.dp, vertical = 9.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    modifier = Modifier.weight(1f).height(56.dp),
                    color = Color(0xFF111821),
                    shape = RoundedCornerShape(12.dp),
                    border = androidx.compose.foundation.BorderStroke(
                        1.dp,
                        if (query.isBlank()) Color.White.copy(.15f) else accent.copy(.65f)
                    )
                ) {
                    Row(
                        Modifier.fillMaxSize().padding(horizontal = 14.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Icon(Icons.Default.Search, null, tint = accent)
                        Spacer(Modifier.width(10.dp))
                        Text(
                            query.ifBlank { "Suchbegriff eingeben …" },
                            color = if (query.isBlank()) Color.White.copy(.45f) else Color.White,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1
                        )
                    }
                }
                Button(
                    onClick = { tvKeyboardOpen = true },
                    colors = ButtonDefaults.buttonColors(containerColor = accent)
                ) { Text("Tastatur", fontWeight = FontWeight.Black) }
            }
        } else {
            OutlinedTextField(
                value = query,
                onValueChange = {
                    query = it
                    V111MenuMemory.rememberText(memoryKey + ":query", it)
                    vm.search(it)
                },
                label = { Text("Suchen") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth().padding(
                    horizontal = if (isTv) 70.dp else 14.dp,
                    vertical = 9.dp
                )
            )
        }

        StatusLine35(u.loading, u.error, accent)
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(horizontal = if (isTv) 70.dp else 12.dp),
            contentPadding = PaddingValues(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            itemsIndexed(u.searchResults, key = { _, it -> it.resumeKey }) { index, item ->
                SearchOrFavoriteRow35(
                    vm, item, accent, isTv,
                    modifier = Modifier
                        .then(if (isTv && index == rememberedIndex) Modifier.focusRequester(focusRequester) else Modifier)
                        .onFocusChanged {
                            if (it.isFocused) V111MenuMemory.remember(memoryKey, index, item.resumeKey)
                        }
                )
            }
        }
    }

    if (legacyFireTvKeyboard && tvKeyboardOpen) {
        V110TvKeyboardDialog(
            title = (kind?.let { sectionTitle35(it) + " · " }.orEmpty()) + "Suche",
            initialValue = query,
            accent = accent,
            onDismiss = { tvKeyboardOpen = false },
            onValueChange = {
                query = it
                V111MenuMemory.rememberText(memoryKey + ":query", it)
                vm.search(it)
            },
            onSubmit = {
                query = it
                V111MenuMemory.rememberText(memoryKey + ":query", it)
                vm.search(it)
                tvKeyboardOpen = false
            }
        )
    }
}'''
)

replace_function(
    screens,
    "fun V035FavoritesScreen(",
    r'''fun V035FavoritesScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val kind = u.contentFilterKind
    val filtered = if (kind == null) u.favorites else u.favorites.filter { matchesKind35(it, kind) }
    val memoryKey = "favorites:" + u.active?.id.orEmpty() + ":" + kind?.name.orEmpty()
    val listState = rememberLazyListState()
    val focusRequester = remember { FocusRequester() }
    val rememberedIndex = V111MenuMemory.index(memoryKey)
    BackHandler { vm.back() }

    LaunchedEffect(filtered.size, isTv) {
        if (isTv && filtered.isNotEmpty()) {
            val index = rememberedIndex.coerceIn(0, filtered.lastIndex)
            listState.scrollToItem(index)
            delay(70L)
            runCatching { focusRequester.requestFocus() }
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            (kind?.let { sectionTitle35(it) + " · " }.orEmpty()) + "FAVORITEN",
            R.drawable.brand_header,
            { vm.back() }
        )
        if (filtered.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Noch keine Favoriten in diesem Bereich", color = Color.White.copy(.65f), fontSize = 18.sp)
            }
        } else {
            LazyColumn(
                state = listState,
                modifier = Modifier.fillMaxSize().padding(
                    horizontal = if (isTv) 70.dp else 12.dp,
                    vertical = 8.dp
                ),
                contentPadding = PaddingValues(bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                itemsIndexed(filtered, key = { _, it -> it.resumeKey }) { index, item ->
                    SearchOrFavoriteRow35(
                        vm, item, accent, isTv,
                        modifier = Modifier
                            .then(if (isTv && index == rememberedIndex) Modifier.focusRequester(focusRequester) else Modifier)
                            .onFocusChanged {
                                if (it.isFocused) V111MenuMemory.remember(memoryKey, index, item.resumeKey)
                            }
                    )
                }
            }
        }
    }
}'''
)

replace_function(
    screens,
    "private fun SearchOrFavoriteRow35(",
    r'''private fun SearchOrFavoriteRow35(
    vm: MainViewModel,
    item: MediaEntry,
    accent: Color,
    isTv: Boolean,
    modifier: Modifier = Modifier
) {
    val u by vm.ui.collectAsState()
    if (item.kind == MediaKind.LIVE) {
        LiveChannelRow(item, "Live TV", accent, modifier = modifier) { vm.play(item) }
    } else {
        LaunchedEffect(item.resumeKey) { vm.ensureDetails(item) }
        val detail = u.details[item.resumeKey] ?: item
        MediaInfoRow(
            detail,
            u.detailLoading.contains(item.resumeKey),
            accent,
            isTv,
            modifier = modifier
        ) {
            if (item.kind == MediaKind.SERIES) vm.navigate(Screen.Episodes(detail)) else vm.play(detail)
        }
    }
}'''
)

# ---------------------------------------------------------------------------
# Settings and playlists: preserve the focused row when returning from nested
# screens such as Designs, Dashboard, Add Playlist, etc.
# ---------------------------------------------------------------------------
legacy_screens = java / "ui/Screens.kt"
for imp in (
    "import androidx.compose.foundation.lazy.rememberLazyListState",
    "import androidx.compose.foundation.lazy.itemsIndexed",
    "import androidx.compose.ui.focus.FocusRequester",
    "import androidx.compose.ui.focus.focusRequester",
    "import androidx.compose.ui.focus.onFocusChanged",
    "import kotlinx.coroutines.delay",
):
    ensure_import(legacy_screens, imp)

replace_function(
    legacy_screens,
    "fun SettingsScreen(",
    r'''fun SettingsScreen(vm: MainViewModel, accent: Color) {
    val u by vm.ui.collectAsState()
    val memoryKey = "settings"
    val state = rememberLazyListState()
    val requesters = remember { List(8) { FocusRequester() } }
    val remembered = V111MenuMemory.index(memoryKey).coerceIn(0, 7)
    BackHandler { vm.back() }

    LaunchedEffect(Unit) {
        state.scrollToItem(remembered)
        delay(70L)
        runCatching { requesters[remembered].requestFocus() }
    }

    fun rememberedModifier(index: Int): Modifier =
        Modifier
            .then(if (index == remembered) Modifier.focusRequester(requesters[index]) else Modifier)
            .onFocusChanged {
                if (it.isFocused) V111MenuMemory.remember(memoryKey, index, index.toString())
            }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("EINSTELLUNGEN", R.drawable.brand_header, { vm.back() })
        LazyColumn(
            state = state,
            modifier = Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item {
                FocusCard(
                    "Skin / Design",
                    u.themeCatalog?.themes?.get(u.themeId)?.label.orEmpty(),
                    R.drawable.icon_settings,
                    accent = accent,
                    modifier = rememberedModifier(0),
                    onClick = { vm.navigate(Screen.Themes) }
                )
            }
            item {
                FocusCard(
                    "Playlists verwalten",
                    u.playlists.size.toString() + " gespeichert",
                    R.drawable.icon_playlist,
                    accent = accent,
                    modifier = rememberedModifier(1),
                    onClick = { vm.navigate(Screen.Playlists) }
                )
            }
            item {
                FocusCard(
                    "Kategorien verwalten",
                    "Live TV · Filme · Serien",
                    R.drawable.icon_live,
                    accent = accent,
                    modifier = rememberedModifier(2),
                    onClick = { vm.navigate(Screen.CategorySettings) }
                )
            }
            item {
                V081WeatherSettingsCard(
                    accent,
                    modifier = rememberedModifier(3)
                )
            }
            item {
                FocusCard(
                    "Gerät & Dashboard",
                    if (u.webAdminRunning) "Aktiv · " + u.webAdminUrl else "Kopplung · Websetup · Fernverwaltung",
                    R.drawable.icon_playlist,
                    accent = accent,
                    modifier = rememberedModifier(4),
                    onClick = { vm.navigate(Screen.WebAdmin) }
                )
            }
            item {
                FocusCard(
                    "Bevorzugte Audiosprache",
                    lang(u.preferredAudioLanguage),
                    R.drawable.icon_settings,
                    accent = accent,
                    modifier = rememberedModifier(5),
                    onClick = { vm.setAudioLanguage(nextAudio(u.preferredAudioLanguage)) }
                )
            }
            item {
                FocusCard(
                    "Bevorzugte Untertitelsprache",
                    lang(u.preferredSubtitleLanguage),
                    R.drawable.icon_settings,
                    accent = accent,
                    modifier = rememberedModifier(6),
                    onClick = { vm.setSubtitleLanguage(nextSub(u.preferredSubtitleLanguage)) }
                )
            }
            item {
                FocusCard(
                    "App-Update",
                    "Automatisch alle 24h oder jetzt manuell prüfen",
                    R.drawable.icon_settings,
                    accent = accent,
                    modifier = rememberedModifier(7),
                    onClick = { vm.navigate(Screen.Updates) }
                )
            }
            item {
                GlassPanel(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        Text("Android v1.0.11", fontWeight = FontWeight.Bold)
                        Text(
                            "SmartTube · Fokus-Wiederherstellung · Dashboard",
                            color = Color.White.copy(.62f)
                        )
                    }
                }
            }
        }
    }
}'''
)

replace_function(
    legacy_screens,
    "fun PlaylistsScreen(",
    r'''fun PlaylistsScreen(vm: MainViewModel, accent: Color) {
    val u by vm.ui.collectAsState()
    val memoryKey = "playlists"
    val state = rememberLazyListState()
    val remembered = V111MenuMemory.index(memoryKey)
    val focusRequester = remember { FocusRequester() }
    BackHandler { vm.back() }

    LaunchedEffect(u.playlists.size) {
        if (u.playlists.isNotEmpty()) {
            val index = remembered.coerceIn(0, u.playlists.lastIndex)
            state.scrollToItem(index)
            delay(70L)
            runCatching { focusRequester.requestFocus() }
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            "PLAYLISTS",
            R.drawable.brand_header,
            { vm.back() },
            actions = {
                TextButton(onClick = { vm.navigate(Screen.AddPlaylist) }) {
                    Text("+ Hinzufügen", color = accent)
                }
            }
        )
        LazyColumn(
            state = state,
            modifier = Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp)
        ) {
            itemsIndexed(u.playlists, key = { _, it -> it.id }) { index, playlist ->
                GlassPanel(Modifier.fillMaxWidth()) {
                    Row(
                        Modifier.padding(16.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(Modifier.weight(1f)) {
                            Text(playlist.name, fontWeight = FontWeight.Bold)
                            Text(playlist.type.name, color = Color.White.copy(.6f))
                        }
                        Button(
                            onClick = {
                                V111MenuMemory.remember(memoryKey, index, playlist.id)
                                vm.selectPlaylist(playlist.id)
                            },
                            modifier = Modifier
                                .then(
                                    if (index == remembered) Modifier.focusRequester(focusRequester)
                                    else Modifier
                                )
                                .onFocusChanged {
                                    if (it.isFocused) {
                                        V111MenuMemory.remember(memoryKey, index, playlist.id)
                                    }
                                },
                            colors = ButtonDefaults.buttonColors(containerColor = accent),
                            shape = MaterialTheme.shapes.small
                        ) {
                            Text(if (playlist.id == u.active?.id) "Aktiv" else "Wählen")
                        }
                        TextButton(onClick = { vm.removePlaylist(playlist.id) }) {
                            Text("Löschen", color = Color(0xFFFF8585))
                        }
                    }
                }
            }
        }
    }
}'''
)


# Movies / Series: remember both the vertical shelf and the exact horizontal
# poster inside every shelf. This prevents Back from jumping to the hero/top.
hub = java / "ui/V060CinematicHub.kt"
h = hub.read_text()
if "import androidx.compose.foundation.lazy.itemsIndexed" not in h:
    h = h.replace(
        "import androidx.compose.foundation.lazy.items\n",
        "import androidx.compose.foundation.lazy.items\nimport androidx.compose.foundation.lazy.itemsIndexed\n",
        1,
    )

if "val contentState = rememberLazyListState()" in h:
    h = h.replace(
        "    val contentState = rememberLazyListState()\n",
        '    val contentState = v111RememberLazyListState("cinematic-main:" + kind.name)\n',
        1,
    )

a, b = function_span(h, "private fun V060PosterRow(")
row = h[a:b]
if "v111RememberLazyListState(rowKey)" not in row:
    row = row.replace(
        "    Column(Modifier.fillMaxWidth()) {\n",
        '    val rowKey = "cinematic-row:" + title\n'
        '    val rowState = v111RememberLazyListState(rowKey)\n'
        "    Column(Modifier.fillMaxWidth()) {\n",
        1,
    )
    row = row.replace(
        "        LazyRow(\n",
        "        LazyRow(\n            state = rowState,\n",
        1,
    )

    current_items = '''            items(entries, key = { it.resumeKey }) { item ->
                V060Poster(item, accent, isTv, infoByKey[item.resumeKey].orEmpty()) { onItem(item) }
            }'''
    replacement_items = '''            itemsIndexed(entries, key = { _, item -> item.resumeKey }) { index, item ->
                V060Poster(
                    item,
                    accent,
                    isTv,
                    infoByKey[item.resumeKey].orEmpty(),
                    rememberedFocus = v111RememberFocus(rowKey, item.resumeKey, index, isTv, scopeKey = "cinematic:" + (if (item.kind == MediaKind.EPISODE) MediaKind.SERIES.name else item.kind.name))
                ) { onItem(item) }
            }'''
    if current_items in row:
        row = row.replace(current_items, replacement_items, 1)
    else:
        old_items = next((anchor for anchor in (
            '            items(entries, key = { it.resumeKey }) { item -> V060Poster(item, accent, isTv) { onItem(item) } }',
            '            items(entries.take(24), key = { it.resumeKey }) { item -> V060Poster(item, accent, isTv) { onItem(item) } }',
        ) if anchor in row), None)
        if old_items is not None:
            row = row.replace(
                old_items,
                '''            itemsIndexed(entries, key = { _, item -> item.resumeKey }) { index, item ->
                V060Poster(
                    item,
                    accent,
                    isTv,
                    rememberedFocus = v111RememberFocus(rowKey, item.resumeKey, index, isTv, scopeKey = "cinematic:" + (if (item.kind == MediaKind.EPISODE) MediaKind.SERIES.name else item.kind.name))
                ) { onItem(item) }
            }''',
                1,
            )
        else:
            raise SystemExit("cinematic poster row items anchor missing")
h = h[:a] + row + h[b:]

a, b = function_span(h, "private fun V060Poster(")
poster = h[a:b]
if "rememberedFocus: Modifier = Modifier" not in poster:
    current_sig = "private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, infoText: String = \"\", onClick: () -> Unit)"
    old_sig = "private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, onClick: () -> Unit)"
    if current_sig in poster:
        poster = poster.replace(
            current_sig,
            "private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, infoText: String = \"\", rememberedFocus: Modifier = Modifier, onClick: () -> Unit)",
            1,
        )
    elif old_sig in poster:
        poster = poster.replace(
            old_sig,
            "private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, rememberedFocus: Modifier = Modifier, onClick: () -> Unit)",
            1,
        )
    else:
        raise SystemExit("cinematic poster signature anchor missing")

    shadow_anchor = ".shadow(shadow, shape)\n            .onFocusChanged"
    if shadow_anchor not in poster:
        raise SystemExit("cinematic poster focus anchor missing")
    poster = poster.replace(
        shadow_anchor,
        ".shadow(shadow, shape)\n            .then(rememberedFocus)\n            .onFocusChanged",
        1,
    )
h = h[:a] + poster + h[b:]
hub.write_text(h)

# Live TV already remembered IDs; also persist the two rail scroll states.
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

# Theme browser: remember which category was open and the scroll position in
# both overview and category detail views.
themes_path = java / "ui/V079Themes.kt"
theme_text = themes_path.read_text()
theme_text = theme_text.replace(
    '    var selectedGroupId by rememberSaveable { mutableStateOf<String?>(null) }\n',
    '''    var selectedGroupId by rememberSaveable {
        mutableStateOf<String?>(V111MenuMemory.text("themes-group").takeIf { it.isNotBlank() })
    }
''',
    1,
)
theme_text = theme_text.replace(
    'selectedGroupId = item.group.id',
    'selectedGroupId = item.group.id; V111MenuMemory.rememberText("themes-group", item.group.id)',
)
detail_anchor = '''                LazyColumn(
                    Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
                    contentPadding = PaddingValues(top = 8.dp, bottom = 28.dp),
'''
if detail_anchor in theme_text:
    theme_text = theme_text.replace(
        detail_anchor,
        '''                LazyColumn(
                    state = v111RememberLazyListState("themes-detail:" + selected.group.id),
                    modifier = Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
                    contentPadding = PaddingValues(top = 8.dp, bottom = 28.dp),
''',
        1,
    )
overview_anchor = '''                LazyColumn(
                    Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
                    contentPadding = PaddingValues(top = 9.dp, bottom = 30.dp),
'''
if overview_anchor in theme_text:
    theme_text = theme_text.replace(
        overview_anchor,
        '''                LazyColumn(
                    state = v111RememberLazyListState("themes-overview"),
                    modifier = Modifier.fillMaxSize().padding(horizontal = if (isTv) 44.dp else 12.dp),
                    contentPadding = PaddingValues(top = 9.dp, bottom = 30.dp),
''',
        1,
    )
themes_path.write_text(theme_text)

themes = java / "ui/V079Themes.kt"
ts = themes.read_text()
if "import androidx.compose.ui.focus.focusRequester" not in ts:
    ts = ts.replace(
        "import androidx.compose.ui.focus.onFocusChanged\n",
        "import androidx.compose.ui.focus.focusRequester\nimport androidx.compose.ui.focus.onFocusChanged\n",
        1,
    )
ts = ts.replace(
'''    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.015f else 1f, label = "categoryFocus")
''',
'''    var focused by remember { mutableStateOf(false) }
    val focusRequester = remember { androidx.compose.ui.focus.FocusRequester() }
    LaunchedEffect(item.group.id) {
        if (V111MenuMemory.id("theme-categories") == item.group.id) {
            kotlinx.coroutines.delay(70L)
            runCatching { focusRequester.requestFocus() }
        }
    }
    val scale by animateFloatAsState(if (focused) 1.015f else 1f, label = "categoryFocus")
''',
1
)
ts = ts.replace(
'''            .graphicsLayer { scaleX = scale; scaleY = scale }
            .onFocusChanged { focused = it.isFocused }
            .focusable().clip(shape)
''',
'''            .graphicsLayer { scaleX = scale; scaleY = scale }
            .focusRequester(focusRequester)
            .onFocusChanged {
                focused = it.isFocused
                if (it.isFocused) V111MenuMemory.remember("theme-categories", 0, item.group.id)
            }
            .focusable().clip(shape)
''',
1
)
themes.write_text(ts)



# Series season/episode browser: remember selected season and episode-grid scroll.
if legacy_screens.exists():
    es = legacy_screens.read_text()
    if "fun EpisodesScreen(" in es:
        a, b = function_span(es, "fun EpisodesScreen(")
        fn = es[a:b]
        if 'val episodeMemoryKey = "episodes:" + series.resumeKey' not in fn:
            fn = fn.replace(
                "    val seasons = remember(orderedEpisodes) { orderedEpisodes.map { it.season }.distinct() }\n",
                '''    val seasons = remember(orderedEpisodes) { orderedEpisodes.map { it.season }.distinct() }
    val episodeMemoryKey = "episodes:" + series.resumeKey
''',
                1,
            )
            fn = fn.replace(
                "    var selectedSeason by remember(series.resumeKey, seasons) { mutableStateOf(seasons.firstOrNull()) }\n",
                '''    var selectedSeason by remember(series.resumeKey, seasons) {
        mutableStateOf(
            V111MenuMemory.text(episodeMemoryKey + ":season").toIntOrNull()
                ?.takeIf { it in seasons }
                ?: seasons.firstOrNull()
        )
    }
''',
                1,
            )
            fn = fn.replace(
                "            LazyRow(\n                modifier=Modifier.fillMaxWidth(),",
                '''            LazyRow(
                state=v111RememberLazyListState(episodeMemoryKey + ":seasons"),
                modifier=Modifier.fillMaxWidth(),''',
                1,
            )
            fn = fn.replace(
                "                        onClick={selectedSeason=season},",
                '''                        onClick={
                            selectedSeason=season
                            V111MenuMemory.rememberText(episodeMemoryKey + ":season", season.toString())
                        },''',
                1,
            )
            fn = fn.replace(
                "            LazyVerticalGrid(\n                GridCells.Fixed(if(isTv)5 else 2),",
                '''            LazyVerticalGrid(
                state=v111RememberLazyGridState(episodeMemoryKey + ":grid"),
                columns=GridCells.Fixed(if(isTv)5 else 2),''',
                1,
            )
            fn = fn.replace(
                "                Modifier.fillMaxSize().padding(horizontal=14.dp,vertical=6.dp),",
                "                modifier=Modifier.fillMaxSize().padding(horizontal=14.dp,vertical=6.dp),",
                1,
            )
        es = es[:a] + fn + es[b:]
        legacy_screens.write_text(es)

# Mediathek and secondary grids: preserve scroll position as part of the same
# global Back-navigation rule.
parity = java / "ui/ParityScreens.kt"
if parity.exists():
    ps = parity.read_text()

    if "fun ParityMediathekHomeScreen(" in ps:
        a, b = function_span(ps, "fun ParityMediathekHomeScreen(")
        fn = ps[a:b]
        if 'v111RememberLazyGridState("mediathek-countries")' not in fn:
            fn = fn.replace(
                "        LazyVerticalGrid(\n",
                '        LazyVerticalGrid(\n            state = v111RememberLazyGridState("mediathek-countries"),\n',
                1,
            )
        ps = ps[:a] + fn + ps[b:]

    if "fun ParityMediathekDirectoryScreen(" in ps:
        a, b = function_span(ps, "fun ParityMediathekDirectoryScreen(")
        fn = ps[a:b]
        if 'v111RememberLazyListState("mediathek-providers:' not in fn:
            fn = fn.replace(
                "        LazyColumn(\n            Modifier.fillMaxSize()",
                '        LazyColumn(\n            state = v111RememberLazyListState("mediathek-providers:" + countryId),\n            modifier = Modifier.fillMaxSize()',
                1,
            )
        ps = ps[:a] + fn + ps[b:]

    if "fun ParityMediathekListScreen(" in ps:
        a, b = function_span(ps, "fun ParityMediathekListScreen(")
        fn = ps[a:b]
        if 'v111RememberLazyGridState("mediathek-list:' not in fn:
            fn = fn.replace(
                "            LazyVerticalGrid(\n                columns =",
                '            LazyVerticalGrid(\n                state = v111RememberLazyGridState("mediathek-list:" + providerId),\n                columns =',
                1,
            )
        ps = ps[:a] + fn + ps[b:]

    parity.write_text(ps)

# Recently watched is a separate full-screen grid and should obey the same rule.
h = hub.read_text()
if "fun V060RecentlyWatchedScreen(" in h:
    a, b = function_span(h, "fun V060RecentlyWatchedScreen(")
    fn = h[a:b]
    if 'v111RememberLazyGridState("recently-watched")' not in fn:
        fn = fn.replace(
            "        else LazyVerticalGrid(\n            GridCells.Adaptive(if (isTv) 170.dp else 124.dp), Modifier.fillMaxSize(),",
            '        else LazyVerticalGrid(\n            state = v111RememberLazyGridState("recently-watched"),\n            columns = GridCells.Adaptive(if (isTv) 170.dp else 124.dp), modifier = Modifier.fillMaxSize(),',
            1,
        )
    h = h[:a] + fn + h[b:]
    hub.write_text(h)


# Weather card participates in Settings focus restoration.
weather = java / "ui/V081WeatherSettings.kt"
if weather.exists():
    ws = weather.read_text()
    ws = ws.replace(
        'fun V081WeatherSettingsCard(accent: androidx.compose.ui.graphics.Color) {',
        'fun V081WeatherSettingsCard(accent: androidx.compose.ui.graphics.Color, modifier: Modifier = Modifier) {',
        1,
    )
    ws = ws.replace(
        '''        accent = accent,
        onClick = { showDialog = true }
''',
        '''        accent = accent,
        modifier = modifier,
        onClick = { showDialog = true }
''',
        1,
    )
    weather.write_text(ws)

# Category manager entry screen restores the last selected media type.
category_settings = java / "ui/V101CategorySettings.kt"
if category_settings.exists():
    cs = category_settings.read_text()
    if 'val memoryKey = "category-settings"' not in cs:
        cs = cs.replace(
            '    BackHandler { vm.back() }\n',
            '    val memoryKey = "category-settings"\n'
            '    val listState = v111RememberLazyListState(memoryKey)\n'
            '    BackHandler { vm.back() }\n',
            1,
        )
        cs = cs.replace(
            '''        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(if (isTv) 20.dp else 14.dp),''',
            '''        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(if (isTv) 20.dp else 14.dp),''',
            1,
        )
        cards = [
            ("Live-TV-Kategorien", "live", 0),
            ("Film-Kategorien", "movie", 1),
            ("Serien-Kategorien", "series", 2),
        ]
        for title, item_id, index in cards:
            marker = f'                    "{title}",'
            pos = cs.find(marker)
            if pos < 0:
                raise SystemExit(f"category settings card missing: {title}")
            click = cs.find("                    onClick =", pos)
            if click < 0:
                raise SystemExit(f"category settings onClick missing: {title}")
            cs = cs[:click] + (
                f'                    modifier = v111RememberFocus(memoryKey, "{item_id}", {index}, enabled = isTv),\n'
            ) + cs[click:]
    category_settings.write_text(cs)

# Mediathek country/provider menus also restore exact focus and scroll.
parity = java / "ui/ParityScreens.kt"
if parity.exists():
    ps = parity.read_text()
    if "import androidx.compose.foundation.lazy.itemsIndexed\n" not in ps:
        ps = ps.replace(
            "import androidx.compose.foundation.lazy.items\n",
            "import androidx.compose.foundation.lazy.items\nimport androidx.compose.foundation.lazy.itemsIndexed\n",
            1,
        )
    if "itemsIndexed as gridItemsIndexed" not in ps:
        ps = ps.replace(
            "import androidx.compose.foundation.lazy.grid.items as gridItems\n",
            "import androidx.compose.foundation.lazy.grid.items as gridItems\n"
            "import androidx.compose.foundation.lazy.grid.itemsIndexed as gridItemsIndexed\n",
            1,
        )
    ps = ps.replace(
        '''fun ParityMediathekHomeScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    BackHandler { vm.back() }''',
        '''fun ParityMediathekHomeScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val gridState = v111RememberLazyGridState("mediathek:countries")
    BackHandler { vm.back() }''',
        1,
    )
    ps = ps.replace(
        '''        LazyVerticalGrid(
            columns = GridCells.Fixed(if (isTv) 3 else 2),''',
        '''        LazyVerticalGrid(
            state = gridState,
            columns = GridCells.Fixed(if (isTv) 3 else 2),''',
        1,
    )
    ps = ps.replace(
        '''            gridItems(MediathekClient.countries, key = { it.id }) { country ->
                ParityDirectoryCard(country.label, country.meta, country.info, accent) {''',
        '''            gridItemsIndexed(MediathekClient.countries, key = { _, item -> item.id }) { index, country ->
                ParityDirectoryCard(
                    country.label, country.meta, country.info, accent,
                    modifier = v111RememberFocus(
                        "mediathek:countries", country.id, index, enabled = isTv
                    )
                ) {''',
        1,
    )
    ps = ps.replace(
        '''    val providers = remember(countryId) { MediathekClient.providers(countryId) }
    BackHandler { vm.back() }''',
        '''    val providers = remember(countryId) { MediathekClient.providers(countryId) }
    val memoryKey = "mediathek:providers:" + countryId
    val providerState = v111RememberLazyListState(memoryKey)
    BackHandler { vm.back() }''',
        1,
    )
    ps = ps.replace(
        '''        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal = if (isTv) 70.dp else 14.dp, vertical = 12.dp),''',
        '''        LazyColumn(
            state = providerState,
            modifier = Modifier.fillMaxSize().padding(horizontal = if (isTv) 70.dp else 14.dp, vertical = 12.dp),''',
        1,
    )
    ps = ps.replace(
        '''            items(providers, key = { it.id }) { provider ->
                ParityProviderRow(provider, accent) { vm.navigate(ParityMediathekList(provider.id)) }
''',
        '''            itemsIndexed(providers, key = { _, provider -> provider.id }) { index, provider ->
                ParityProviderRow(
                    provider,
                    accent,
                    modifier = v111RememberFocus(memoryKey, provider.id, index, enabled = isTv)
                ) { vm.navigate(ParityMediathekList(provider.id)) }
''',
        1,
    )
    ps = ps.replace(
        'private fun ParityDirectoryCard(title: String, meta: String, info: String, accent: Color, onClick: () -> Unit) {',
        '''private fun ParityDirectoryCard(
    title: String,
    meta: String,
    info: String,
    accent: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {''',
        1,
    )
    ps = ps.replace(
        '        Modifier.heightIn(min = 150.dp).onFocusChanged',
        '        modifier.heightIn(min = 150.dp).onFocusChanged',
        1,
    )
    ps = ps.replace(
        'private fun ParityProviderRow(provider: MediathekClient.Provider, accent: Color, onClick: () -> Unit) {',
        '''private fun ParityProviderRow(
    provider: MediathekClient.Provider,
    accent: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {''',
        1,
    )
    ps = ps.replace(
        '        Modifier.fillMaxWidth().onFocusChanged',
        '        modifier.fillMaxWidth().onFocusChanged',
        1,
    )
    parity.write_text(ps)

checks = [
    (home, 'V111MenuMemory.id(homeMemoryKey)'),
    (home, 'V111MenuMemory.remember(homeMemoryKey'),
    (screens, 'memoryKey = "search:"'),
    (screens, 'itemsIndexed(u.searchResults'),
    (screens, 'itemsIndexed(filtered'),
    (themes, 'V111MenuMemory.id("theme-categories")'),
    (hub, 'v111RememberLazyListState("cinematic-main:" + kind.name)'),
    (hub, 'v111RememberLazyListState(rowKey)'),
    (live, 'v111RememberLazyListState("livetv-categories")'),
    (themes_path, 'v111RememberLazyListState("themes-overview")'),
    (parity, 'v111RememberLazyGridState("mediathek-countries")'),
    (hub, 'v111RememberLazyGridState("recently-watched")'),
    (legacy_screens, 'val memoryKey = "settings"'),
    (legacy_screens, 'val memoryKey = "playlists"'),
    (legacy_screens, 'val episodeMemoryKey = "episodes:" + series.resumeKey'),
    (legacy_screens, 'Screen.CategorySettings'),
    (weather, 'modifier: Modifier = Modifier'),
    (category_settings, 'v111RememberFocus(memoryKey'),
    (parity, '"mediathek:countries"'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing navigation memory marker {marker} in {path}")

print("Android 1.0.11 back-navigation focus memory applied across active menus")
