#!/usr/bin/env python3
from pathlib import Path
import os
import shutil

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

gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 802', 'versionCode = 803', 'versionCode')
replace_once(gradle, 'versionName = "0.8.2"', 'versionName = "0.8.3"', 'versionName')

for rel in ["ui/Screens.kt", "ui/V078DashboardPairingGate.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.8.2", "0.8.3"))

src = Path(__file__).with_name("V083Home.kt")
dst = java / "ui/V083Home.kt"
shutil.copyfile(src, dst)

screens = java / "ui/Screens.kt"
s = screens.read_text()
if "V082HomeScreen(vm,isTv,accent)" in s:
    s = s.replace("V082HomeScreen(vm,isTv,accent)", "V083HomeScreen(vm,isTv,accent)", 1)
elif "V082HomeScreen(vm, isTv, accent)" in s:
    s = s.replace("V082HomeScreen(vm, isTv, accent)", "V083HomeScreen(vm, isTv, accent)", 1)
else:
    raise SystemExit("0.8.2 home delegate anchor missing")
screens.write_text(s)

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.8.2", "EpiMediaHub-Android/0.8.3"))

hub = java / "ui/V060CinematicHub.kt"
for imp in [
    "import androidx.compose.animation.core.FastOutSlowInEasing",
    "import androidx.compose.animation.animateColorAsState",
    "import androidx.compose.animation.core.animateDpAsState",
    "import androidx.compose.animation.core.tween",
]:
    ensure_import(hub, imp)

h = hub.read_text()
double_scroll = '''    LaunchedEffect(visibleCategories, selectedCategoryId, categoryStartIndex) {
        if (selectedCategoryId.isNotBlank()) {
            val index = visibleCategories.indexOfFirst { it.id == selectedCategoryId }
            if (index >= 0) contentState.scrollToItem(categoryStartIndex + index)
        }
    }

'''
if double_scroll in h:
    h = h.replace(double_scroll, "", 1)
hub.write_text(h)

replace_function(
    hub,
    "private fun V060Action(",
    r'''private fun V060Action(title: String, icon: androidx.compose.ui.graphics.vector.ImageVector, accent: Color, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (focused) 1.022f else 1f,
        animationSpec = tween(140, easing = FastOutSlowInEasing),
        label = "hubActionScale"
    )
    val background by animateColorAsState(
        targetValue = if (focused) accent.copy(.23f) else Color(0xD9121A24),
        animationSpec = tween(140, easing = FastOutSlowInEasing),
        label = "hubActionBg"
    )
    val border by animateColorAsState(
        targetValue = if (focused) Color.White.copy(.92f) else Color.White.copy(.13f),
        animationSpec = tween(140, easing = FastOutSlowInEasing),
        label = "hubActionBorder"
    )
    Surface(
        modifier = Modifier.graphicsLayer { scaleX = scale; scaleY = scale }
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clickable(onClick = onClick),
        color = background,
        shape = RoundedCornerShape(13.dp),
        border = BorderStroke(1.dp, border)
    ) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = if (focused) Color.White else Color.White.copy(.88f), modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text(title, color = Color.White, fontWeight = FontWeight.Bold)
        }
    }
}'''
)

