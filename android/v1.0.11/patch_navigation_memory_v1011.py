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

# HOME
home = java / "ui/V083Home.kt"
h = home.read_text()
if 'val homeMenuKey = "home"' not in h:
    h = h.replace(
        '    val firstFocus = remember { FocusRequester() }\n',
        '    val firstFocus = remember { FocusRequester() }\n'
        '    val homeMenuKey = "home"\n'
        '    val rememberedHomeItem = V111MenuMemory.id(homeMenuKey)\n',
        1,
    )
h = h.replace(
    '''    LaunchedEffect(isTv) {
        if (isTv) {
            delay(80L)
            runCatching { firstFocus.requestFocus() }
        }
    }
''',
    '''    LaunchedEffect(isTv, rememberedHomeItem) {
        if (isTv && rememberedHomeItem.isBlank()) {
            delay(80L)
            runCatching { firstFocus.requestFocus() }
        }
    }
''',
    1,
)
old_home_mod = '''                                    modifier = Modifier.weight(1f)
                                        .fillMaxHeight()
                                        .then(
                                            if (index == 0) Modifier.focusRequester(firstFocus)
                                            else Modifier
                                        ),
'''
new_home_mod = '''                                    modifier = Modifier.weight(1f)
                                        .fillMaxHeight()
                                        .then(
                                            if (index == 0 && rememberedHomeItem.isBlank()) {
                                                Modifier.focusRequester(firstFocus)
                                            } else Modifier
                                        )
                                        .then(
                                            v111RememberFocus(
                                                menuKey = homeMenuKey,
                                                itemId = tile.title,
                                                index = index,
                                                enabled = isTv
                                            )
                                        ),
'''
if old_home_mod not in h:
    raise SystemExit("V083 home tile modifier anchor missing")
h = h.replace(old_home_mod, new_home_mod, 1)
home.write_text(h)

# SEARCH + FAVORITES
screens35 = java / "ui/V035Screens.kt"
s35 = screens35.read_text()

search_new = r'''@Composable
fun V035SearchScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val kind = u.contentFilterKind
    val menuKey = "search:" + (kind?.name ?: "all")
    var query by remember(menuKey) { mutableStateOf(V111MenuMemory.text(menuKey + ":query")) }
    val legacyFireTvKeyboard = remember { isTv && v110NeedsLegacyFireTvKeyboard() }
    var tvKeyboardOpen by remember(legacyFireTvKeyboard) { mutableStateOf(false) }
    val listState = v111RememberLazyListState(menuKey)
    BackHandler { vm.back() }

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
                    V111MenuMemory.rememberText(menuKey + ":query", it)
                    vm.search(it)
                },
                label = { Text("Suchen") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
                    .padding(horizontal = if (isTv) 70.dp else 14.dp, vertical = 9.dp)
            )
        }

        StatusLine35(u.loading, u.error, accent)
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize()
                .padding(horizontal = if (isTv) 70.dp else 12.dp),
            contentPadding = PaddingValues(bottom = 24.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            itemsIndexed(u.searchResults, key = { _, item -> item.resumeKey }) { index, item ->
                SearchOrFavoriteRow35(
                    vm = vm,
                    item = item,
                    accent = accent,
                    isTv = isTv,
                    modifier = v111RememberFocus(menuKey, item.resumeKey, index, enabled = isTv)
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
                V111MenuMemory.rememberText(menuKey + ":query", it)
                vm.search(it)
            },
            onSubmit = {
                query = it
                V111MenuMemory.rememberText(menuKey + ":query", it)
                vm.search(it)
                tvKeyboardOpen = false
            }
        )
    }
}'''
start,end = function_span(s35, "fun V035SearchScreen(")
s35 = s35[:start] + search_new + s35[end:]

