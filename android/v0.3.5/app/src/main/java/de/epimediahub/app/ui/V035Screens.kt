package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.Folder
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaCategory
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun V035HomeScreen(vm: MainViewModel, isTv: Boolean, accent: Color) {
    val u by vm.ui.collectAsState()
    val columns = if (isTv) 4 else 2
    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            u.active?.name ?: "EpiMediaHub",
            R.drawable.brand_header,
            actions = { Text(if (isTv) "ANDROID TV" else "MOBILE", color = Color.White.copy(.58f), fontWeight = FontWeight.SemiBold) }
        )
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            LazyVerticalGrid(
                columns = GridCells.Fixed(columns),
                modifier = Modifier.fillMaxWidth(if (isTv) .92f else .97f).padding(18.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                item { FocusCard("LIVE TV", "Sender & EPG", R.drawable.icon_live, accent = accent, onClick = { vm.openLibrary(MediaKind.LIVE) }, modifier = Modifier.heightIn(min = 138.dp)) }
                item { FocusCard("FILME", "VOD-Mediathek", R.drawable.icon_movies, accent = accent, onClick = { vm.openLibrary(MediaKind.MOVIE) }, modifier = Modifier.heightIn(min = 138.dp)) }
                item { FocusCard("SERIEN", "Staffeln & Episoden", R.drawable.icon_series, accent = accent, onClick = { vm.openLibrary(MediaKind.SERIES) }, modifier = Modifier.heightIn(min = 138.dp)) }
                item { FocusCard("EINSTELLUNGEN", "Playlist · Design · Update", R.drawable.icon_settings, accent = accent, onClick = { vm.navigate(Screen.Settings) }, modifier = Modifier.heightIn(min = 138.dp)) }
            }
        }
    }
}

@Composable
fun V035CategoryScreen(vm: MainViewModel, kind: MediaKind, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar(sectionTitle35(kind), R.drawable.brand_header, { vm.back() })
        StatusLine35(u.loading, u.error, accent)
        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal = if (isTv) 72.dp else 14.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp),
            contentPadding = PaddingValues(bottom = 24.dp)
        ) {
            items(u.categories, key = { it.id }) { category ->
                CategoryListRow(category.name, accent) { vm.switchLibraryCategory(kind, category) }
            }
        }
    }
}