replace_function(
    hub,
    "private fun V060Poster(",
    r'''private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (focused) 1.035f else 1f,
        animationSpec = tween(155, easing = FastOutSlowInEasing),
        label = "posterScale"
    )
    val shadow by animateDpAsState(
        targetValue = if (focused) 14.dp else 2.dp,
        animationSpec = tween(155, easing = FastOutSlowInEasing),
        label = "posterShadow"
    )
    val borderWidth by animateDpAsState(
        targetValue = if (focused) 2.dp else 1.dp,
        animationSpec = tween(135, easing = FastOutSlowInEasing),
        label = "posterBorderWidth"
    )
    val borderColor by animateColorAsState(
        targetValue = if (focused) Color.White.copy(.96f) else Color.White.copy(.10f),
        animationSpec = tween(135, easing = FastOutSlowInEasing),
        label = "posterBorderColor"
    )
    val width = if (isTv) 172.dp else 126.dp
    val height = if (isTv) 250.dp else 190.dp
    val shape = RoundedCornerShape(14.dp)
    Box(
        Modifier.width(width).height(height)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(shadow, shape)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(Color(0xFF111A26))
            .border(borderWidth, borderColor, shape)
            .clickable(onClick = onClick)
    ) {
        if (item.image.isNotBlank()) AsyncImage(item.image, item.name, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Icon(Icons.Default.Tv, null, tint = accent, modifier = Modifier.size(44.dp)) }
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Transparent, Color.Black.copy(.94f)))))
        Column(Modifier.align(Alignment.BottomStart).padding(10.dp)) {
            Text(item.name, color = Color.White, fontSize = if (isTv) 14.sp else 12.sp, lineHeight = if (isTv) 17.sp else 15.sp, fontWeight = FontWeight.Black, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (item.rating.isNotBlank()) Text("★ ${item.rating}", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 3.dp))
        }
        if (focused) {
            Text(
                "OK",
                color = Color.Black,
                fontSize = 10.sp,
                fontWeight = FontWeight.Black,
                modifier = Modifier.align(Alignment.TopEnd).padding(8.dp)
                    .background(accent, RoundedCornerShape(7.dp))
                    .padding(horizontal = 7.dp, vertical = 4.dp)
            )
        }
    }
}'''
)

