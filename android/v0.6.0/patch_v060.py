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


# Version metadata.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 502', 'versionCode = 600', 'versionCode')
replace_once(gradle, 'versionName = "0.5.2"', 'versionName = "0.6.0"', 'versionName')
for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt", "data/XtreamClient.kt"]:
    path = java / rel
    path.write_text(path.read_text().replace("0.5.2", "0.6.0"))


# Media metadata: preserve a provider-supplied YouTube trailer id/URL.
models = java / "model/Models.kt"
replace_once(
    models,
    '    val releaseDate: String = ""\n)',
    '    val releaseDate: String = "",\n    val trailer: String = ""\n)',
    'MediaEntry trailer field',
)

xtream = java / "data/XtreamClient.kt"
text = xtream.read_text()
text = text.replace(
    '            releaseDate = release\n        )',
    '            releaseDate = release,\n            trailer = firstNonBlank(info.optString("youtube_trailer"), info.optString("trailer"), item.trailer)\n        )',
    2,
)
if text.count('trailer = firstNonBlank(info.optString("youtube_trailer")') != 2:
    raise SystemExit("Xtream trailer enrichment anchors missing")
xtream.write_text(text)


# Persist richer metadata and a genuine recently-watched history.
prefs = java / "data/PrefsRepository.kt"
replace_once(
    prefs,
    '    fun toggleFavorite(item: MediaEntry): Boolean {',
    '''    fun recordRecentlyWatched(item: MediaEntry) {
        if (item.kind == MediaKind.LIVE) return
        val list = loadRecentlyWatched().filterNot { it.resumeKey == item.resumeKey }.toMutableList()
        list.add(0, item)
        writeArray("recently_watched", list.take(80).map(::mediaJson))
    }

    fun loadRecentlyWatched(): List<MediaEntry> = readArray("recently_watched")
        .mapNotNull { runCatching { mediaFromJson(it) }.getOrNull() }

    fun toggleFavorite(item: MediaEntry): Boolean {''',
    'recently watched repository',
)
replace_once(
    prefs,
    '        put("plot",m.plot);put("streamUrl",m.streamUrl);put("extension",m.extension);put("seriesId",m.seriesId);put("season",m.season);put("episode",m.episode);put("epgId",m.epgId)\n',
    '        put("plot",m.plot);put("streamUrl",m.streamUrl);put("extension",m.extension);put("seriesId",m.seriesId);put("season",m.season);put("episode",m.episode);put("epgId",m.epgId)\n        put("year",m.year);put("duration",m.duration);put("cast",m.cast);put("director",m.director);put("genre",m.genre);put("releaseDate",m.releaseDate);put("trailer",m.trailer)\n',
    'media metadata persistence',
)
old_media_from = '''    private fun mediaFromJson(o:JSONObject)=MediaEntry(
        o.getString("id"),o.optString("name"),MediaKind.valueOf(o.optString("kind","LIVE")),o.optString("categoryId"),o.optString("image"),o.optString("rating"),
        o.optString("plot"),o.optString("streamUrl"),o.optString("extension","ts"),o.optString("seriesId"),o.optInt("season"),o.optInt("episode"),o.optString("epgId")
    )
'''
new_media_from = '''    private fun mediaFromJson(o:JSONObject)=MediaEntry(
        id=o.getString("id"),name=o.optString("name"),kind=MediaKind.valueOf(o.optString("kind","LIVE")),categoryId=o.optString("categoryId"),
        image=o.optString("image"),rating=o.optString("rating"),plot=o.optString("plot"),streamUrl=o.optString("streamUrl"),extension=o.optString("extension","ts"),
        seriesId=o.optString("seriesId"),season=o.optInt("season"),episode=o.optInt("episode"),epgId=o.optString("epgId"),year=o.optString("year"),
        duration=o.optString("duration"),cast=o.optString("cast"),director=o.optString("director"),genre=o.optString("genre"),releaseDate=o.optString("releaseDate"),trailer=o.optString("trailer")
    )
'''
replace_once(prefs, old_media_from, new_media_from, 'media json restore')


