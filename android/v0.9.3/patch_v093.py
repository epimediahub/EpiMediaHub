#!/usr/bin/env python3
"""Android 0.9.3: clean Continue Watching, category visibility and VOD seek/time overlay."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
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
    a, b = function_span(text, signature)
    path.write_text(text[:a] + replacement.rstrip() + text[b:])

# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 902', 'versionCode = 903', 'versionCode')
replace_once(gradle, 'versionName = "0.9.2"', 'versionName = "0.9.3"', 'versionName')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.9.2", "0.9.3"))

# ---------------------------------------------------------------------------
# Shared UI helpers.
# ---------------------------------------------------------------------------
helpers = java / "ui/V093PlaybackUi.kt"
helpers.write_text(r'''package de.epimediahub.app.ui

import de.epimediahub.app.model.ContinueItem
import de.epimediahub.app.model.MediaKind

internal fun V093FormatTime(ms: Long): String {
    val totalSeconds = (ms.coerceAtLeast(0L) / 1000L)
    val hours = totalSeconds / 3600L
    val minutes = (totalSeconds % 3600L) / 60L
    val seconds = totalSeconds % 60L
    return if (hours > 0L) {
        "%d:%02d:%02d".format(hours, minutes, seconds)
    } else {
        "%02d:%02d".format(minutes, seconds)
    }
}

internal fun V093RemainingMinutes(positionMs: Long, durationMs: Long): Long {
    if (durationMs <= 0L) return 0L
    val remaining = (durationMs - positionMs).coerceAtLeast(0L)
    return (remaining + 59_999L) / 60_000L
}

internal fun V093ContinueLabel(item: ContinueItem): String {
    val media = item.media
    val parts = mutableListOf<String>()
    if (media.kind == MediaKind.EPISODE) {
        if (media.categoryId.isNotBlank()) parts += media.categoryId
        parts += if (media.season <= 0) "Spezial · Folge ${media.episode}" else "Staffel ${media.season} · Folge ${media.episode}"
    }
    val remaining = V093RemainingMinutes(item.positionMs, item.durationMs)
    if (remaining > 0L) parts += "noch ${remaining} Min."
    return if (parts.isEmpty()) "Fortsetzen" else parts.joinToString(" · ")
}
''')

# ---------------------------------------------------------------------------
# Continue Watching persistence: one entry per series, always the most recent
# episode. This also de-duplicates old saved entries at load time.
# ---------------------------------------------------------------------------
prefs = java / "data/PrefsRepository.kt"
ps = prefs.read_text()

collection_anchor = '''    private fun collectionKey(base: String, profileId: String): String =
        if (profileId.isBlank()) base else "${base}_$profileId"
'''
if collection_anchor not in ps:
    raise SystemExit("Prefs collectionKey anchor missing")
collection_new = collection_anchor + r'''
    private fun continueIdentity(item: MediaEntry): String =
        if (item.kind == MediaKind.EPISODE && item.seriesId.isNotBlank()) "series:${item.seriesId}" else item.resumeKey

    private fun hiddenCategoryKey(profileId: String, kind: MediaKind): String =
        "hidden_categories_${profileId}_${kind.name}"

    fun loadHiddenCategories(profileId: String, kind: MediaKind): Set<String> =
        p.getStringSet(hiddenCategoryKey(profileId, kind), emptySet())?.toSet().orEmpty()

    fun setCategoryHidden(profileId: String, kind: MediaKind, categoryId: String, hidden: Boolean) {
        if (profileId.isBlank() || categoryId.isBlank()) return
        val values = loadHiddenCategories(profileId, kind).toMutableSet()
        if (hidden) values += categoryId else values -= categoryId
        p.edit().putStringSet(hiddenCategoryKey(profileId, kind), values).apply()
    }
'''
prefs.write_text(ps.replace(collection_anchor, collection_new, 1))

replace_function(
    prefs,
    '    fun savePlayback(',
    r'''    fun savePlayback(item: MediaEntry, pos: Long, duration: Long) {
        if(item.kind==MediaKind.LIVE) return
        val profileId = item.sourceProfileId
        val safe=pos.coerceAtLeast(0L)
        val done=duration>0 && safe >= (duration*.93).toLong()
        if(done) p.edit().remove("resume_${item.resumeKey}").apply() else p.edit().putLong("resume_${item.resumeKey}",safe).apply()

        val identity = continueIdentity(item)
        val list=loadContinue(profileId)
            .filterNot { continueIdentity(it.media) == identity }
            .toMutableList()

        if(!done && safe>=15_000) {
            list.add(0,ContinueItem(item,safe,duration.coerceAtLeast(0),System.currentTimeMillis()))
        }
        writeArray(collectionKey("continue", profileId),list.take(60).map(::continueJson))
    }'''
)

replace_function(
    prefs,
    '    fun loadContinue(',
    r'''    fun loadContinue(profileId: String = ""): List<ContinueItem> {
        fun decode(key: String) = readArray(key).mapNotNull { o ->
            runCatching { ContinueItem(mediaFromJson(o.getJSONObject("media")),o.optLong("position"),o.optLong("duration"),o.optLong("updated")) }.getOrNull()
        }.sortedByDescending{it.updatedAt}

        fun clean(list: List<ContinueItem>): List<ContinueItem> =
            list.sortedByDescending { it.updatedAt }.distinctBy { continueIdentity(it.media) }

        val scoped = clean(decode(collectionKey("continue", profileId)))
        if (profileId.isBlank() || scoped.isNotEmpty()) return scoped
        return clean(decode("continue").filter { it.media.sourceProfileId == profileId })
    }'''
)

ps = prefs.read_text()
clear_anchor = '''        edit.remove(collectionKey("favorites_items", profileId))
        p.all.keys.filter { it.startsWith("resume_${profileId}:") }.forEach { edit.remove(it) }
'''
if clear_anchor not in ps:
    raise SystemExit("Prefs clear collections anchor missing")
prefs.write_text(ps.replace(
    clear_anchor,
    '''        edit.remove(collectionKey("favorites_items", profileId))
        p.all.keys.filter { it.startsWith("resume_${profileId}:") }.forEach { edit.remove(it) }
        p.all.keys.filter { it.startsWith("hidden_categories_${profileId}_") }.forEach { edit.remove(it) }
''',
    1,
))

# ---------------------------------------------------------------------------
# ViewModel state and category visibility controls.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
vs = vm.read_text()
replace_once(
    vm,
    'data object RecentlyWatched : Screen\n',
    'data object RecentlyWatched : Screen\ndata class ManageCategories(val kind: MediaKind) : Screen\n',
    'category manager screen',
)
replace_once(
    vm,
    'val catalogRowsLoading: Boolean = false,\n',
    'val catalogRowsLoading: Boolean = false,\nval hiddenCategoryIds: Set<String> = emptySet(),\n',
    'hidden category UI state',
)

vs = vm.read_text()
_, favorites_end = function_span(vs, "fun openKindFavorites(")
category_methods = r'''

fun openCategoryManager(kind: MediaKind) {
    val profileId = _ui.value.active?.id.orEmpty()
    set {
        it.copy(
            contentFilterKind = kind,
            hiddenCategoryIds = prefs.loadHiddenCategories(profileId, kind)
        )
    }
    navigate(Screen.ManageCategories(kind))
}

fun setCategoryVisible(kind: MediaKind, categoryId: String, visible: Boolean) {
    val profileId = _ui.value.active?.id.orEmpty()
    if (profileId.isBlank()) return
    prefs.setCategoryHidden(profileId, kind, categoryId, !visible)
    val hidden = prefs.loadHiddenCategories(profileId, kind)
    if (!visible && rememberedLibraryCategory(kind) == categoryId) {
        rememberLibraryCategory(kind, "")
    }
    set { it.copy(hiddenCategoryIds = hidden) }
}
'''
vm.write_text(vs[:favorites_end] + category_methods + vs[favorites_end:])

vs = vm.read_text()
cat_start, cat_end = function_span(vs, "fun loadCategories(")
cat_fn = vs[cat_start:cat_end]
p_anchor = 'val p = _ui.value.active ?: return\n'
if p_anchor not in cat_fn:
    raise SystemExit("loadCategories profile anchor missing")
cat_fn = cat_fn.replace(
    p_anchor,
    p_anchor + 'val hiddenForKind = prefs.loadHiddenCategories(p.id, kind)\n',
    1,
)
loading_anchor = 'catalogRowsLoading = kind == MediaKind.MOVIE || kind == MediaKind.SERIES || kind == MediaKind.LIVE,\n'
if loading_anchor not in cat_fn:
    raise SystemExit("loadCategories loading anchor missing")
cat_fn = cat_fn.replace(
    loading_anchor,
    loading_anchor + 'hiddenCategoryIds = hiddenForKind,\n',
    1,
)
vm.write_text(vs[:cat_start] + cat_fn + vs[cat_end:])

vs = vm.read_text()
select_anchor = 'contentFilterKind = null,\n'
if vs.count(select_anchor) != 1:
    raise SystemExit(f"selectPlaylist contentFilter reset count was {vs.count(select_anchor)}")
vm.write_text(vs.replace(
    select_anchor,
    select_anchor + 'hiddenCategoryIds = emptySet(),\n',
    1,
))

# ---------------------------------------------------------------------------
# Continue Watching full screen: episode identity + remaining minutes.
# ---------------------------------------------------------------------------
screens = java / "ui/Screens.kt"
replace_function(
    screens,
    'fun ContinueWatchingScreen(',
    r'''fun ContinueWatchingScreen(vm:MainViewModel,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar("WEITERSCHAUEN",R.drawable.brand_header,{vm.back()})
        if(u.continueWatching.isEmpty()){
            EmptyState("Nichts offen","Angefangene Filme und Serien erscheinen hier.")
        } else {
            LazyVerticalGrid(
                GridCells.Fixed(if(isTv)5 else 2),
                Modifier.fillMaxSize().padding(14.dp),
                horizontalArrangement=Arrangement.spacedBy(10.dp),
                verticalArrangement=Arrangement.spacedBy(10.dp)
            ){
                gridItems(u.continueWatching,key={it.media.resumeKey}){c->
                    MediaCard(c.media,accent,V093ContinueLabel(c),c.progress){vm.play(c.media)}
                }
            }
        }
    }
}'''
)

# ---------------------------------------------------------------------------
# Cinematic hub: hide unwanted categories, expose manager, and show continue
# metadata directly on each poster.
# ---------------------------------------------------------------------------
hub = java / "ui/V060CinematicHub.kt"
hs = hub.read_text()
replace_once(
    hub,
    '    val visibleCategories = u.categories.filter { u.catalogRows[it.id].orEmpty().isNotEmpty() }',
    '    val visibleCategories = u.categories.filter { it.id !in u.hiddenCategoryIds && u.catalogRows[it.id].orEmpty().isNotEmpty() }',
    'cinematic hidden categories',
)

hs = hub.read_text()
action_anchor = '''                            V060Action("Favoriten", Icons.Default.FavoriteBorder, accent) { vm.openKindFavorites(kind) }
'''
if action_anchor not in hs:
    raise SystemExit("cinematic action anchor missing")
hub.write_text(hs.replace(
    action_anchor,
    action_anchor + '                            V060Action("Kategorien verwalten", Icons.Default.Tv, accent) { vm.openCategoryManager(kind) }\n',
    1,
))

hs = hub.read_text()
continue_call = '''                            V060PosterRow("WEITERSCHAUEN", continueItems.map { it.media }, accent, isTv, onMore = { vm.navigate(Screen.ContinueWatching) }) {
                                if (it.kind == MediaKind.EPISODE) vm.play(it) else vm.navigate(Screen.Details(it))
                            }'''
if continue_call not in hs:
    raise SystemExit("cinematic Continue Watching row anchor missing")
hub.write_text(hs.replace(
    continue_call,
    '''                            V060PosterRow(
                                "WEITERSCHAUEN",
                                continueItems.map { it.media },
                                accent,
                                isTv,
                                onMore = { vm.navigate(Screen.ContinueWatching) },
                                infoByKey = continueItems.associate { it.media.resumeKey to V093ContinueLabel(it) }
                            ) {
                                if (it.kind == MediaKind.EPISODE) vm.play(it) else vm.navigate(Screen.Details(it))
                            }''',
    1,
))

replace_function(
    hub,
    'private fun V060PosterRow(',
    r'''private fun V060PosterRow(
    title: String,
    entries: List<MediaEntry>,
    accent: Color,
    isTv: Boolean,
    onMore: (() -> Unit)?,
    infoByKey: Map<String, String> = emptyMap(),
    onItem: (MediaEntry) -> Unit
) {
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(horizontal = if (isTv) 44.dp else 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.width(5.dp).height(22.dp).background(accent, RoundedCornerShape(99.dp)))
            Spacer(Modifier.width(9.dp))
            Text(title, color = Color.White, fontSize = if (isTv) 20.sp else 16.sp, fontWeight = FontWeight.Black, modifier = Modifier.weight(1f), maxLines = 1)
            if (onMore != null) TextButton(onClick = onMore) { Text("ALLE", color = accent, fontWeight = FontWeight.Black, fontSize = 12.sp) }
        }
        LazyRow(
            contentPadding = PaddingValues(horizontal = if (isTv) 44.dp else 14.dp, vertical = 9.dp),
            horizontalArrangement = Arrangement.spacedBy(if (isTv) 15.dp else 11.dp)
        ) {
            items(entries, key = { it.resumeKey }) { item ->
                V060Poster(item, accent, isTv, infoByKey[item.resumeKey].orEmpty()) { onItem(item) }
            }
        }
    }
}'''
)

# Preserve the current v0.8.3 focus animation but add an optional metadata line.
hs = hub.read_text()
sig = 'private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, onClick: () -> Unit) {'
if sig not in hs:
    raise SystemExit("V060Poster signature missing")
hs = hs.replace(sig, 'private fun V060Poster(item: MediaEntry, accent: Color, isTv: Boolean, infoText: String = "", onClick: () -> Unit) {', 1)
poster_name = '''            Text(item.name, color = Color.White, fontSize = if (isTv) 14.sp else 12.sp, lineHeight = if (isTv) 17.sp else 15.sp, fontWeight = FontWeight.Black, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (item.rating.isNotBlank()) Text("★ ${item.rating}", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 3.dp))
'''
if poster_name not in hs:
    raise SystemExit("V060Poster text anchor missing")
hs = hs.replace(
    poster_name,
    '''            Text(item.name, color = Color.White, fontSize = if (isTv) 14.sp else 12.sp, lineHeight = if (isTv) 17.sp else 15.sp, fontWeight = FontWeight.Black, maxLines = 2, overflow = TextOverflow.Ellipsis)
            if (infoText.isNotBlank()) {
                Text(infoText, color = accent, fontSize = if (isTv) 11.sp else 9.sp, fontWeight = FontWeight.Bold, maxLines = 2, overflow = TextOverflow.Ellipsis, modifier = Modifier.padding(top = 3.dp))
            } else if (item.rating.isNotBlank()) {
                Text("★ ${item.rating}", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 3.dp))
            }
''',
    1,
)
hub.write_text(hs)

# ---------------------------------------------------------------------------
# Live TV: apply hidden categories and expose category manager.
# ---------------------------------------------------------------------------
live = java / "ui/V076LiveTv.kt"
ls = live.read_text()
replace_once(
    live,
    '''    val categories = remember(u.categories, u.catalogRows) {
        u.categories.filter { u.catalogRows[it.id].orEmpty().isNotEmpty() }
    }''',
    '''    val categories = remember(u.categories, u.catalogRows, u.hiddenCategoryIds) {
        u.categories.filter { it.id !in u.hiddenCategoryIds && u.catalogRows[it.id].orEmpty().isNotEmpty() }
    }''',
    'Live hidden categories',
)
ls = live.read_text()
fav_action = '''                    TextButton(onClick = { vm.openKindFavorites(MediaKind.LIVE) }) {
                        Text("Favoriten", color = accent, fontWeight = FontWeight.Black)
                    }
'''
if fav_action not in ls:
    raise SystemExit("Live favorites action anchor missing")
live.write_text(ls.replace(
    fav_action,
    fav_action + '''                    TextButton(onClick = { vm.openCategoryManager(MediaKind.LIVE) }) {
                        Text("Kategorien", color = accent, fontWeight = FontWeight.Black)
                    }
''',
    1,
))

# ---------------------------------------------------------------------------
# Category visibility manager.
# ---------------------------------------------------------------------------
manager = java / "ui/V093CategoryVisibility.kt"
manager.write_text(r'''package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.model.MediaKind

@Composable
fun V093CategoryVisibilityScreen(vm: MainViewModel, kind: MediaKind, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val categories = u.categories.filterNot { it.id == "__recently_added__" }
    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            when(kind) {
                MediaKind.LIVE -> "LIVE-TV-KATEGORIEN"
                MediaKind.MOVIE -> "FILM-KATEGORIEN"
                else -> "SERIEN-KATEGORIEN"
            },
            R.drawable.brand_header,
            { vm.back() }
        )
        Text(
            "Nicht benötigte Kategorien kannst du hier ausblenden. Sie werden nicht gelöscht und lassen sich jederzeit wieder einschalten.",
            color = Color.White.copy(.70f),
            fontSize = if (isTv) 15.sp else 13.sp,
            modifier = Modifier.padding(horizontal = if (isTv) 34.dp else 16.dp, vertical = 12.dp)
        )
        if (categories.isEmpty()) {
            EmptyState("Keine Kategorien", "Für diesen Bereich wurden keine Kategorien geladen.")
        } else {
            LazyColumn(
                Modifier.fillMaxSize(),
                contentPadding = PaddingValues(horizontal = if (isTv) 34.dp else 12.dp, vertical = 8.dp),
                verticalArrangement = Arrangement.spacedBy(7.dp)
            ) {
                items(categories, key = { it.id }) { category ->
                    val visible = category.id !in u.hiddenCategoryIds
                    var focused by remember { mutableStateOf(false) }
                    Surface(
                        modifier = Modifier.fillMaxWidth()
                            .onFocusChanged { focused = it.isFocused }
                            .focusable()
                            .clickable { vm.setCategoryVisible(kind, category.id, !visible) },
                        color = if (focused) accent.copy(.24f) else Color(0xD90D1520),
                        shape = RoundedCornerShape(13.dp),
                        border = BorderStroke(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.08f))
                    ) {
                        Row(
                            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = if (isTv) 13.dp else 10.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column(Modifier.weight(1f)) {
                                Text(category.name, color = Color.White, fontWeight = FontWeight.Bold, fontSize = if (isTv) 16.sp else 14.sp)
                                Text(if (visible) "Sichtbar" else "Ausgeblendet", color = if (visible) accent else Color.White.copy(.48f), fontSize = 11.sp)
                            }
                            Switch(
                                checked = visible,
                                onCheckedChange = { enabled -> vm.setCategoryVisible(kind, category.id, enabled) }
                            )
                        }
                    }
                }
            }
        }
    }
}
''')

# App route.
app = java / "EpiMediaHubApp.kt"
replace_once(
    app,
    '                Screen.RecentlyWatched -> V060RecentlyWatchedScreen(vm, accent, isTv)\n',
    '                Screen.RecentlyWatched -> V060RecentlyWatchedScreen(vm, accent, isTv)\n                is Screen.ManageCategories -> V093CategoryVisibilityScreen(vm, s.kind, accent, isTv)\n',
    'category manager route',
)

# ---------------------------------------------------------------------------
# VOD player: exact seek/time overlay for movies and episodes. On TV the native
# Media3 controller is disabled for all VOD so there is only one clean overlay.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
pl = player.read_text()

state_anchor = '''    var controls by remember(item.resumeKey) { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
'''
if state_anchor not in pl:
    raise SystemExit("player state anchor missing")
pl = pl.replace(
    state_anchor,
    '''    var controls by remember(item.resumeKey) { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
    var playbackPositionMs by remember(item.resumeKey) { mutableLongStateOf(0L) }
    var playbackDurationMs by remember(item.resumeKey) { mutableLongStateOf(0L) }
''',
    1,
)

old_autohide = '''    LaunchedEffect(item.resumeKey, controls) {
        if ((item.kind == MediaKind.LIVE || item.kind == MediaKind.EPISODE) && controls) {
            delay(if (item.kind == MediaKind.LIVE) 4500 else 3500)
            controls = false
        }
    }'''
if old_autohide not in pl:
    raise SystemExit("player auto-hide anchor missing")
pl = pl.replace(
    old_autohide,
    '''    LaunchedEffect(item.resumeKey, controls) {
        if (controls) {
            delay(if (item.kind == MediaKind.LIVE) 4500 else 3500)
            controls = false
        }
    }

    LaunchedEffect(player, item.resumeKey) {
        while (true) {
            playbackPositionMs = player.currentPosition.coerceAtLeast(0L)
            playbackDurationMs = player.duration.takeIf { it > 0L } ?: 0L
            delay(250L)
        }
    }''',
    1,
)

old_seek = '''    fun seekBy(deltaMs: Long) {
        val duration = player.duration.takeIf { it > 0 } ?: Long.MAX_VALUE
        val target = (player.currentPosition + deltaMs).coerceAtLeast(0L).coerceAtMost(duration)
        player.seekTo(target)
        controls = true
    }'''
if old_seek not in pl:
    raise SystemExit("player seekBy anchor missing")
pl = pl.replace(
    old_seek,
    '''    fun seekBy(deltaMs: Long) {
        val duration = player.duration.takeIf { it > 0 } ?: Long.MAX_VALUE
        val target = (player.currentPosition + deltaMs).coerceAtLeast(0L).coerceAtMost(duration)
        player.seekTo(target)
        playbackPositionMs = target
        if (duration != Long.MAX_VALUE) playbackDurationMs = duration
        controls = true
    }''',
    1,
)

# Two PlayerView construction/update occurrences.
old_use = 'useController = item.kind != MediaKind.LIVE && !(isTv && item.kind == MediaKind.EPISODE)'
old_auto = 'controllerAutoShow = item.kind != MediaKind.LIVE && !(isTv && item.kind == MediaKind.EPISODE)'
if pl.count(old_use) != 2 or pl.count(old_auto) != 2:
    raise SystemExit(f"player controller anchors unexpected use={pl.count(old_use)} auto={pl.count(old_auto)}")
pl = pl.replace(old_use, 'useController = item.kind != MediaKind.LIVE && !isTv')
pl = pl.replace(old_auto, 'controllerAutoShow = item.kind != MediaKind.LIVE && !isTv')
pl = pl.replace(
    'if (item.kind == MediaKind.LIVE || (isTv && item.kind == MediaKind.EPISODE)) hideController()',
    'if (item.kind == MediaKind.LIVE || isTv) hideController()',
)
pl = pl.replace(
    'if (item.kind == MediaKind.LIVE || (isTv && item.kind == MediaKind.EPISODE)) it.hideController()',
    'if (item.kind == MediaKind.LIVE || isTv) it.hideController()',
)

# Add the seek/time panel immediately before the existing episode metadata overlay.
episode_marker = '        if (isEpisode && controls) {\n'
if episode_marker not in pl:
    raise SystemExit("episode overlay insertion marker missing")
vod_overlay = r'''        if (item.kind != MediaKind.LIVE && controls) {
            val duration = playbackDurationMs.coerceAtLeast(0L)
            val position = playbackPositionMs.coerceIn(0L, if (duration > 0L) duration else Long.MAX_VALUE)
            val progress = if (duration > 0L) (position.toFloat() / duration.toFloat()).coerceIn(0f, 1f) else 0f
            val remainingMinutes = V093RemainingMinutes(position, duration)
            val vodTitle = if (isEpisode) item.categoryId.ifBlank { "Serie" } else item.name
            Surface(
                modifier = Modifier
                    .align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .padding(horizontal = 28.dp, vertical = 26.dp),
                color = Color(0xEA080D14),
                shape = MaterialTheme.shapes.large,
                border = androidx.compose.foundation.BorderStroke(1.dp, accent.copy(alpha = .70f))
            ) {
                Column(Modifier.fillMaxWidth().padding(horizontal = 20.dp, vertical = 14.dp)) {
                    Text(vodTitle, color = Color.White, fontWeight = FontWeight.Black, fontSize = 18.sp, maxLines = 1)
                    if (isEpisode) {
                        Text(
                            buildString {
                                append(if (item.season <= 0) "Spezial · Folge ${item.episode}" else "Staffel ${item.season} · Folge ${item.episode}")
                                if (item.name.isNotBlank() && !item.name.equals(vodTitle, ignoreCase = true)) append(" · ").append(item.name)
                            },
                            color = Color.White.copy(alpha = .72f),
                            fontSize = 12.sp,
                            maxLines = 1
                        )
                    }
                    Spacer(Modifier.height(10.dp))
                    LinearProgressIndicator(
                        progress = { progress },
                        modifier = Modifier.fillMaxWidth().height(5.dp),
                        color = accent,
                        trackColor = Color.White.copy(alpha = .16f)
                    )
                    Spacer(Modifier.height(8.dp))
                    Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                        Text(V093FormatTime(position), color = Color.White, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                        Spacer(Modifier.weight(1f))
                        if (remainingMinutes > 0L) {
                            Text("noch ${remainingMinutes} Min.", color = accent, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                            Spacer(Modifier.width(18.dp))
                        }
                        Text(V093FormatTime(duration), color = Color.White.copy(alpha = .70f), fontSize = 13.sp)
                    }
                }
            }
        }

'''
pl = pl.replace(episode_marker, vod_overlay + episode_marker, 1)
player.write_text(pl)

# Sanity.
checks = [
    (gradle, 'versionName = "0.9.3"'),
    (gradle, 'versionCode = 903'),
    (prefs, 'private fun continueIdentity(item: MediaEntry)'),
    (prefs, 'distinctBy { continueIdentity(it.media) }'),
    (prefs, 'fun loadHiddenCategories(profileId: String, kind: MediaKind)'),
    (vm, 'data class ManageCategories(val kind: MediaKind) : Screen'),
    (vm, 'hiddenCategoryIds: Set<String> = emptySet()'),
    (vm, 'fun setCategoryVisible(kind: MediaKind, categoryId: String, visible: Boolean)'),
    (screens, 'V093ContinueLabel(c)'),
    (hub, 'infoByKey = continueItems.associate'),
    (hub, 'it.id !in u.hiddenCategoryIds'),
    (live, 'u.hiddenCategoryIds'),
    (manager, 'Nicht benötigte Kategorien kannst du hier ausblenden'),
    (app, 'is Screen.ManageCategories -> V093CategoryVisibilityScreen'),
    (player, 'var playbackPositionMs by remember(item.resumeKey) { mutableLongStateOf(0L) }'),
    (player, 'if (item.kind != MediaKind.LIVE && controls)'),
    (player, 'V093FormatTime(position)'),
    (player, 'V093RemainingMinutes(position, duration)'),
    (player, 'useController = item.kind != MediaKind.LIVE && !isTv'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.3 marker missing in {path}: {marker}")

print("Android 0.9.3 Continue Watching, category visibility and VOD seek overlay applied")
