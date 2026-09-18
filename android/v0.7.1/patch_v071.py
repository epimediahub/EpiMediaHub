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
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace missing: {signature}")


# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
build = root / "app/build.gradle.kts"
s = build.read_text()
require_once(s, 'versionCode = 700', 'v0.7.0 versionCode')
require_once(s, 'versionName = "0.7.0"', 'v0.7.0 versionName')
s = s.replace('versionCode = 700', 'versionCode = 701', 1)
s = s.replace('versionName = "0.7.0"', 'versionName = "0.7.1"', 1)

# LibVLC is used only for Live variants explicitly labelled RAW/HEVC/H265.
# Those provider labels are a practical signal for streams whose audio track
# is not decoded by the device's MediaCodec path. Keep ExoPlayer as default.
dep_anchor = '    implementation("androidx.media3:media3-ui:1.4.1")\n'
require_once(s, dep_anchor, 'Media3 UI dependency')
s = s.replace(
    dep_anchor,
    dep_anchor + '    implementation("org.videolan.android:libvlc-all:3.7.6")\n',
    1,
)
build.write_text(s)

home = java / "ui/V070Home.kt"
hs = home.read_text()
if "0.7.0" not in hs:
    raise SystemExit("visible v0.7.0 marker missing")
home.write_text(hs.replace("0.7.0", "0.7.1"))

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.0", "EpiMediaHub-Android/0.7.1"))


# ---------------------------------------------------------------------------
# Movie/series TV hub: persistent left category rail while retaining the
# Netflix-style rows on the right. Clicking a rail entry scrolls the same
# cinematic page to that category instead of leaving the hub.
# ---------------------------------------------------------------------------
hub = java / "ui/V060CinematicHub.kt"
s = hub.read_text()

if 'import androidx.compose.animation.core.FastOutSlowInEasing\n' not in s:
    s = s.replace(
        'import androidx.compose.animation.core.animateFloatAsState\n',
        'import androidx.compose.animation.core.FastOutSlowInEasing\n'
        'import androidx.compose.animation.core.animateFloatAsState\n'
        'import androidx.compose.animation.core.tween\n',
        1,
    )
if 'import androidx.compose.foundation.lazy.itemsIndexed\n' not in s:
    s = s.replace(
        'import androidx.compose.foundation.lazy.items\n',
        'import androidx.compose.foundation.lazy.items\n'
        'import androidx.compose.foundation.lazy.itemsIndexed\n'
        'import androidx.compose.foundation.lazy.rememberLazyListState\n',
        1,
    )
if 'import kotlinx.coroutines.launch\n' not in s:
    s = s.replace(
        'import de.epimediahub.app.model.MediaKind\n',
        'import de.epimediahub.app.model.MediaKind\n'
        'import kotlinx.coroutines.launch\n',
        1,
    )