# View-model state for cinematic category rows and recent history.
vm = java / "MainViewModel.kt"
replace_once(vm, '    data object ContinueWatching : Screen\n', '    data object ContinueWatching : Screen\n    data object RecentlyWatched : Screen\n', 'recent screen')
replace_once(
    vm,
    '    val continueWatching: List<ContinueItem> = emptyList(),\n',
    '    val continueWatching: List<ContinueItem> = emptyList(),\n    val recentlyWatched: List<MediaEntry> = emptyList(),\n    val catalogRows: Map<String, List<MediaEntry>> = emptyMap(),\n    val catalogRowsLoading: Boolean = false,\n',
    'catalog state',
)
text = vm.read_text()
anchor = '            continueWatching = prefs.loadContinue(),\n'
if text.count(anchor) != 2:
    raise SystemExit(f"recent state anchors: expected 2, found {text.count(anchor)}")
vm.write_text(text.replace(anchor, '            continueWatching = prefs.loadContinue(),\n            recentlyWatched = prefs.loadRecentlyWatched(),\n', 1))
replace_once(
    vm,
    '                continueWatching = prefs.loadContinue(),\n',
    '                continueWatching = prefs.loadContinue(),\n                recentlyWatched = prefs.loadRecentlyWatched(),\n',
    'refresh recent state',
)
replace_once(
    vm,
    '            Screen.Favorites, Screen.ContinueWatching -> refreshCollections()\n',
    '            Screen.Favorites, Screen.ContinueWatching, Screen.RecentlyWatched -> refreshCollections()\n',
    'recent navigation refresh',
)
replace_once(
    vm,
    '        set { it.copy(loading = true, categories = emptyList(), error = "") }\n',
    '        set { it.copy(loading = true, categories = emptyList(), catalogRows = emptyMap(), catalogRowsLoading = kind == MediaKind.MOVIE || kind == MediaKind.SERIES, error = "") }\n',
    'catalog loading reset',
)
replace_once(
    vm,
    '                set { it.copy(loading = false, categories = categories) }\n',
    '                set { it.copy(loading = false, categories = categories) }\n                loadCatalogRows(kind, categories)\n',
    'catalog row trigger',
)
load_items_anchor = '    private fun loadItems(kind: MediaKind, cat: String) {\n'
catalog_loader = '''    private fun loadCatalogRows(kind: MediaKind, categories: List<MediaCategory>) {
        if (kind != MediaKind.MOVIE && kind != MediaKind.SERIES) return
        val profile = _ui.value.active ?: return
        if (profile.type != PlaylistType.XTREAM || categories.isEmpty()) {
            set { it.copy(catalogRowsLoading = false) }
            return
        }
        viewModelScope.launch {
            val rows = runCatching {
                withContext(Dispatchers.IO) {
                    coroutineScope {
                        categories.take(12).map { category ->
                            async {
                                category.id to runCatching { XtreamClient(profile).entries(kind, category.id).take(24) }.getOrDefault(emptyList())
                            }
                        }.awaitAll().filter { it.second.isNotEmpty() }.toMap()
                    }
                }
            }.getOrDefault(emptyMap())
            if (_ui.value.contentFilterKind == kind) set { it.copy(catalogRows = rows, catalogRowsLoading = false) }
        }
    }

'''
replace_once(vm, load_items_anchor, catalog_loader + load_items_anchor, 'catalog loader insertion')
replace_once(
    vm,
    '    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {\n        val profile = _ui.value.active\n',
    '    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {\n        prefs.recordRecentlyWatched(item)\n        refreshCollections()\n        val profile = _ui.value.active\n',
    'recent play recording',
)


