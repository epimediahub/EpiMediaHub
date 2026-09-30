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
        LiveChannelRow(item, "Live TV", accent, modifier) { vm.play(item) }
    } else {
        LaunchedEffect(item.resumeKey) { vm.ensureDetails(item) }
        val detail = u.details[item.resumeKey] ?: item
        MediaInfoRow(
            detail,
            u.detailLoading.contains(item.resumeKey),
            accent,
            isTv,
            modifier
        ) {
            if (item.kind == MediaKind.SERIES) vm.navigate(Screen.Episodes(detail)) else vm.play(detail)
        }
    }
}'''
)

themes = java / "ui/V079Themes.kt"
ts = themes.read_text()
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

checks = [
    (home, 'V111MenuMemory.id(homeMemoryKey)'),
    (home, 'V111MenuMemory.remember(homeMemoryKey'),
    (screens, 'memoryKey = "search:"'),
    (screens, 'itemsIndexed(u.searchResults'),
    (screens, 'itemsIndexed(filtered'),
    (themes, 'V111MenuMemory.id("theme-categories")'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing navigation memory marker {marker} in {path}")

print("Android 1.0.11 back-navigation focus memory applied across active menus")