a, b = function_span(s, "fun V060CinematicHubScreen(vm: MainViewModel, kind: MediaKind, accent: Color, isTv: Boolean)")
new_screen = r'''fun V060CinematicHubScreen(vm: MainViewModel, kind: MediaKind, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val recent = u.recentlyWatched.filter { it.kind == kind || (kind == MediaKind.SERIES && it.kind == MediaKind.EPISODE) }
    val continueItems = u.continueWatching.filter { it.media.kind == kind || (kind == MediaKind.SERIES && it.media.kind == MediaKind.EPISODE) }
    val visibleCategories = u.categories.filter { u.catalogRows[it.id].orEmpty().isNotEmpty() }
    val firstCatalog = visibleCategories.asSequence().mapNotNull { u.catalogRows[it.id]?.firstOrNull() }.firstOrNull()
    val hero = recent.firstOrNull() ?: firstCatalog
    val contentState = rememberLazyListState()
    val scope = rememberCoroutineScope()
    var selectedCategoryId by remember(kind, u.active?.id) { mutableStateOf("") }
    val categoryStartIndex =
        (if (hero != null) 1 else 0) +
        1 +
        (if (continueItems.isNotEmpty()) 1 else 0) +
        (if (recent.isNotEmpty()) 1 else 0)

    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(if (kind == MediaKind.MOVIE) "FILME" else "SERIEN", R.drawable.brand_header, { vm.back() })
        if (u.loading || u.catalogRowsLoading) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(Modifier.size(if (isTv) 46.dp else 38.dp), color = accent, strokeWidth = 3.dp)
                    Spacer(Modifier.height(16.dp))
                    Text(
                        if (kind == MediaKind.MOVIE) "Filme werden geladen …" else "Serien werden geladen …",
                        color = Color.White,
                        fontSize = if (isTv) 20.sp else 17.sp,
                        fontWeight = FontWeight.Black
                    )
                    Spacer(Modifier.height(6.dp))
                    Text("Katalog wird vorbereitet", color = Color.White.copy(.66f), fontSize = if (isTv) 14.sp else 12.sp)
                }
            }
        } else {
            LoadingOrError(false, u.error)
            Row(Modifier.fillMaxSize()) {
                if (isTv) {
                    V071CategoryRail(
                        categories = visibleCategories,
                        selectedId = selectedCategoryId,
                        accent = accent,
                        onOverview = {
                            selectedCategoryId = ""
                            scope.launch { contentState.animateScrollToItem(0) }
                        },
                        onCategory = { index, category ->
                            selectedCategoryId = category.id
                            scope.launch { contentState.animateScrollToItem(categoryStartIndex + index) }
                        }
                    )
                    Box(Modifier.fillMaxHeight().width(1.dp).background(Color.White.copy(.10f)))
                }

                LazyColumn(
                    modifier = Modifier.weight(1f).fillMaxHeight(),
                    state = contentState,
                    contentPadding = PaddingValues(bottom = 34.dp),
                    verticalArrangement = Arrangement.spacedBy(if (isTv) 21.dp else 15.dp)
                ) {
                    hero?.let { featured ->
                        item(key = "hero:" + featured.resumeKey) {
                            V060Hero(featured, accent, isTv) { vm.navigate(Screen.Details(featured)) }
                        }
                    }
                    item(key = "actions") {
                        Row(
                            Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal = if (isTv) 28.dp else 14.dp),
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
                    items(visibleCategories, key = { "category:" + it.id }) { category ->
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
                    }
                }
            }
        }
    }
}'''
s = s[:a] + new_screen + s[b:]

hero_signature = '@Composable\nprivate fun V060Hero('
if hero_signature not in s:
    raise SystemExit("V060Hero insertion anchor missing")
rail = r'''@Composable
private fun V071CategoryRail(
    categories: List<MediaCategory>,
    selectedId: String,
    accent: Color,
    onOverview: () -> Unit,
    onCategory: (Int, MediaCategory) -> Unit
) {
    Column(
        Modifier.width(226.dp).fillMaxHeight().background(Color.Black.copy(.18f))
            .padding(start = 16.dp, end = 12.dp, top = 10.dp, bottom = 14.dp)
    ) {
        Text("KATEGORIEN", color = Color.White.copy(.55f), fontSize = 11.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(horizontal = 10.dp, vertical = 8.dp))
        LazyColumn(
            Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(5.dp),
            contentPadding = PaddingValues(bottom = 18.dp)
        ) {
            item(key = "rail-overview") {
                V071CategoryRailItem("Übersicht", selectedId.isBlank(), accent, onOverview)
            }
            itemsIndexed(categories, key = { _, category -> "rail:" + category.id }) { index, category ->
                V071CategoryRailItem(category.name, selectedId == category.id, accent) {
                    onCategory(index, category)
                }
            }
        }
    }
}

@Composable
private fun V071CategoryRailItem(title: String, selected: Boolean, accent: Color, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(11.dp)
    Surface(
        modifier = Modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
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
}

'''
s = s.replace(hero_signature, rail + hero_signature, 1)