# Route the visual movie/series hubs and recent history screen.
app = java / "EpiMediaHubApp.kt"
replace_once(
    app,
    '                Screen.ContinueWatching -> ContinueWatchingScreen(vm, accent, isTv)\n                is Screen.Categories -> CategoryScreen(vm, s.kind, accent, isTv)\n',
    '                Screen.ContinueWatching -> ContinueWatchingScreen(vm, accent, isTv)\n                Screen.RecentlyWatched -> V060RecentlyWatchedScreen(vm, accent, isTv)\n                is Screen.Categories -> if (s.kind == de.epimediahub.app.model.MediaKind.MOVIE || s.kind == de.epimediahub.app.model.MediaKind.SERIES) V060CinematicHubScreen(vm, s.kind, accent, isTv) else CategoryScreen(vm, s.kind, accent, isTv)\n',
    'cinematic route',
)


# Highly visible focus motion on the main dashboard.
home = java / "ui/V044Home.kt"
text = home.read_text()
text = text.replace('if(focused)1.022f else 1f', 'if(focused)1.065f else 1f')
text = text.replace('stiffness=Spring.StiffnessMedium', 'stiffness=Spring.StiffnessLow')
text = text.replace('.shadow(if(focused)19.dp else 2.dp,shape)', '.shadow(if(focused)28.dp else 2.dp,shape)')
text = text.replace('if(focused)Color.White.copy(.38f)else Color.White.copy(.15f)', 'if(focused)accent else Color.White.copy(.15f)')
home.write_text(text)


# Skin-aware, cinematic channel banners.
rows = java / "ui/BrowserRows.kt"
text = rows.read_text()
text = text.replace('import androidx.compose.foundation.background\n', 'import androidx.compose.animation.core.animateFloatAsState\nimport androidx.compose.animation.core.spring\nimport androidx.compose.foundation.Image\nimport androidx.compose.foundation.background\n')
text = text.replace('import androidx.compose.ui.focus.onFocusChanged\n', 'import androidx.compose.ui.draw.alpha\nimport androidx.compose.ui.draw.shadow\nimport androidx.compose.ui.focus.onFocusChanged\n')
text = text.replace('import androidx.compose.ui.layout.ContentScale\n', 'import androidx.compose.ui.graphics.Brush\nimport androidx.compose.ui.graphics.graphicsLayer\nimport androidx.compose.ui.layout.ContentScale\nimport androidx.compose.ui.res.painterResource\n')
start = text.index('@Composable\nfun LiveChannelRow(')
end = text.index('@Composable\nfun MediaInfoRow(', start)
live = r'''@Composable
fun LiveChannelRow(
    media: MediaEntry,
    nowText: String,
    accent: Color,
    modifier: Modifier = Modifier,
    skinMarkRes: Int = 0,
    isTv: Boolean = false,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.035f else 1f, spring(stiffness = 420f), label = "liveBannerFocus")
    val shape = RoundedCornerShape(if (isTv) 18.dp else 14.dp)
    Surface(
        modifier = modifier.fillMaxWidth().graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 22.dp else 2.dp, shape)
            .onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
        color = Color.Transparent,
        contentColor = Color.White,
        shape = shape,
        border = androidx.compose.foundation.BorderStroke(if (focused) 3.dp else 1.dp, if (focused) accent else Color.White.copy(.10f))
    ) {
        Box(
            Modifier.fillMaxWidth().height(if (isTv) 88.dp else 74.dp)
                .background(Brush.horizontalGradient(listOf(accent.copy(if (focused) .34f else .20f), Color(0xF20B1420), Color(0xFA070B12))))
        ) {
            if (skinMarkRes != 0) Image(
                painterResource(skinMarkRes), null,
                Modifier.align(Alignment.CenterEnd).fillMaxHeight().fillMaxWidth(.40f).alpha(if (focused) .28f else .16f),
                contentScale = ContentScale.Fit
            )
            Box(Modifier.align(Alignment.CenterStart).fillMaxHeight().width(if (focused) 8.dp else 4.dp).background(accent))
            Row(Modifier.fillMaxSize().padding(start = if (isTv) 20.dp else 14.dp, end = 18.dp, top = 9.dp, bottom = 9.dp), verticalAlignment = Alignment.CenterVertically) {
                Surface(shape = RoundedCornerShape(12.dp), color = Color.White.copy(.10f), modifier = Modifier.size(if (isTv) 68.dp else 56.dp)) {
                    if (media.image.isNotBlank()) AsyncImage(media.image, null, Modifier.fillMaxSize().padding(6.dp), contentScale = ContentScale.Fit)
                    else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Icon(Icons.Default.LiveTv, null, tint = accent, modifier = Modifier.size(31.dp)) }
                }
                Spacer(Modifier.width(if (isTv) 18.dp else 13.dp))
                Column(Modifier.weight(1f)) {
                    Text(media.name, color = Color.White, fontSize = if (isTv) 21.sp else 17.sp, fontWeight = FontWeight.Black, maxLines = 1)
                    Text(if (nowText.isNotBlank()) nowText else "Jetzt live", color = if (focused) Color.White else Color.White.copy(.72f), fontSize = if (isTv) 14.sp else 12.sp, maxLines = 1, modifier = Modifier.padding(top = 4.dp))
                }
                Text(if (focused) "OK · ÖFFNEN" else "LIVE", color = if (focused) accent else Color.White.copy(.62f), fontSize = 12.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.width(8.dp))
                Icon(Icons.Default.PlayArrow, null, tint = if (focused) accent else Color.White.copy(.55f), modifier = Modifier.size(31.dp))
            }
        }
    }
}

'''
rows.write_text(text[:start] + live + text[end:])