favorites_new = r'''@Composable
fun V035FavoritesScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val kind = u.contentFilterKind
    val filtered = if (kind == null) u.favorites else u.favorites.filter { matchesKind35(it, kind) }
    val menuKey = "favorites:" + (kind?.name ?: "all")
    val listState = v111RememberLazyListState(menuKey)
    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            "${kind?.let { sectionTitle35(it) + " · " }.orEmpty()}FAVORITEN",
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
                modifier = Modifier.fillMaxSize()
                    .padding(horizontal = if (isTv) 70.dp else 12.dp, vertical = 8.dp),
                contentPadding = PaddingValues(bottom = 24.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                itemsIndexed(filtered, key = { _, item -> item.resumeKey }) { index, item ->
                    SearchOrFavoriteRow35(
                        vm = vm,
                        item = item,
                        accent = accent,
                        isTv = isTv,
                        modifier = v111RememberFocus(menuKey, item.resumeKey, index, enabled = isTv)
                    )
                }
            }
        }
    }
}'''
start,end = function_span(s35, "fun V035FavoritesScreen(")
s35 = s35[:start] + favorites_new + s35[end:]

row_new = r'''@Composable
private fun SearchOrFavoriteRow35(
    vm: MainViewModel,
    item: MediaEntry,
    accent: Color,
    isTv: Boolean,
    modifier: Modifier = Modifier
) {
    val u by vm.ui.collectAsState()
    if (item.kind == MediaKind.LIVE) {
        LiveChannelRow(item, "Live TV", accent, modifier) { vm.play(item) }
    } else {
        LaunchedEffect(item.resumeKey) { vm.ensureDetails(item) }
        val detail = u.details[item.resumeKey] ?: item
        MediaInfoRow(detail, u.detailLoading.contains(item.resumeKey), accent, isTv, modifier) {
            if (item.kind == MediaKind.SERIES) vm.navigate(Screen.Episodes(detail)) else vm.play(detail)
        }
    }
}'''
start,end = function_span(s35, "private fun SearchOrFavoriteRow35(")
s35 = s35[:start] + row_new + s35[end:]
screens35.write_text(s35)

# THEMES
themes = java / "ui/V079Themes.kt"
t = themes.read_text()
if "import androidx.compose.foundation.lazy.itemsIndexed\n" not in t:
    t = t.replace(
        "import androidx.compose.foundation.lazy.items\n",
        "import androidx.compose.foundation.lazy.items\nimport androidx.compose.foundation.lazy.itemsIndexed\n",
        1,
    )
t = t.replace(
    '''                    items(selected.themes, key = { it.id }) { theme ->
                        V099ThemePreview(
                            vm, theme, theme.id == u.themeId, isTv,
                            onClick = { vm.selectTheme(theme.id) }
                        )
                    }
''',
    '''                    itemsIndexed(selected.themes, key = { _, theme -> theme.id }) { index, theme ->
                        V099ThemePreview(
                            vm, theme, theme.id == u.themeId, isTv,
                            modifier = v111RememberFocus(
                                "themes:${selected.group.id}",
                                theme.id,
                                index,
                                enabled = isTv
                            ),
                            onClick = { vm.selectTheme(theme.id) }
                        )
                    }
''',
    1,
)
t = t.replace(
    '''                        V099CategoryCard(item, isTv, accent) { selectedGroupId = item.group.id }
''',
    '''                        V099CategoryCard(
                            item, isTv, accent,
                            modifier = v111RememberFocus(
                                "themes:categories",
                                item.group.id,
                                categories.indexOf(item),
                                enabled = isTv
                            )
                        ) { selectedGroupId = item.group.id }
''',
)
t = t.replace(
    '''private fun V099CategoryCard(item: V099Category, isTv: Boolean, accent: Color, onClick: () -> Unit) {''',
    '''private fun V099CategoryCard(
    item: V099Category,
    isTv: Boolean,
    accent: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {''',
    1,
)
t = t.replace(
    '''    Box(
        Modifier.fillMaxWidth().height(if (isTv) 108.dp else 88.dp)''',
    '''    Box(
        modifier.fillMaxWidth().height(if (isTv) 108.dp else 88.dp)''',
    1,
)
t = t.replace(
    '''private fun V099ThemePreview(vm: MainViewModel, theme: ThemeInfo, active: Boolean,
                             isTv: Boolean, onClick: () -> Unit) {''',
    '''private fun V099ThemePreview(
    vm: MainViewModel,
    theme: ThemeInfo,
    active: Boolean,
    isTv: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {''',
    1,
)
needle = '''    Box(
        Modifier.fillMaxWidth().height(if (isTv) 172.dp else 133.dp)'''
