#!/usr/bin/env python3
"""Complete Back restoration on the active routes without dropping existing actions."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"


def replace(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def span(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"unclosed function: {signature}")


def edit(relative, signature, transform):
    path = java / relative
    text = path.read_text()
    a, b = span(text, signature)
    path.write_text(text[:a] + transform(text[a:b]) + text[b:])


# All routes retain saveable menu state and list offsets.
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
s = replace(s, "    val scope = rememberCoroutineScope()\n", """    val scope = rememberCoroutineScope()
    val menuStates = androidx.compose.runtime.saveable.rememberSaveableStateHolder()
    val menuStateKey = u.active?.id.orEmpty() + ":" + u.contentFilterKind?.name.orEmpty() + ":" +
        u.screen.javaClass.simpleName + ":" + when (val screen = u.screen) {
            is Screen.Categories -> screen.kind.name
            is Screen.Items -> screen.kind.name + ":" + screen.category.id
            is Screen.Episodes -> screen.series.resumeKey
            is Screen.Details -> screen.item.resumeKey
            is Screen.Player -> screen.item.resumeKey
            is Screen.ManageCategories -> screen.kind.name
            is ParityMediathekDirectory -> screen.countryId
            is ParityMediathekList -> screen.providerId
            is ParityMediathekDetail -> screen.item.id
            else -> ""
        }