screens = java / "ui/Screens.kt"
text = screens.read_text()
anchor = 'fun ItemsScreen(vm:MainViewModel,kind:MediaKind,cat:MediaCategory,accent:Color,isTv:Boolean){\n    val u by vm.ui.collectAsState()\n'
if anchor not in text:
    raise SystemExit('ItemsScreen anchor missing')
text = text.replace(anchor, anchor + '    val liveBannerRes=remember(u.themeId){vm.themeRepo().bannerMarkRes(u.themeId).takeIf{it!=0}?:vm.themeRepo().markRes(u.themeId)}\n', 1)
text = text.replace('LiveChannelRow(m,now?.let{"${clock(it.start)}–${clock(it.end)}  ${it.title}"}.orEmpty(),accent){', 'LiveChannelRow(m,now?.let{"${clock(it.start)}–${clock(it.end)}  ${it.title}"}.orEmpty(),accent,skinMarkRes=liveBannerRes,isTv=true){', 1)
text = text.replace('LiveChannelRow(m,now?.title.orEmpty(),accent){vm.rememberBrowserPosition', 'LiveChannelRow(m,now?.title.orEmpty(),accent,skinMarkRes=liveBannerRes,isTv=false){vm.rememberBrowserPosition', 1)
screens.write_text(text)


# Trailer action in the existing detail screen.
details = java / "ui/V043Details.kt"
text = details.read_text()
text = text.replace('package de.epimediahub.app.ui\n\n', 'package de.epimediahub.app.ui\n\nimport android.content.Intent\nimport android.net.Uri\n')
text = text.replace('import androidx.compose.ui.res.painterResource\n', 'import androidx.compose.ui.platform.LocalContext\nimport androidx.compose.ui.res.painterResource\n')
anchor = '    val u by vm.ui.collectAsState()\n    val detail = u.details[item.resumeKey] ?: item\n'
if anchor not in text:
    raise SystemExit('detail context anchor missing')
text = text.replace(anchor, '    val u by vm.ui.collectAsState()\n    val context = LocalContext.current\n    val detail = u.details[item.resumeKey] ?: item\n', 1)
button_anchor = '''                            OutlinedButton(
                                onClick = { vm.toggleFavorite(detail) },
                                shape = RoundedCornerShape(13.dp),
                                modifier = Modifier.height(if (isTv) 54.dp else 46.dp)
                            ) {
                                Icon(if (favorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder, null, tint = if (favorite) accent else Color.White)
                                Spacer(Modifier.width(7.dp))
                                Text(if (favorite) "Favorit" else "Zu Favoriten", color = Color.White, fontWeight = FontWeight.Bold)
                            }
                        }
'''
if button_anchor not in text:
    raise SystemExit('detail action anchor missing')