if needle not in t:
    raise SystemExit("V099 theme preview modifier anchor missing")
t = t.replace(
    needle,
    '''    Box(
        modifier.fillMaxWidth().height(if (isTv) 172.dp else 133.dp)''',
    1,
)
themes.write_text(t)

# MEDIATHEK
parity = java / "ui/ParityScreens.kt"
p = parity.read_text()
if "import androidx.compose.foundation.lazy.itemsIndexed\n" not in p:
    p = p.replace(
        "import androidx.compose.foundation.lazy.items\n",
        "import androidx.compose.foundation.lazy.items\nimport androidx.compose.foundation.lazy.itemsIndexed\n",
        1,
    )
if "itemsIndexed as gridItemsIndexed" not in p:
    p = p.replace(
        "import androidx.compose.foundation.lazy.grid.items as gridItems\n",
        "import androidx.compose.foundation.lazy.grid.items as gridItems\n"
        "import androidx.compose.foundation.lazy.grid.itemsIndexed as gridItemsIndexed\n",
        1,
    )
p = p.replace(
    '''fun ParityMediathekHomeScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    BackHandler { vm.back() }''',
    '''fun ParityMediathekHomeScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val gridState = v111RememberLazyGridState("mediathek:countries")
    BackHandler { vm.back() }''',
    1,
)
p = p.replace(
    '''        LazyVerticalGrid(
            columns = GridCells.Fixed(if (isTv) 3 else 2),''',
    '''        LazyVerticalGrid(
            state = gridState,
            columns = GridCells.Fixed(if (isTv) 3 else 2),''',
    1,
)
p = p.replace(
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
p = p.replace(
    '''    val providers = remember(countryId) { MediathekClient.providers(countryId) }
    BackHandler { vm.back() }''',
    '''    val providers = remember(countryId) { MediathekClient.providers(countryId) }
    val menuKey = "mediathek:providers:" + countryId
    val listState = v111RememberLazyListState(menuKey)
    BackHandler { vm.back() }''',
    1,
)
p = p.replace(
    '''        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal = if (isTv) 70.dp else 14.dp, vertical = 12.dp),''',
    '''        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(horizontal = if (isTv) 70.dp else 14.dp, vertical = 12.dp),''',
    1,
)
p = p.replace(
    '''            items(providers, key = { it.id }) { provider ->
                ParityProviderRow(provider, accent) { vm.navigate(ParityMediathekList(provider.id)) }
''',
    '''            itemsIndexed(providers, key = { _, provider -> provider.id }) { index, provider ->
                ParityProviderRow(
                    provider,
                    accent,
                    modifier = v111RememberFocus(menuKey, provider.id, index, enabled = isTv)
                ) { vm.navigate(ParityMediathekList(provider.id)) }
''',
    1,
)
p = p.replace(
    '''private fun ParityDirectoryCard(title: String, meta: String, info: String, accent: Color, onClick: () -> Unit) {''',
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
p = p.replace(
    '''    Column(
        Modifier.heightIn(min = 150.dp).onFocusChanged''',
    '''    Column(
        modifier.heightIn(min = 150.dp).onFocusChanged''',
    1,
)
p = p.replace(
    '''private fun ParityProviderRow(provider: MediathekClient.Provider, accent: Color, onClick: () -> Unit) {''',
    '''private fun ParityProviderRow(
    provider: MediathekClient.Provider,
    accent: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {''',
    1,
)
p = p.replace(
    '''    Row(
        Modifier.fillMaxWidth().onFocusChanged''',
    '''    Row(
        modifier.fillMaxWidth().onFocusChanged''',
    1,
)
parity.write_text(p)

# CATEGORY SETTINGS
category_settings = java / "ui/V101CategorySettings.kt"
cs = category_settings.read_text()
cs = cs.replace(
    '''    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {''',
    '''    val listState = v111RememberLazyListState("category-settings")
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {''',
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
for title, item_id, index in [
    ("Live-TV-Kategorien", "live", 0),
    ("Film-Kategorien", "movie", 1),
    ("Serien-Kategorien", "series", 2),
]:
    marker = f'                    "{title}",'
    pos = cs.find(marker)
    if pos < 0:
        raise SystemExit(f"category settings marker missing: {title}")
    click = cs.find("                    onClick =", pos)
    if click < 0:
        raise SystemExit(f"category settings onClick missing: {title}")
    cs = cs[:click] + (
        f'                    modifier = v111RememberFocus("category-settings", "{item_id}", {index}, enabled = isTv),\n'
    ) + cs[click:]
category_settings.write_text(cs)

# WEATHER CARD modifier
weather = java / "ui/V081WeatherSettings.kt"
w = weather.read_text()
w = w.replace(
    'fun V081WeatherSettingsCard(accent: androidx.compose.ui.graphics.Color) {',
    'fun V081WeatherSettingsCard(accent: androidx.compose.ui.graphics.Color, modifier: Modifier = Modifier) {',
    1,
)
w = w.replace(
    '''        accent = accent,
        onClick = { showDialog = true }
''',
    '''        accent = accent,
        modifier = modifier,
        onClick = { showDialog = true }
''',
    1,
)
weather.write_text(w)

# SETTINGS + PLAYLISTS
screens = java / "ui/Screens.kt"
ss = screens.read_text()

settings_new = r'''@Composable
fun SettingsScreen(vm:MainViewModel,accent:Color){
    val u by vm.ui.collectAsState()
    val isTv = v111IsTvDevice()
    val menuKey = "settings"
    val listState = v111RememberLazyListState(menuKey)
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar("EINSTELLUNGEN",R.drawable.brand_header,{vm.back()})
        LazyColumn(
            state = listState,
            modifier = Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ){
            item{
                FocusCard(
                    "Skin / Design",
                    u.themeCatalog?.themes?.get(u.themeId)?.label.orEmpty(),
                    R.drawable.icon_settings,
                    accent=accent,
                    modifier=v111RememberFocus(menuKey,"themes",0,enabled=isTv),
                    onClick={vm.navigate(Screen.Themes)}
                )
            }
            item{
                FocusCard(
                    "Playlists verwalten",
                    "${u.playlists.size} gespeichert",
                    R.drawable.icon_playlist,
                    accent=accent,
                    modifier=v111RememberFocus(menuKey,"playlists",1,enabled=isTv),
                    onClick={vm.navigate(Screen.Playlists)}
                )
            }
            item{
                FocusCard(
                    "Kategorien verwalten",
                    "Live TV · Filme · Serien",
                    R.drawable.icon_live,
                    accent=accent,
                    modifier=v111RememberFocus(menuKey,"categories",2,enabled=isTv),
                    onClick={vm.navigate(Screen.CategorySettings)}
                )
            }
            item{
                V081WeatherSettingsCard(
                    accent,
                    modifier=v111RememberFocus(menuKey,"weather",3,enabled=isTv)
                )
            }
            item{
                FocusCard(
                    "PC-Verwaltung im Browser",
                    if(u.webAdminRunning)"Aktiv · ${u.webAdminUrl}" else "Xtream/M3U bequem am Computer eingeben",
                    R.drawable.icon_playlist,
                    accent=accent,
                    modifier=v111RememberFocus(menuKey,"webadmin",4,enabled=isTv),
                    onClick={vm.navigate(Screen.WebAdmin)}
                )
            }
            item{
                FocusCard(
                    "Bevorzugte Audiosprache",
                    lang(u.preferredAudioLanguage),
                    R.drawable.icon_settings,
                    accent=accent,
                    modifier=v111RememberFocus(menuKey,"audio",5,enabled=isTv),
                    onClick={vm.setAudioLanguage(nextAudio(u.preferredAudioLanguage))}
                )
            }
            item{
                FocusCard(
                    "Bevorzugte Untertitelsprache",
                    lang(u.preferredSubtitleLanguage),
                    R.drawable.icon_settings,
                    accent=accent,
                    modifier=v111RememberFocus(menuKey,"subtitle",6,enabled=isTv),
                    onClick={vm.setSubtitleLanguage(nextSub(u.preferredSubtitleLanguage))}
                )
            }
            item{
                GlassPanel(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(20.dp)){
                        Text("Android v1.0.11",fontWeight=FontWeight.Bold)
                        Text("SmartTube · globale Fokus-/Positionswiederherstellung",color=Color.White.copy(.62f))
                    }
                }
            }
        }
    }
}'''
start,end = function_span(ss, "fun SettingsScreen(")
ss = ss[:start] + settings_new + ss[end:]

playlists_new = r'''@Composable
fun PlaylistsScreen(vm:MainViewModel,accent:Color){
    val u by vm.ui.collectAsState()
    val isTv = v111IsTvDevice()
    val menuKey = "playlists"
    val listState = v111RememberLazyListState(menuKey)
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar(
            "PLAYLISTS",
            R.drawable.brand_header,
            {vm.back()},
            actions={
                TextButton(onClick={vm.navigate(Screen.AddPlaylist)}){
                    Text("+ Hinzufügen",color=accent)
                }
            }
        )
        LazyColumn(
            state=listState,
            modifier=Modifier.fillMaxSize().padding(16.dp),
            verticalArrangement=Arrangement.spacedBy(10.dp)
        ){
            itemsIndexed(u.playlists,key={_,p->p.id}){index,p->
                GlassPanel(Modifier.fillMaxWidth()){
                    Row(Modifier.padding(16.dp),verticalAlignment=Alignment.CenterVertically){
                        Column(Modifier.weight(1f)){
                            Text(p.name,fontWeight=FontWeight.Bold)
                            Text(p.type.name,color=Color.White.copy(.6f))
                        }
                        Button(
                            onClick={vm.selectPlaylist(p.id)},
                            modifier=v111RememberFocus(menuKey,p.id,index,enabled=isTv),
                            colors=ButtonDefaults.buttonColors(containerColor=accent),
                            shape=MaterialTheme.shapes.small
                        ){
                            Text(if(p.id==u.active?.id)"Aktiv" else "Wählen")
                        }
                        TextButton(onClick={vm.removePlaylist(p.id)}){
                            Text("Löschen",color=Color(0xFFFF8585))
                        }
                    }
                }
            }
        }
    }
}'''
start,end = function_span(ss, "fun PlaylistsScreen(")
ss = ss[:start] + playlists_new + ss[end:]
screens.write_text(ss)

checks = [
    (home, 'v111RememberFocus('),
    (screens35, 'V111MenuMemory.rememberText(menuKey + ":query"'),
    (themes, '"themes:categories"'),
    (parity, '"mediathek:countries"'),
    (category_settings, '"category-settings"'),
    (weather, 'modifier: Modifier = Modifier'),
    (screens, 'Text("Android v1.0.11"'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing 1.0.11 navigation marker {marker} in {path}")

print("Android 1.0.11 global Back focus/scroll restoration applied across main menus")