@Composable
fun V035ItemsScreen(vm: MainViewModel, kind: MediaKind, category: MediaCategory, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    BackHandler { vm.back() }
    val listState = rememberLazyListState()
    val lastFocusRequester = remember { FocusRequester() }
    val rememberedId = vm.browserSelectedId(kind, category.id)
    val rememberedIndex = vm.browserPosition(kind, category.id)

    LaunchedEffect(u.items.size, category.id, rememberedId) {
        if (u.items.isNotEmpty() && rememberedIndex > 0) {
            listState.scrollToItem(rememberedIndex.coerceAtMost(u.items.lastIndex))
            if (rememberedId.isNotBlank() && isTv) {
                delay(180)
                runCatching { lastFocusRequester.requestFocus() }
            }
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(sectionTitle35(kind), R.drawable.brand_header, { vm.back() }, actions = {
            Text(category.name, color = accent, fontWeight = FontWeight.Bold, maxLines = 1)
        })
        StatusLine35(u.loading, u.error, accent)
        if (u.epgLoading && kind == MediaKind.LIVE) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())

        if (isTv) {
            Row(
                Modifier.fillMaxSize().padding(horizontal = 13.dp, vertical = 7.dp),
                horizontalArrangement = Arrangement.spacedBy(11.dp)
            ) {
                V035LibrarySidebar(vm, kind, category, accent, Modifier.width(250.dp).fillMaxHeight())
                Surface(
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                    color = Color(0xF20A0F17),
                    shape = RoundedCornerShape(18.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(.08f))
                ) {
                    V035ContentList(vm, kind, category, accent, true, listState, rememberedId, lastFocusRequester)
                }
            }
        } else {
            Column(Modifier.fillMaxSize()) {
                Row(Modifier.fillMaxWidth().padding(horizontal = 10.dp, vertical = 5.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    OutlinedButton(onClick = { vm.navigate(Screen.Categories(kind), remember = false) }, modifier = Modifier.weight(1f)) { Text("Kategorien") }
                    OutlinedButton(onClick = { vm.openKindSearch(kind) }, modifier = Modifier.weight(1f)) { Text("Suche") }
                    OutlinedButton(onClick = { vm.openKindFavorites(kind) }, modifier = Modifier.weight(1f)) { Text("Favoriten") }
                }
                V035ContentList(vm, kind, category, accent, false, listState, rememberedId, lastFocusRequester)
            }
        }
    }
}

@Composable
private fun V035ContentList(
    vm: MainViewModel,
    kind: MediaKind,
    category: MediaCategory,
    accent: Color,
    isTv: Boolean,
    listState: androidx.compose.foundation.lazy.LazyListState,
    rememberedId: String,
    focusRequester: FocusRequester
) {
    val u by vm.ui.collectAsState()
    LazyColumn(
        state = listState,
        modifier = Modifier.fillMaxSize().padding(9.dp),
        contentPadding = PaddingValues(bottom = 24.dp),
        verticalArrangement = Arrangement.spacedBy(if (kind == MediaKind.LIVE) 6.dp else 10.dp)
    ) {
        itemsIndexed(u.items, key = { _, item -> item.kind.name + item.id }) { index, item ->
            val focusMod = if (isTv && rememberedId.isNotBlank() && item.id == rememberedId) Modifier.focusRequester(focusRequester) else Modifier
            if (kind == MediaKind.LIVE) {
                val now = currentEpg35(u.epg[item.id].orEmpty())
                LiveChannelRow(item, now?.let { "${clock35(it.start)}–${clock35(it.end)}  ${it.title}" }.orEmpty(), accent, focusMod) {
                    vm.rememberBrowserPosition(kind, category.id, index, item.id)
                    vm.play(item)
                }
            } else {
                LaunchedEffect(item.resumeKey) { vm.ensureDetails(item) }
                val detail = u.details[item.resumeKey] ?: item
                MediaInfoRow(detail, u.detailLoading.contains(item.resumeKey), accent, isTv, focusMod) {
                    vm.rememberBrowserPosition(kind, category.id, index, item.id)
                    if (kind == MediaKind.SERIES) vm.navigate(Screen.Episodes(detail)) else vm.play(detail)
                }
            }
        }
    }
}

@Composable
private fun V035LibrarySidebar(vm: MainViewModel, kind: MediaKind, current: MediaCategory, accent: Color, modifier: Modifier) {
    val u by vm.ui.collectAsState()
    val favCount = u.favorites.count { matchesKind35(it, kind) }
    Surface(
        modifier = modifier,
        color = Color(0xF20A0F17),
        shape = RoundedCornerShape(18.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(.08f))
    ) {
        LazyColumn(Modifier.fillMaxSize().padding(8.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
            item { SideRow35("Suche", false, accent, Icons.Default.Search) { vm.openKindSearch(kind) } }
            item { SideRow35(if (favCount > 0) "Favoriten ($favCount)" else "Favoriten", false, accent, Icons.Default.FavoriteBorder) { vm.openKindFavorites(kind) } }
            item { HorizontalDivider(color = Color.White.copy(.08f), modifier = Modifier.padding(vertical = 5.dp)) }
            items(u.categories, key = { it.id }) { c ->
                SideRow35(c.name, c.id == current.id, accent, Icons.Default.Folder) {
                    if (c.id != current.id) vm.switchLibraryCategory(kind, c)
                }
            }
        }
    }
}

@Composable
private fun SideRow35(title: String, selected: Boolean, accent: Color, icon: ImageVector, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(11.dp)
    Row(
        Modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused }.focusable()
            .background(if (selected || focused) accent.copy(if (focused) .28f else .15f) else Color.Transparent, shape)
            .border(1.dp, if (focused) accent else Color.Transparent, shape)
            .clickable(onClick = onClick).padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Icon(icon, null, tint = if (selected || focused) accent else Color.White.copy(.55f), modifier = Modifier.size(19.dp))
        Spacer(Modifier.width(8.dp))
        Text(title, color = Color.White, fontWeight = if (selected || focused) FontWeight.Bold else FontWeight.Medium, fontSize = 14.sp, maxLines = 2)
    }
}

@Composable
fun V035SearchScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val kind = u.contentFilterKind
    var query by remember { mutableStateOf("") }
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("${kind?.let { sectionTitle35(it) + " · " }.orEmpty()}SUCHE", R.drawable.brand_header, { vm.back() })
        OutlinedTextField(
            value = query,
            onValueChange = { query = it; vm.search(it) },
            label = { Text("Suchen") },
            leadingIcon = { Icon(Icons.Default.Search, null) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(horizontal = if (isTv) 70.dp else 14.dp, vertical = 9.dp)
        )
        StatusLine35(u.loading, u.error, accent)
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = if (isTv) 70.dp else 12.dp), contentPadding = PaddingValues(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            items(u.searchResults, key = { it.resumeKey }) { item ->
                SearchOrFavoriteRow35(vm, item, accent, isTv)
            }
        }
    }
}