# Smoother, smaller focus motion: no 10% zoom/big shadow jump on every D-pad move.
old_scale = '    val scale by animateFloatAsState(if (focused) 1.10f else 1f, spring(stiffness = 360f), label = "posterFocus")\n'
new_scale = '    val scale by animateFloatAsState(if (focused) 1.04f else 1f, tween(durationMillis = 145, easing = FastOutSlowInEasing), label = "posterFocus")\n'
require_once(s, old_scale, 'poster scale')
s = s.replace(old_scale, new_scale, 1)
old_visual = '            .shadow(if (focused) 26.dp else 2.dp, shape).onFocusChanged { focused = it.isFocused }.focusable()\n            .clip(shape).background(Color(0xFF111A26)).border(if (focused) 3.dp else 1.dp, if (focused) accent else Color.White.copy(.10f), shape).clickable(onClick = onClick)\n'
new_visual = '            .shadow(if (focused) 14.dp else 2.dp, shape).onFocusChanged { focused = it.isFocused }.focusable()\n            .clip(shape).background(Color(0xFF111A26)).border(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.10f), shape).clickable(onClick = onClick)\n'
require_once(s, old_visual, 'poster shadow/border')
s = s.replace(old_visual, new_visual, 1)
hub.write_text(s)


# ---------------------------------------------------------------------------
# Live RAW/HEVC audio compatibility.
#
# HEVC itself is a video codec/provider label, not an audio codec. On the
# affected variants the muxed audio can still require codecs unavailable in a
# device's MediaCodec path. Keep ExoPlayer everywhere else, enable decoder
# fallback, and route only explicitly labelled RAW/HEVC/H265 Live variants
# through packaged LibVLC for broader audio/video decoding support.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()

if 'import android.net.Uri\n' not in s:
    s = s.replace('import android.os.Looper\n', 'import android.os.Looper\nimport android.net.Uri\n', 1)
if 'import androidx.media3.exoplayer.DefaultRenderersFactory\n' not in s:
    s = s.replace('import androidx.media3.exoplayer.DefaultLoadControl\n', 'import androidx.media3.exoplayer.DefaultLoadControl\nimport androidx.media3.exoplayer.DefaultRenderersFactory\n', 1)
if 'import androidx.compose.ui.focus.FocusRequester\n' not in s:
    focus_anchor = 'import androidx.compose.ui.input.key.onPreviewKeyEvent\n'
    require_once(s, focus_anchor, 'Player focus import anchor')
    s = s.replace(focus_anchor, 'import androidx.compose.ui.focus.FocusRequester\nimport androidx.compose.ui.focus.focusRequester\n' + focus_anchor, 1)
if 'import org.videolan.libvlc.LibVLC\n' not in s:
    import_anchor = 'import java.net.URLDecoder\n'
    require_once(s, import_anchor, 'Player URLDecoder import')
    s = s.replace(
        import_anchor,
        import_anchor +
        'import org.videolan.libvlc.LibVLC\n'
        'import org.videolan.libvlc.Media\n'
        'import org.videolan.libvlc.MediaPlayer as VlcMediaPlayer\n'
        'import org.videolan.libvlc.util.VLCVideoLayout\n',
        1,
    )

old_builder = '''        val exoBuilder = ExoPlayer.Builder(context)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
'''
new_builder = '''        val renderersFactory = DefaultRenderersFactory(context)
            .setEnableDecoderFallback(true)
        val exoBuilder = ExoPlayer.Builder(context, renderersFactory)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
'''
require_once(s, old_builder, 'ExoPlayer builder')
s = s.replace(old_builder, new_builder, 1)