button_new = button_anchor + '''                        if (detail.trailer.isNotBlank()) {
                            Spacer(Modifier.height(10.dp))
                            OutlinedButton(
                                onClick = {
                                    val raw = detail.trailer.trim()
                                    val url = if (raw.startsWith("http://") || raw.startsWith("https://")) raw else "https://www.youtube.com/watch?v=$raw"
                                    runCatching { context.startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(url))) }
                                },
                                shape = RoundedCornerShape(13.dp),
                                modifier = Modifier.height(if (isTv) 52.dp else 45.dp)
                            ) {
                                Icon(Icons.Default.PlayArrow, null, tint = accent)
                                Spacer(Modifier.width(7.dp))
                                Text("Trailer ansehen", color = Color.White, fontWeight = FontWeight.Bold)
                            }
                        }
'''
text = text.replace(button_anchor, button_new, 1)
details.write_text(text)


# New cinematic content hub.
(java / "ui/V060CinematicHub.kt").write_text(r'''package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.History
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Search
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import de.epimediahub.app.model.MediaCategory
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

@Composable
fun V060CinematicHubScreen(vm: MainViewModel, kind: MediaKind, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val recent = u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }
    val continueItems = u.continueWatching.filter { it.media.kind == kind || (kind == MediaKind.SERIES && it.media.kind == MediaKind.EPISODE) }
    val firstCatalog = u.categories.asSequence().mapNotNull { u.catalogRows[it.id]?.firstOrNull() }.firstOrNull()
    val hero = recent.firstOrNull() ?: firstCatalog
    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(if (kind == MediaKind.MOVIE) "FILME" else "SERIEN", R.drawable.brand_header, { vm.back() })
        LoadingOrError(u.loading, u.error)
        LazyColumn(
            Modifier.fillMaxSize(),
            contentPadding = PaddingValues(bottom = 34.dp),
            verticalArrangement = Arrangement.spacedBy(if (isTv) 21.dp else 15.dp)
        ) {
            hero?.let { featured ->
                item(key = "hero:${featured.resumeKey}") {
                    V060Hero(featured, accent, isTv) { vm.navigate(Screen.Details(featured)) }
                }
            }
            item(key = "actions") {
                Row(
                    Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = if (isTv) 44.dp else 14.dp),
                    horizontalArrangement = Arrangement.spacedBy(10.dp)
                ) {
                    V060Action("Suchen", Icons.Default.Search, accent) { vm.openKindSearch(kind) }
                    V060Action("Zuletzt gesehen", Icons.Default.History, accent) { vm.navigate(Screen.RecentlyWatched) }
                    V060Action("Favoriten", Icons.Default.FavoriteBorder, accent) { vm.openKindFavorites(kind) }
                }
            }
            if (continueItems.isNotEmpty()) {
                item(key = "continue") {
                    V060PosterRow("WEITERSCHAUEN", continueItems.map { it.media }, accent, isTv, onMore = { vm.navigate(Screen.ContinueWatching) }) {
                        if (it.kind == MediaKind.EPISODE) vm.play(it) else vm.navigate(Screen.Details(it))
                    }
                }
            }
            if (recent.isNotEmpty()) {
                item(key = "recent") {
                    V060PosterRow("ZULETZT GESEHEN", recent, accent, isTv, onMore = { vm.navigate(Screen.RecentlyWatched) }) {
                        if (it.kind == MediaKind.EPISODE) vm.play(it) else vm.navigate(Screen.Details(it))
                    }
                }
            }
            items(u.categories.take(12), key = { "category:${it.id}" }) { category ->
                val row = u.catalogRows[category.id].orEmpty()
                if (row.isNotEmpty()) {
                    V060PosterRow(category.name.uppercase(), row, accent, isTv, onMore = { vm.switchLibraryCategory(kind, category) }) {
                        vm.navigate(Screen.Details(it))
                    }
                }
            }
            if (u.catalogRowsLoading) {
                item(key = "catalog-loading") {
                    Row(Modifier.fillMaxWidth().padding(28.dp), horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(22.dp), color = accent, strokeWidth = 2.dp)
                        Spacer(Modifier.width(10.dp))
                        Text("Katalog wird aufgebaut …", color = Color.White.copy(.78f))
                    }
                }
            }
            if (!u.loading && !u.catalogRowsLoading && u.categories.isNotEmpty()) {
                item(key = "all-categories") {
                    TextButton(onClick = { vm.switchLibraryCategory(kind, u.categories.first()) }, modifier = Modifier.padding(horizontal = if (isTv) 44.dp else 14.dp)) {
                        Text("Alle Kategorien öffnen", color = accent, fontWeight = FontWeight.Black)
                    }
                }
            }
        }
    }
}

@Composable
private fun V060Hero(item: MediaEntry, accent: Color, isTv: Boolean, onClick: () -> Unit) {
    val shape = RoundedCornerShape(if (isTv) 25.dp else 18.dp)
    Box(
        Modifier.fillMaxWidth().height(if (isTv) 300.dp else 220.dp)
            .padding(horizontal = if (isTv) 44.dp else 12.dp, vertical = 8.dp)
            .clip(shape).background(Color(0xFF0B1420)).clickable(onClick = onClick)
    ) {
        if (item.image.isNotBlank()) AsyncImage(item.image, item.name, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        Box(Modifier.fillMaxSize().background(Brush.horizontalGradient(listOf(Color.Black.copy(.94f), Color.Black.copy(.66f), Color.Transparent, Color.Black.copy(.18f)))))
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Transparent, Color.Black.copy(.78f)))))
        Column(Modifier.align(Alignment.CenterStart).fillMaxWidth(if (isTv) .54f else .76f).padding(if (isTv) 34.dp else 20.dp)) {
            Text("HEUTE IM FOKUS", color = accent, fontSize = 12.sp, fontWeight = FontWeight.Black)
            Text(item.name, color = Color.White, fontSize = if (isTv) 34.sp else 25.sp, lineHeight = if (isTv) 39.sp else 29.sp, fontWeight = FontWeight.Black, maxLines = 2, overflow = TextOverflow.Ellipsis)
            val meta = listOf(item.year, item.genre, if (item.rating.isBlank()) "" else "★ ${item.rating}").filter { it.isNotBlank() }.joinToString("  ·  ")
            if (meta.isNotBlank()) Text(meta, color = Color.White.copy(.84f), fontSize = 13.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 7.dp), maxLines = 1)
            if (item.plot.isNotBlank()) Text(item.plot, color = Color.White.copy(.82f), fontSize = if (isTv) 15.sp else 13.sp, lineHeight = if (isTv) 20.sp else 18.sp, maxLines = 3, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 9.dp))
            Button(onClick = onClick, colors = ButtonDefaults.buttonColors(containerColor = Color.White), modifier = Modifier.padding(top = 13.dp), shape = RoundedCornerShape(10.dp)) {
                Icon(Icons.Default.PlayArrow, null, tint = Color.Black)
                Spacer(Modifier.width(7.dp))
                Text("Details", color = Color.Black, fontWeight = FontWeight.Black)
            }
        }
    }
}

@Composable
private fun V060Action(title: String, icon: androidx.compose.ui.graphics.vector.ImageVector, accent: Color, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.08f else 1f, spring(stiffness = 380f), label = "hubAction")
    Surface(
        modifier = Modifier.graphicsLayer { scaleX = scale; scaleY = scale }.onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
        color = if (focused) accent.copy(.30f) else Color(0xD9121A24), shape = RoundedCornerShape(13.dp),
        border = BorderStroke(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.13f))
    ) {
        Row(Modifier.padding(horizontal = 16.dp, vertical = 11.dp), verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, null, tint = if (focused) accent else Color.White, modifier = Modifier.size(20.dp))
            Spacer(Modifier.width(8.dp))
            Text(title, color = Color.White, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun V060PosterRow(title: String, entries: List<MediaEntry>, accent: Color, isTv: Boolean, onMore: () -> Unit, onItem: (MediaEntry) -> Unit) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = if (isTv) 44.dp else 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.width(5.dp).height(22.dp).background(accent, RoundedCornerShape(99.dp)))
            Spacer(Modifier.width(9.dp))
            Text(title, color = Color.White, fontSize = if (isTv) 20.sp else 16.sp, fontWeight = FontWeight.Black, modifier = Modifier.weight(1f), maxLines = 1)
            TextButton(onClick = onMore) { Text("ALLE", color = accent, fontWeight = FontWeight.Black, fontSize = 12.sp) }
        }
        LazyRow(
            contentPadding = PaddingValues(horizontal = if (isTv) 44.dp else 14.dp, vertical = 9.dp),
            horizontalArrangement = Arrangement.spacedBy(if (isTv) 15.dp else 11.dp)
        ) {
            items(entries.take(24), key = { it.resumeKey }) { item -> V060Poster(item, accent, isTv) { onItem(item) } }
        }
    }
}

@Composable
private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.10f else 1f, spring(stiffness = 360f), label = "posterFocus")
    val width = if (isTv) 172.dp else 126.dp
    val height = if (isTv) 250.dp else 190.dp
    val shape = RoundedCornerShape(14.dp)
    Box(
        Modifier.width(width).height(height).graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 26.dp else 2.dp, shape).onFocusChanged { focused = it.isFocused }.focusable()
            .clip(shape).background(Color(0xFF111A26)).border(if (focused) 3.dp else 1.dp, if (focused) accent else Color.White.copy(.10f), shape).clickable(onClick = onClick)
    ) {
        if (item.image.isNotBlank()) AsyncImage(item.image, item.name, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Icon(Icons.Default.Tv, null, tint = accent, modifier = Modifier.size(44.dp)) }
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Transparent, Color.Black.copy(.94f)))))
        Column(Modifier.align(Alignment.BottomStart).padding(10.dp)) {
            Text(item.name, color = Color.White, fontSize = if (isTv) 14.sp else 12.sp, lineHeight = if (isTv) 17.sp else 15.sp, fontWeight = FontWeight.Black, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (item.rating.isNotBlank()) Text("★ ${item.rating}", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 3.dp))
        }
        if (focused) Text("OK", color = Color.Black, fontSize = 10.sp, fontWeight = FontWeight.Black, modifier = Modifier.align(Alignment.TopEnd).padding(8.dp).background(accent, RoundedCornerShape(7.dp)).padding(horizontal = 7.dp, vertical = 4.dp))
    }
}

@Composable
fun V060RecentlyWatchedScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val kind = u.contentFilterKind
    val list = if (kind == null) u.recentlyWatched else u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("ZULETZT GESEHEN", R.drawable.brand_header, { vm.back() })
        if (list.isEmpty()) EmptyState("Noch kein Verlauf", "Gestartete Filme und Serien erscheinen automatisch hier.")
        else LazyVerticalGrid(
            GridCells.Adaptive(if (isTv) 170.dp else 124.dp), Modifier.fillMaxSize(),
            contentPadding = PaddingValues(if (isTv) 28.dp else 12.dp), horizontalArrangement = Arrangement.spacedBy(14.dp), verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            gridItems(list, key = { it.resumeKey }) { item -> V060Poster(item, accent, isTv) { if (item.kind == MediaKind.EPISODE) vm.play(item) else vm.navigate(Screen.Details(item)) } }
        }
    }
}
''')

print("Android v0.6.0 cinematic UI patch applied")