""", "route state holder")
a, b = span(s, "            when (val s = u.screen)")
s = s[:a] + "            menuStates.SaveableStateProvider(menuStateKey) {\n" + s[a:b] + "\n            }" + s[b:]
app.write_text(s)


# The app routes to V070PlaylistsScreen, rather than the legacy PlaylistsScreen.
def playlists(s):
    s = replace(s, "    val firstFocus = remember { FocusRequester() }", """    val memoryKey = "playlists-active"
    val state = v111RememberLazyListState(memoryKey)
    val firstFocus = remember { FocusRequester() }
    val rememberedIndex = u.playlists.indexOfFirst { it.id == V111MenuMemory.id(memoryKey) }
        .takeIf { it >= 0 } ?: V111MenuMemory.index(memoryKey).coerceIn(0, (u.playlists.size - 1).coerceAtLeast(0))""", "playlist selection")
    s = replace(s, "if (u.playlists.isNotEmpty()) { delay(90); runCatching { firstFocus.requestFocus() } }", """if (u.playlists.isNotEmpty()) {
            state.scrollToItem(rememberedIndex)
            delay(90)
            runCatching { firstFocus.requestFocus() }
        }""", "playlist Back focus")
    s = replace(s, "                Modifier.fillMaxSize().padding(horizontal = 42.dp, vertical = 14.dp),", "                state = state,\n                modifier = Modifier.fillMaxSize().padding(horizontal = 42.dp, vertical = 14.dp),", "playlist list state")
    s = replace(s, "modifier = if (index == 0) Modifier.focusRequester(firstFocus) else Modifier,", """modifier = Modifier
                            .then(if (index == rememberedIndex) Modifier.focusRequester(firstFocus) else Modifier)
                            .onFocusChanged { if (it.hasFocus) V111MenuMemory.remember(memoryKey, index, playlist.id) },""", "playlist focus memory")
    s = replace(s, "onSelect = { vm.selectPlaylist(playlist.id) },", "onSelect = { V111MenuMemory.remember(memoryKey, index, playlist.id); vm.selectPlaylist(playlist.id) },", "playlist click memory")
    return s


edit("ui/V070Playlists.kt", "fun V070PlaylistsScreen(", playlists)


# Add an optional modifier to shared episode/continue-watching cards.
cards = java / "ui/Screens.kt"
s = cards.read_text()
s = replace(s, "import androidx.compose.foundation.lazy.grid.items as gridItems\n", "import androidx.compose.foundation.lazy.grid.items as gridItems\nimport androidx.compose.foundation.lazy.grid.itemsIndexed as gridItemsIndexed\n", "indexed media grid import")
s = replace(s, 'fun MediaCard(media:MediaEntry,accent:Color,subtitle:String="",progress:Float?=null,onClick:()->Unit)', 'fun MediaCard(media:MediaEntry,accent:Color,subtitle:String="",progress:Float?=null,modifier:Modifier=Modifier,onClick:()->Unit)', "media card modifier")
s = replace(s, "    Column(Modifier.height(280.dp).onFocusChanged", "    Column(modifier.height(280.dp).onFocusChanged", "media card focus modifier")
cards.write_text(s)


def episodes(s):
    s = replace(s, 'state=v111RememberLazyGridState(episodeMemoryKey + ":grid"),', 'state=v111RememberLazyGridState(episodeMemoryKey + ":grid:" + selectedSeason),', "episode season grid")
    s = replace(s, "                gridItems(visibleEpisodes,key={it.resumeKey}){e->", "                gridItemsIndexed(visibleEpisodes,key={_, it->it.resumeKey}){index,e->", "episode indexed cards")
    s = replace(s, "                        onClick={vm.play(e,orderedEpisodes)}", """                        modifier=v111RememberFocus(episodeMemoryKey + ":grid:" + selectedSeason, e.resumeKey, index, isTv),
                        onClick={
                            V111MenuMemory.remember(episodeMemoryKey + ":grid:" + selectedSeason, index, e.resumeKey)
                            vm.play(e,orderedEpisodes)
                        }""", "episode focus")
    return s


edit("ui/Screens.kt", "fun EpisodesScreen(", episodes)


def continuing(s):
    s = replace(s, "    BackHandler{vm.back()}", '    val memoryKey = "continue-watching:" + u.active?.id.orEmpty() + ":" + u.contentFilterKind?.name.orEmpty()\n    BackHandler{vm.back()}', "continue key")
    s = replace(s, "                GridCells.Fixed(if(isTv)5 else 2),\n                Modifier.fillMaxSize().padding(14.dp),", "                columns=GridCells.Fixed(if(isTv)5 else 2),\n                state=v111RememberLazyGridState(memoryKey),\n                modifier=Modifier.fillMaxSize().padding(14.dp),", "continue grid")
    s = replace(s, "                gridItems(u.continueWatching,key={it.media.resumeKey}){c->", "                gridItemsIndexed(u.continueWatching,key={_, it->it.media.resumeKey}){index,c->", "continue indexed cards")
    s = replace(s, "MediaCard(c.media,accent,V093ContinueLabel(c),c.progress){vm.play(c.media)}", "MediaCard(c.media,accent,V093ContinueLabel(c),c.progress,modifier=v111RememberFocus(memoryKey,c.media.resumeKey,index,isTv)){vm.play(c.media)}", "continue focus")
    return s


edit("ui/Screens.kt", "fun ContinueWatchingScreen(", continuing)


hub = java / "ui/V060CinematicHub.kt"
s = hub.read_text()
s = replace(s, "import androidx.compose.foundation.lazy.grid.items as gridItems\n", "import androidx.compose.foundation.lazy.grid.items as gridItems\nimport androidx.compose.foundation.lazy.grid.itemsIndexed as gridItemsIndexed\n", "indexed recent grid import")
hub.write_text(s)


def recently(s):
    s = replace(s, '    BackHandler { vm.back() }', '    val memoryKey = "recently-watched:" + u.active?.id.orEmpty() + ":" + kind?.name.orEmpty()\n    BackHandler { vm.back() }', "recent key")
    s = replace(s, 'state = v111RememberLazyGridState("recently-watched"),', 'state = v111RememberLazyGridState(memoryKey),', "recent grid key")
    s = replace(s, "gridItems(list, key = { it.resumeKey }) { item -> V060Poster(item, accent, isTv)", "gridItemsIndexed(list, key = { _, item -> item.resumeKey }) { index, item -> V060Poster(item, accent, isTv, rememberedFocus = v111RememberFocus(memoryKey, item.resumeKey, index, isTv))", "recent focus")
    return s


edit("ui/V060CinematicHub.kt", "fun V060RecentlyWatchedScreen(", recently)


visibility_path = java / "ui/V093CategoryVisibility.kt"
s = visibility_path.read_text()
s = replace(s, "import androidx.compose.foundation.lazy.items\n", "import androidx.compose.foundation.lazy.itemsIndexed\n", "indexed category visibility import")
visibility_path.write_text(s)


def visibility(s):
    s = replace(s, "    BackHandler { vm.back() }", '    val memoryKey = "category-visibility:" + u.active?.id.orEmpty() + ":" + kind.name\n    BackHandler { vm.back() }', "visibility key")
    s = replace(s, "                Modifier.fillMaxSize(),", "                state = v111RememberLazyListState(memoryKey),\n                modifier = Modifier.fillMaxSize(),", "visibility list")
    s = replace(s, "                items(categories, key = { it.id }) { category ->", "                itemsIndexed(categories, key = { _, it -> it.id }) { index, category ->", "visibility indexed rows")
    s = replace(s, "modifier = Modifier.fillMaxWidth()", "modifier = v111RememberFocus(memoryKey, category.id, index, isTv).fillMaxWidth()", "visibility focus")
    return s


edit("ui/V093CategoryVisibility.kt", "fun V093CategoryVisibilityScreen(", visibility)


# Media library rows already keep their selected ID in the ViewModel. Extend
# focus restoration from Live TV to films and series too.
def library(s):
    s = replace(s, "    BackHandler{vm.back()}", '    val memoryKey = "library:" + u.active?.id.orEmpty() + ":" + kind.name + ":" + cat.id\n    BackHandler{vm.back()}', "library key")
    s = replace(s, "MediaInfoRow(detail,u.detailLoading.contains(m.resumeKey),accent,true){", "MediaInfoRow(detail,u.detailLoading.contains(m.resumeKey),accent,true,modifier=v111RememberFocus(memoryKey,m.resumeKey,index,isTv)){", "library focus")
    return s


edit("ui/Screens.kt", "fun ItemsScreen(", library)


# Exact focus on Mediathek result cards, including a retained search query.
def mediathek(s):
    s = replace(s, 'var query by remember { mutableStateOf("") }', 'var query by androidx.compose.runtime.saveable.rememberSaveable(providerId) { mutableStateOf("") }', "mediathek query")
    s = replace(s, 'var submitted by remember { mutableStateOf("") }', 'var submitted by androidx.compose.runtime.saveable.rememberSaveable(providerId) { mutableStateOf("") }', "mediathek submitted query")
    s = replace(s, "                gridItems(entries, key = { it.id }) { media ->\n                    V042MediathekCard(media, accent, isTv)", '                gridItemsIndexed(entries, key = { _, it -> it.id }) { index, media ->\n                    V042MediathekCard(media, accent, isTv, modifier = v111RememberFocus("mediathek-list:" + providerId, media.id, index, isTv))', "mediathek focus")
    return s


edit("ui/ParityScreens.kt", "fun ParityMediathekListScreen(", mediathek)
def mediathek_card(s):
    s = replace(s, "    isTv: Boolean,\n    onClick: () -> Unit", "    isTv: Boolean,\n    modifier: Modifier = Modifier,\n    onClick: () -> Unit", "mediathek card modifier")
    return replace(s, "    Column(\n        Modifier\n", "    Column(\n        modifier\n", "mediathek card focus modifier")
edit("ui/ParityScreens.kt", "private fun V042MediathekCard(", mediathek_card)


# Theme choice retains its focused preview even when selecting a skin rebuilds
# the theme backdrop around the screen.
def theme_preview(s):
    s = replace(s, "            .onFocusChanged { focused = it.isFocused }", '            .then(v111RememberFocus("themes-preview:" + theme.group, theme.id, 0, isTv))\n            .onFocusChanged { focused = it.isFocused }', "theme preview focus")
    return s
edit("ui/V079Themes.kt", "private fun V099ThemePreview(", theme_preview)

# Returning from the private category browser must stay in the overview.
themes = java / "ui/V079Themes.kt"
s = themes.read_text()
old = "if (selectedGroupId != null) selectedGroupId = null else vm.back()"
if s.count(old) != 2:
    raise SystemExit("theme Back actions changed")
s = s.replace(old, 'if (selectedGroupId != null) { selectedGroupId = null; V111MenuMemory.rememberText("themes-group", "") } else vm.back()')
themes.write_text(s)


# The playlist shortcut in the home header also restores its own focus.
def home_header(s):
    return replace(s, "                        .onFocusChanged { playlistFocused = it.isFocused }", '                        .then(v111RememberFocus("home", "playlist-switch", 6, isTv))\n                        .onFocusChanged { playlistFocused = it.isFocused }', "home playlist shortcut focus")
edit("ui/V083Home.kt", "private fun V083Header(", home_header)


def epg(s):
    s = replace(s, "    val profile = u.active", '    val profile = u.active\n    val memoryKey = "epg:" + profile?.id.orEmpty() + ":" + category.id', "EPG state key")
    s = replace(s, "            Modifier.fillMaxSize().padding(horizontal = if (isTv) 24.dp else 10.dp, vertical = 8.dp),", "            state = v111RememberLazyListState(memoryKey),\n            modifier = Modifier.fillMaxSize().padding(horizontal = if (isTv) 24.dp else 10.dp, vertical = 8.dp),", "EPG list state")
    s = replace(s, "ParityEpgChannel(vm, profile, channel, window, now, accent)", "ParityEpgChannel(vm, profile, channel, window, now, accent, memoryKey)", "EPG focus scope")
    return s
edit("ui/ParityScreens.kt", "fun ParityEpgGridScreen(", epg)


def epg_channel(s):
    s = replace(s, "    accent: Color\n", '    accent: Color,\n    memoryKey: String\n', "EPG channel focus key")
    s = replace(s, "    GlassPanel(Modifier.fillMaxWidth())", "    val isTv = v111IsTvDevice()\n    GlassPanel(Modifier.fillMaxWidth())", "EPG TV focus")
    s = replace(s, "                        Modifier.fillMaxWidth()\n                            .onFocusChanged", '                        Modifier.fillMaxWidth()\n                            .then(v111RememberFocus(memoryKey, channel.id + ":" + event.start, 0, isTv && canPlay))\n                            .onFocusChanged', "EPG event focus")
    return s
edit("ui/ParityScreens.kt", "private fun ParityEpgChannel(", epg_channel)

print("Android 1.0.11 active playlists, episodes, history, Mediathek and route state verified")