player_anchor = '''@OptIn(UnstableApi::class)
@Composable
fun PlayerScreen'''
require_once(s, player_anchor, 'PlayerScreen composable anchor')
vlc_fallback = r'''private fun V071UseVlcLiveFallback(item: MediaEntry): Boolean {
    if (item.kind != MediaKind.LIVE) return false
    val label = item.name.trim()
    return Regex("(?i)(?:\bRAW\b|\bHEVC\b|\bH\.?265\b)\s*$").containsMatchIn(label)
}

@Composable
private fun V071VlcLivePlayer(
    vm: MainViewModel,
    item: MediaEntry,
    channelList: List<MediaEntry>,
    accent: Color,
    isTv: Boolean
) {
    val context = LocalContext.current
    val u by vm.ui.collectAsState()
    val playbackUrls = remember(item.resumeKey, item.streamUrl, u.active?.id, item.sourceProfileId) { vm.playbackUrls(item) }
    val request = remember(item.resumeKey, playbackUrls) {
        parseIptvHttpRequest(playbackUrls.firstOrNull().orEmpty().ifBlank { item.streamUrl })
    }
    val focusRequester = remember(item.resumeKey) { FocusRequester() }
    val videoLayout = remember(item.resumeKey) { VLCVideoLayout(context) }
    val libVlc = remember(item.resumeKey) {
        LibVLC(context, arrayListOf("--network-caching=900", "--clock-jitter=0", "--clock-synchro=0"))
    }
    val vlcPlayer = remember(item.resumeKey) { VlcMediaPlayer(libVlc) }
    var controls by remember(item.resumeKey) { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()

    fun switchLiveBy(direction: Int): Boolean {
        val channels = channelList.filter { it.kind == MediaKind.LIVE }
        if (channels.isEmpty()) return true
        val currentIndex = channels.indexOfFirst { it.resumeKey == item.resumeKey }
        if (currentIndex < 0) return true
        val nextIndex = (currentIndex + direction + channels.size) % channels.size
        controls = true
        vm.switchLiveChannel(channels[nextIndex], channels)
        return true
    }

    BackHandler { vm.back() }

    LaunchedEffect(item.resumeKey) {
        runCatching { focusRequester.requestFocus() }
    }
    LaunchedEffect(item.resumeKey, controls) {
        if (controls) {
            delay(4500)
            controls = false
        }
    }

    DisposableEffect(item.resumeKey, request.url) {
        playbackError = ""
        vlcPlayer.attachViews(videoLayout, null, false, false)
        val failure = runCatching {
            if (request.url.isBlank()) error("Leere Stream-Adresse")
            val media = Media(libVlc, Uri.parse(request.url))
            try {
                media.setHWDecoderEnabled(true, false)
                media.addOption(":network-caching=900")
                media.addOption(":http-user-agent=" + request.userAgent.ifBlank { "VLC/3.0.21 LibVLC/3.0.21" })
                if (request.referer.isNotBlank()) media.addOption(":http-referrer=" + request.referer)
                vlcPlayer.media = media
            } finally {
                media.release()
            }
            vlcPlayer.play()
        }.exceptionOrNull()
        if (failure != null) playbackError = "Kompatibilitätsplayer konnte den Live-Stream nicht starten."

        onDispose {
            runCatching { vlcPlayer.stop() }
            runCatching { vlcPlayer.detachViews() }
            runCatching { vlcPlayer.release() }
            runCatching { libVlc.release() }
        }
    }

    Box(
        Modifier.fillMaxSize()
            .focusRequester(focusRequester)
            .focusable()
            .onPreviewKeyEvent {
                if (it.type != androidx.compose.ui.input.key.KeyEventType.KeyDown) return@onPreviewKeyEvent false
                when (it.nativeKeyEvent.keyCode) {
                    KeyEvent.KEYCODE_DPAD_UP -> switchLiveBy(-1)
                    KeyEvent.KEYCODE_DPAD_DOWN -> switchLiveBy(1)
                    KeyEvent.KEYCODE_DPAD_LEFT, KeyEvent.KEYCODE_DPAD_RIGHT -> true
                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                        controls = !controls
                        true
                    }
                    else -> false
                }
            }
    ) {
        AndroidView(
            factory = { videoLayout },
            modifier = Modifier.fillMaxSize()
        )
        if (controls) {
            Surface(
                modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(horizontal = 24.dp, vertical = 26.dp),
                color = Color(0xEA0A0F17),
                shape = MaterialTheme.shapes.large,
                border = androidx.compose.foundation.BorderStroke(1.dp, accent.copy(alpha = .85f))
            ) {
                Row(
                    modifier = Modifier.fillMaxWidth().height(92.dp).padding(horizontal = 18.dp, vertical = 12.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Surface(
                        modifier = Modifier.width(132.dp).fillMaxHeight(),
                        color = Color.White,
                        shape = MaterialTheme.shapes.medium
                    ) {
                        if (item.image.isNotBlank()) {
                            AsyncImage(
                                model = item.image,
                                contentDescription = item.name,
                                modifier = Modifier.fillMaxSize().padding(8.dp),
                                contentScale = ContentScale.Fit
                            )
                        } else {
                            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                Text("TV", color = accent, fontWeight = FontWeight.Black, fontSize = 24.sp)
                            }
                        }
                    }
                    Spacer(Modifier.width(18.dp))
                    Column(Modifier.weight(1f)) {
                        Text(item.name, color = Color.White, fontWeight = FontWeight.Black, fontSize = 22.sp, maxLines = 1)
                        Text(
                            if (nowProgramme.isNotBlank()) nowProgramme else "Jetzt live",
                            color = Color.White.copy(alpha = .75f),
                            fontSize = 14.sp,
                            maxLines = 1
                        )
                    }
                    Surface(color = accent.copy(alpha = .18f), shape = MaterialTheme.shapes.small) {
                        Text(
                            if (isTv) "LIVE · KOMPATIBILITÄT" else "LIVE",
                            color = accent,
                            fontWeight = FontWeight.Black,
                            fontSize = 11.sp,
                            modifier = Modifier.padding(horizontal = 12.dp, vertical = 7.dp)
                        )
                    }
                }
            }
        }
        if (playbackError.isNotBlank()) {
            Surface(
                modifier = Modifier.align(Alignment.Center).padding(28.dp),
                color = Color(0xE6181B22),
                shape = MaterialTheme.shapes.medium
            ) {
                Text(playbackError, color = Color.White, fontWeight = FontWeight.Bold, modifier = Modifier.padding(18.dp))
            }
        }
    }
}

@OptIn(UnstableApi::class)
@Composable
fun PlayerScreen'''
s = s.replace(player_anchor, vlc_fallback, 1)