replace_function(
    hub,
    "private fun V071CategoryRail(",
    r'''private fun V071CategoryRail(
    categories: List<MediaCategory>,
    selectedId: String,
    accent: Color,
    onOverview: () -> Unit,
    onCategory: (Int, MediaCategory) -> Unit
) {
    val railState = rememberLazyListState()
    val selectedFocus = remember(categories.size) { FocusRequester() }
    var initialFocusDone by remember { mutableStateOf(false) }
    val selectedIndex = if (selectedId.isBlank()) 0 else {
        val index = categories.indexOfFirst { it.id == selectedId }
        if (index >= 0) index + 1 else 0
    }

    LaunchedEffect(categories.size) {
        if (categories.isNotEmpty() && !initialFocusDone) {
            railState.scrollToItem(selectedIndex.coerceAtLeast(0))
            delay(55)
            runCatching { selectedFocus.requestFocus() }
            initialFocusDone = true
        }
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
    "private fun V071CategoryRailItem(",
    r'''private fun V071CategoryRailItem(
    title: String,
    selected: Boolean,
    accent: Color,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(11.dp)
    val bg by animateColorAsState(
        targetValue = when {
            focused -> accent.copy(.22f)
            selected -> accent.copy(.13f)
            else -> Color.Transparent
        },
        animationSpec = tween(130, easing = FastOutSlowInEasing),
        label = "railBg"
    )
    val border by animateColorAsState(
        targetValue = when {
            focused -> Color.White.copy(.92f)
            selected -> accent.copy(.58f)
            else -> Color.Transparent
        },
        animationSpec = tween(130, easing = FastOutSlowInEasing),
        label = "railBorder"
    )
    Surface(
        modifier = modifier.fillMaxWidth()
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clickable(onClick = onClick),
        color = bg,
        shape = shape,
        border = BorderStroke(1.dp, border)
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

live = java / "ui/V076LiveTv.kt"
for imp in [
    "import androidx.compose.animation.core.FastOutSlowInEasing",
    "import androidx.compose.animation.animateColorAsState",
    "import androidx.compose.animation.core.animateDpAsState",
    "import androidx.compose.animation.core.animateFloatAsState",
    "import androidx.compose.animation.core.tween",
    "import androidx.compose.ui.graphics.graphicsLayer",
    "import androidx.compose.ui.draw.shadow",
]:
    ensure_import(live, imp)

replace_function(
    live,
    "private fun V076CategoryPane(",
    r'''private fun V076CategoryPane(
    categories: List<MediaCategory>,
    selectedId: String,
    accent: Color,
    onCategory: (MediaCategory) -> Unit,
    modifier: Modifier = Modifier
) {
    val railState = rememberLazyListState()
    val selectedIndex = categories.indexOfFirst { it.id == selectedId }.coerceAtLeast(0)
    val selectedFocus = remember(categories.size) { FocusRequester() }
    var initialFocusDone by remember { mutableStateOf(false) }

    LaunchedEffect(categories.size) {
        if (categories.isNotEmpty() && !initialFocusDone) {
            railState.scrollToItem(selectedIndex)
            delay(55)
            runCatching { selectedFocus.requestFocus() }
            initialFocusDone = true
        }
    }

    Surface(
        modifier = modifier,
        color = Color(0xE80A1019),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Color.White.copy(.08f))
    ) {
        Column(Modifier.fillMaxSize()) {
            Text(
                "KATEGORIEN",
                modifier = Modifier.padding(horizontal = 13.dp, vertical = 12.dp),
                color = Color.White.copy(.58f),
                fontSize = 11.sp,
                fontWeight = FontWeight.Black
            )
            LazyColumn(
                Modifier.fillMaxSize().padding(horizontal = 6.dp),
                state = railState,
                verticalArrangement = Arrangement.spacedBy(3.dp),
                contentPadding = PaddingValues(bottom = 12.dp)
            ) {
                itemsIndexed(categories, key = { _, it -> it.id }) { _, category ->
                    val selected = category.id == selectedId
                    V076CategoryRow(
                        title = category.name,
                        selected = selected,
                        accent = accent,
                        modifier = if (selected) Modifier.focusRequester(selectedFocus) else Modifier,
                        onSelected = { onCategory(category) }
                    )
                }
            }
        }
    }
}'''
)

replace_function(
    live,
    "private fun V076CategoryRow(",
    r'''private fun V076CategoryRow(
    title: String,
    selected: Boolean,
    accent: Color,
    modifier: Modifier = Modifier,
    onSelected: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(10.dp)
    val bg by animateColorAsState(
        targetValue = when {
            focused -> accent.copy(.24f)
            selected -> accent.copy(.13f)
            else -> Color.Transparent
        },
        animationSpec = tween(125, easing = FastOutSlowInEasing),
        label = "liveCategoryBg"
    )
    val textColor by animateColorAsState(
        targetValue = if (focused || selected) Color.White else Color.White.copy(.72f),
        animationSpec = tween(125, easing = FastOutSlowInEasing),
        label = "liveCategoryText"
    )

    Row(
        modifier.fillMaxWidth()
            .onFocusChanged {
                focused = it.isFocused
                if (it.isFocused) onSelected()
            }
            .focusable()
            .background(bg, shape)
            .clickable(onClick = onSelected)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier.width(if (focused || selected) 4.dp else 2.dp).height(25.dp)
                .background(if (focused || selected) accent else Color.White.copy(.16f), RoundedCornerShape(99.dp))
        )
        Spacer(Modifier.width(9.dp))
        Text(
            title,
            color = textColor,
            fontSize = 13.sp,
            fontWeight = if (focused || selected) FontWeight.Black else FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}'''
)

replace_function(
    live,
    "private fun V076ChannelPane(",
    r'''private fun V076ChannelPane(
    channels: List<MediaEntry>,
    selectedId: String,
    accent: Color,
    isTv: Boolean,
    onSelected: (Int, MediaEntry) -> Unit,
    onPlay: (MediaEntry) -> Unit,
    modifier: Modifier = Modifier
) {
    val state = rememberLazyListState()
    Surface(
        modifier = modifier,
        color = Color(0xE80A1019),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Color.White.copy(.08f))
    ) {
        if (channels.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Keine Sender in dieser Kategorie", color = Color.White.copy(.62f))
            }
        } else {
            LazyColumn(
                state = state,
                modifier = Modifier.fillMaxSize().padding(5.dp),
                verticalArrangement = Arrangement.spacedBy(3.dp),
                contentPadding = PaddingValues(bottom = 14.dp)
            ) {
                itemsIndexed(channels, key = { _, m -> m.sourceProfileId + "|" + m.id }) { index, media ->
                    V076ChannelRow(
                        number = index + 1,
                        media = media,
                        selected = media.id == selectedId,
                        accent = accent,
                        isTv = isTv,
                        onSelected = { onSelected(index, media) },
                        onPlay = { onSelected(index, media); onPlay(media) }
                    )
                }
            }
        }
    }
}'''
)

replace_function(
    live,
    "private fun V076ChannelRow(",
    r'''private fun V076ChannelRow(
    number: Int,
    media: MediaEntry,
    selected: Boolean,
    accent: Color,
    isTv: Boolean,
    onSelected: () -> Unit,
    onPlay: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val active = focused || selected
    val epgHeight = if (isTv) 55.dp else 58.dp
    val scale by animateFloatAsState(
        targetValue = if (focused) 1.012f else 1f,
        animationSpec = tween(120, easing = FastOutSlowInEasing),
        label = "liveRowScale"
    )
    val background by animateColorAsState(
        targetValue = when {
            focused -> accent.copy(.28f)
            selected -> accent.copy(.16f)
            else -> Color(0xA80D1520)
        },
        animationSpec = tween(120, easing = FastOutSlowInEasing),
        label = "liveRowBg"
    )
    val borderColor by animateColorAsState(
        targetValue = if (focused) Color.White.copy(.94f) else Color.White.copy(.06f),
        animationSpec = tween(120, easing = FastOutSlowInEasing),
        label = "liveRowBorder"
    )
    val shadow by animateDpAsState(
        targetValue = if (focused) 8.dp else 0.dp,
        animationSpec = tween(120, easing = FastOutSlowInEasing),
        label = "liveRowShadow"
    )
    val shape = RoundedCornerShape(8.dp)

    Surface(
        modifier = Modifier.fillMaxWidth()
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(shadow, shape)
            .onFocusChanged {
                focused = it.isFocused
                if (it.isFocused) onSelected()
            }
            .focusable()
            .clickable(onClick = onPlay),
        color = background,
        shape = shape,
        border = BorderStroke(1.dp, borderColor)
    ) {
        Row(
            Modifier.fillMaxWidth().height(epgHeight).padding(horizontal = 8.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                number.toString(),
                modifier = Modifier.width(32.dp),
                color = if (active) Color.White else Color.White.copy(.58f),
                fontSize = 12.sp,
                fontWeight = FontWeight.Black
            )
            Surface(
                modifier = Modifier.width(if (isTv) 52.dp else 58.dp).fillMaxHeight(),
                color = Color.White,
                shape = RoundedCornerShape(6.dp)
            ) {
                if (media.image.isNotBlank()) {
                    AsyncImage(
                        model = media.image,
                        contentDescription = media.name,
                        modifier = Modifier.fillMaxSize().padding(4.dp),
                        contentScale = ContentScale.Fit
                    )
                } else {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("TV", color = accent, fontWeight = FontWeight.Black, fontSize = 12.sp)
                    }
                }
            }
            Spacer(Modifier.width(9.dp))
            Text(
                media.name,
                modifier = Modifier.weight(1f),
                color = Color.White,
                fontSize = if (isTv) 15.sp else 14.sp,
                fontWeight = if (active) FontWeight.Black else FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            if (active) {
                Text("LIVE", color = Color.White, fontSize = 9.sp, fontWeight = FontWeight.Black)
            }
        }
    }
}'''
)

checks = [
    (gradle, 'versionName = "0.8.3"'),
    (gradle, 'versionCode = 803'),
    (dst, 'fun V083HomeScreen'),
    (dst, 'targetValue = if (focused) 1.025f else 1f'),
    (hub, 'targetValue = if (focused) 1.035f else 1f'),
    (hub, 'var initialFocusDone by remember'),
    (live, 'targetValue = if (focused) 1.012f else 1f'),
    (live, 'var initialFocusDone by remember'),
    (screens, 'V083HomeScreen(vm'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing Android 0.8.3 marker {marker} in {path}")

if 'LaunchedEffect(visibleCategories, selectedCategoryId, categoryStartIndex)' in hub.read_text():
    raise SystemExit("movie/series double scroll feedback loop still present")
if 'LaunchedEffect(selectedId, channels.size)' in live.read_text():
    raise SystemExit("live channel snap-scroll feedback loop still present")

print("Android 0.8.3 motion polish applied")