@Composable
fun V035FavoritesScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val kind = u.contentFilterKind
    val filtered = if (kind == null) u.favorites else u.favorites.filter { matchesKind35(it, kind) }
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("${kind?.let { sectionTitle35(it) + " · " }.orEmpty()}FAVORITEN", R.drawable.brand_header, { vm.back() })
        if (filtered.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Text("Noch keine Favoriten in diesem Bereich", color = Color.White.copy(.65f), fontSize = 18.sp) }
        } else {
            LazyColumn(Modifier.fillMaxSize().padding(horizontal = if (isTv) 70.dp else 12.dp, vertical = 8.dp), contentPadding = PaddingValues(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                items(filtered, key = { it.resumeKey }) { item -> SearchOrFavoriteRow35(vm, item, accent, isTv) }
            }
        }
    }
}

@Composable
private fun SearchOrFavoriteRow35(vm: MainViewModel, item: MediaEntry, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    if (item.kind == MediaKind.LIVE) {
        LiveChannelRow(item, "Live TV", accent) { vm.play(item) }
    } else {
        LaunchedEffect(item.resumeKey) { vm.ensureDetails(item) }
        val detail = u.details[item.resumeKey] ?: item
        MediaInfoRow(detail, u.detailLoading.contains(item.resumeKey), accent, isTv) {
            if (item.kind == MediaKind.SERIES) vm.navigate(Screen.Episodes(detail)) else vm.play(detail)
        }
    }
}

@Composable
private fun StatusLine35(loading: Boolean, error: String?, accent: Color) {
    if (loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth(), color = accent)
    if (!error.isNullOrBlank()) Text(error, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(horizontal = 16.dp, vertical = 4.dp))
}

private fun sectionTitle35(kind: MediaKind): String = when (kind) {
    MediaKind.LIVE -> "LIVE TV"
    MediaKind.MOVIE -> "FILME"
    MediaKind.SERIES -> "SERIEN"
    MediaKind.EPISODE -> "EPISODEN"
}

private fun matchesKind35(item: MediaEntry, kind: MediaKind): Boolean = item.kind == kind || (kind == MediaKind.SERIES && item.kind == MediaKind.EPISODE)
private fun currentEpg35(items: List<EpgItem>): EpgItem? {
    val now = System.currentTimeMillis()
    return items.firstOrNull { now in it.start until it.end } ?: items.firstOrNull { it.end > now }
}
private fun clock35(ms: Long): String = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(ms))