signature = 'fun PlayerScreen(vm: MainViewModel, item: MediaEntry, episodeList: List<MediaEntry>, accent: Color, isTv: Boolean) {\n'
require_once(s, signature, 'PlayerScreen signature')
s = s.replace(
    signature,
    signature +
    '    if (V071UseVlcLiveFallback(item)) {\n'
    '        V071VlcLivePlayer(vm, item, episodeList, accent, isTv)\n'
    '        return\n'
    '    }\n',
    1,
)
player.write_text(s)


# Final markers.
checks = [
    (build, 'versionName = "0.7.1"'),
    (build, 'versionCode = 701'),
    (build, 'org.videolan.android:libvlc-all:3.7.6'),
    (hub, 'private fun V071CategoryRail('),
    (hub, 'contentState.animateScrollToItem(categoryStartIndex + index)'),
    (hub, '1.04f else 1f'),
    (hub, 'durationMillis = 145'),
    (player, 'private fun V071UseVlcLiveFallback(item: MediaEntry)'),
    (player, 'VLCVideoLayout(context)'),
    (player, 'DefaultRenderersFactory(context)'),
    (player, 'setEnableDecoderFallback(true)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.1 marker {marker} in {path}")

print("Android v0.7.1 category rail, smoother poster focus and RAW/HEVC Live audio compatibility applied")
