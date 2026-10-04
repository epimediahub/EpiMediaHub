#!/usr/bin/env python3
"""Customer PIN gates, opaque loading panels, bounded catalogues and SmartTube cold-start preparation."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent

def replace(path, old, new, count=1):
    source = path.read_text()
    assert source.count(old) == count, f'{path}: {source.count(old)} anchors, expected {count}: {old[:100]}'
    path.write_text(source.replace(old, new))

def between(path, first, last, new):
    source = path.read_text()
    start, end = source.index(first), source.index(last, source.index(first))
    path.write_text(source[:start] + new + source[end:])

replace(root / 'app/build.gradle.kts', 'versionCode = 1027', 'versionCode = 1028')
replace(root / 'app/build.gradle.kts', 'versionName = "1.0.27"', 'versionName = "1.0.28"')
for path in java.rglob('*.kt'):
    source = path.read_text()
    if '1.0.27' in source: path.write_text(source.replace('1.0.27', '1.0.28'))

for package, names in {
    'data': ['V128ParentalControl.kt', 'V128TimedCache.kt'],
    'ui': ['V128ParentalUi.kt', 'V128SmartTubeClientStore.kt', 'V128SmartTubePlayerPool.kt']
}.items():
    for name in names: shutil.copyfile(here / name, java / package / name)

models = java / 'model/Models.kt'
replace(models, 'data class MediaCategory(val id: String, val name: String)',
    'data class MediaCategory(val id: String, val name: String, val adult: Boolean = false)')
replace(models, '    val tmdbId: String = ""\n',
    '    val tmdbId: String = "",\n    val adult: Boolean = false,\n    val ageRating: Int = -1,\n    val categoryName: String = ""\n')

prefs = java / 'data/PrefsRepository.kt'
replace(prefs, 'put("tmdbId",m.tmdbId)',
    'put("tmdbId",m.tmdbId);put("adult",m.adult);put("ageRating",m.ageRating);put("categoryName",m.categoryName)')
replace(prefs, 'tmdbId=o.optString("tmdbId")',
    'tmdbId=o.optString("tmdbId"),adult=o.optBoolean("adult"),ageRating=o.optInt("ageRating",-1),categoryName=o.optString("categoryName")')

client = java / 'data/XtreamClient.kt'
replace(client, 'MediaCategory(o.optString("category_id"), o.optString("category_name", "Andere"))',
    'MediaCategory(o.optString("category_id"), o.optString("category_name", "Andere"), V128AdultContent.providerAdult(o) || V128AdultContent.providerAge(o) >= 18 || V128AdultContent.marked(o.optString("category_name")))')
replace(client, '                                kind = kind,',
    '                                kind = kind,\n                                adult = V128AdultContent.providerAdult(o),\n                                ageRating = V128AdultContent.providerAge(o),', count=3)
replace(client, '        return item.copy(\n            name =',
    '''        return item.copy(
            adult = item.adult || V128AdultContent.providerAdult(info) || V128AdultContent.providerAdult(root.optJSONObject("movie_data") ?: JSONObject()),
            ageRating = maxOf(item.ageRating, V128AdultContent.providerAge(info), V128AdultContent.providerAge(root.optJSONObject("movie_data") ?: JSONObject())),
            name =''', count=2)
replace(client, '                    kind = MediaKind.EPISODE,',
    '''                    kind = MediaKind.EPISODE,
                    adult = V128AdultContent.providerAdult(seriesInfo) || V128AdultContent.providerAdult(o) || V128AdultContent.providerAdult(info),
                    ageRating = maxOf(V128AdultContent.providerAge(seriesInfo), V128AdultContent.providerAge(o), V128AdultContent.providerAge(info)),
                    categoryName = seriesInfo.optString("category_name"),''')

parser = java / 'data/M3uParser.kt'
replace(parser, '                            categoryId = group,',
    '''                            categoryId = group,
                            categoryName = group,
                            adult = V128AdultContent.marked(group) || V128AdultContent.marked(name) ||
                                attr(meta, "is_adult").lowercase() in setOf("1", "true", "yes"),
                            ageRating = V128AdultContent.providerAge(org.json.JSONObject().put("content_rating", attr(meta, "tvg-rating"))),''')

vm = java / 'MainViewModel.kt'
replace(vm, '    data object Settings : Screen', '    data object Settings : Screen\n    data object ParentalSettings : Screen')
replace(vm, '    val remoteMaintenanceUnlocked: Boolean = false\n',
    '''    val remoteMaintenanceUnlocked: Boolean = false,
    val parentalSettings: V128ParentalSettings = V128ParentalSettings(),
    val parentalMenuUnlocked: Boolean = false,
    val parentalGranted: Set<String> = emptySet(),
    val parentalBusy: Boolean = false,
    val parentalChecking: Boolean = false,
    val pinPrompt: V128PinPrompt? = null,
    val pinError: String = ""
''')
replace(vm, '    private val prefs = PrefsRepository(app)',
    '    private val prefs = PrefsRepository(app)\n    private val parental = V128ParentalControl(app)')
replace(vm, '            remoteMaintenanceUnlocked = prefs.remoteMaintenanceUnlocked()',
    '            remoteMaintenanceUnlocked = prefs.remoteMaintenanceUnlocked(),\n            parentalSettings = parental.settings()')
replace(vm, '    private val m3uCache = mutableMapOf<String, M3uParser.Result>()',
    '    private val m3uCache = V128TimedCache<M3uParser.Result>()')
replace(vm, '    private val xtreamLibraryCache = java.util.concurrent.ConcurrentHashMap<String, List<MediaEntry>>()',
    '    private val xtreamLibraryCache = V128TimedCache<List<MediaEntry>>()')
replace(vm, '    private var searchGeneration = 0L',
    '''    private var searchGeneration = 0L
    private val libraryCatalogCache = V128TimedCache<V128LibraryCatalog>()
    private var libraryLoadJob: kotlinx.coroutines.Job? = null
    private var libraryLoadGeneration = 0L

''' + (here / 'V128ViewModel.inc').read_text())
replace(vm, '    fun navigate(screen: Screen, remember: Boolean = true) {',
    '    fun navigate(screen: Screen, remember: Boolean = true) {\n        if (!allowParentalNavigation(screen, remember)) return')
replace(vm, '    fun back() {',
    '    fun back() {\n        contentAccessJob?.cancel()\n        set { it.copy(parentalChecking = false) }\n        parentalSettingsAuthorized = false')
replace(vm, '        set { it.copy(screen = s, error = "") }',
    '        navigate(s, remember = false)')
replace(vm, '        val list = prefs.loadPlaylists()\n        val active =',
    '''        val list = prefs.loadPlaylists()
        if (list != _ui.value.playlists) {
            m3uCache.clear(); xtreamLibraryCache.clear(); libraryCatalogCache.clear()
            parentalCategories.clear()
        }
        val active =''')
replace(vm, '''    fun refreshPlaylistsAtAppStart() {
        m3uCache.clear()
        xtreamLibraryCache.clear()
        refreshProfiles()
    }''',
    '''    fun refreshPlaylistsAtAppStart() {
        // Keep fresh, bounded catalogues on resume; changed playlists invalidate them in refreshProfiles.
        refreshProfiles()
    }''')
replace(vm, '        return m3uCache[p.id] ?: M3uParser.download(p.originalUrl).also { m3uCache[p.id] = it }',
    '        return m3uCache.getOrLoad(p.id + "|" + p.originalUrl.hashCode()) { M3uParser.download(p.originalUrl) }')
replace(vm, '        m3uCache.remove(id)', '        m3uCache.keys.removeAll { it.startsWith("$id|") }\n        libraryCatalogCache.keys.removeAll { it.startsWith("$id|") }')
between(vm, '    private fun xtreamLibrary(', '    private fun loadCategories(',
    '''    private fun xtreamLibrary(profile: PlaylistProfile, kind: MediaKind): List<MediaEntry> =
        xtreamLibraryCache.getOrLoad(catalogueKey(profile, kind)) {
            XtreamClient(profile).entries(kind).map { it.copy(sourceProfileId = profile.id) }
        }

''')
catalogue = (here / 'V128Catalog.inc').read_text()
catalogue = catalogue[catalogue.index('    private fun catalogueKey('):]
between(vm, '    private fun loadCategories(', '    private fun loadItems(', catalogue)
replace(vm, '    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {',
    '    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {\n        if (!authorizeContent(item) { play(item, episodeList) }) return')
replace(vm, '        if (item.kind != MediaKind.LIVE || channelList.isEmpty()) return',
    '        if (item.kind != MediaKind.LIVE || channelList.isEmpty()) return\n        if (!authorizeContent(item) { switchLiveChannel(item, channelList) }) return')
replace(vm, '    fun selectV115Episode(current: MediaEntry, selected: MediaEntry, episodeList: List<MediaEntry>) {',
    '    fun selectV115Episode(current: MediaEntry, selected: MediaEntry, episodeList: List<MediaEntry>) {\n        if (!authorizeContent(selected) { selectV115Episode(current, selected, episodeList) }) return')
replace(vm, '        set { it.copy(screen = Screen.Player(ordered[nextIndex], ordered)) }',
    '        if (!authorizeContent(ordered[nextIndex]) { skipEpisode(current, episodeList, direction) }) return\n        set { it.copy(screen = Screen.Player(ordered[nextIndex], ordered)) }')

app = java / 'EpiMediaHubApp.kt'
replace(app, '            if (event == Lifecycle.Event.ON_START) vm.refreshPlaylistsAtAppStart()',
    '            if (event == Lifecycle.Event.ON_START) vm.refreshPlaylistsAtAppStart()\n            if (event == Lifecycle.Event.ON_STOP) vm.lockParentalSession()')
replace(app, '        } else ThemeBackdrop(vm.themeRepo(), info, u.themeId) {',
    '''        } else if (u.parentalSettings.lockMenu && !u.parentalMenuUnlocked) {
            V128MenuLockScreen(vm, accent) { showExitDialog = true }
        } else androidx.compose.runtime.CompositionLocalProvider(LocalV128ArtworkLocked provides { item -> vm.isContentLocked(item) }) {
          ThemeBackdrop(vm.themeRepo(), info, u.themeId) {''')
replace(app, '                Screen.Settings -> SettingsScreen(vm, accent)',
    '                Screen.Settings -> SettingsScreen(vm, accent)\n                Screen.ParentalSettings -> V128ParentalSettingsScreen(vm, accent)')
replace(app, '        updateInfo?.let { update ->',
    '''        }
        if (dashboardPaired && v120LicenseState.allowsUse && !showIntro) {
            u.pinPrompt?.let { prompt ->
                V128PinDialog(prompt.title, accent, u.parentalBusy, u.pinError,
                    onCancel = { vm.cancelParentalPin() }, onSubmit = { vm.submitParentalPin(it) })
            }
            if (u.parentalChecking) androidx.compose.ui.window.Dialog(onDismissRequest = { vm.back() }) {
                V128LoadingPanel("Altersfreigabe wird geprüft …", "", accent, isTv)
            }
        }

        updateInfo?.let { update ->''')

screens = java / 'ui/Screens.kt'
replace(screens, '    val requesters = remember { List(8) { FocusRequester() } }',
    '    val requesters = remember { List(9) { FocusRequester() } }')
replace(screens, '    val remembered = V111MenuMemory.index(memoryKey).coerceIn(0, 7)',
    '    val remembered = V111MenuMemory.index(memoryKey).coerceIn(0, 8)')
replace(screens, '                        Text("Android v1.0.28", fontWeight = FontWeight.Bold)',
    '                        Text("Android v1.0.28", fontWeight = FontWeight.Bold)')
replace(screens, '            item {\n                GlassPanel(Modifier.fillMaxWidth()) {\n                    Column(Modifier.padding(20.dp)) {\n                        Text("Android v1.0.28",',
    '''            item {
                FocusCard("Kindersicherung & PIN", if (u.parentalSettings.hasPin) "18+-Schutz · optionale Menüsperre" else "Eigene vierstellige PIN festlegen",
                    R.drawable.icon_settings, accent = accent, modifier = rememberedModifier(8),
                    onClick = { vm.navigate(Screen.ParentalSettings) })
            }
            item {
                GlassPanel(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        Text("Android v1.0.28",''')
replace(screens, 'if(media.image.isNotBlank())AsyncImage(media.image,null,Modifier.fillMaxWidth().weight(1f),contentScale=ContentScale.Crop)',
    'if(media.image.isNotBlank() || LocalV128ArtworkLocked.current(media))V128MediaArtwork(media,Modifier.fillMaxWidth().weight(1f))')

hub = java / 'ui/V060CinematicHub.kt'
between(hub, '                Column(horizontalAlignment = Alignment.CenterHorizontally) {\n                    CircularProgressIndicator(',
    '            }\n        } else {\n            LoadingOrError(false, u.error)',
    '''                V128LoadingPanel(when (kind) { MediaKind.LIVE -> "Sender werden geladen …"; MediaKind.MOVIE -> "Filme werden geladen …"; else -> "Serien werden geladen …" },
                    "Katalog wird vorbereitet", accent, isTv)
''')
replace(hub, 'if (item.image.isNotBlank()) AsyncImage(item.image, item.name, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)',
    'V128MediaArtwork(item, Modifier.fillMaxSize())', count=2)
replace(hub, '    LaunchedEffect(kind, u.active?.id, newest.size) {',
    '''    val contentState = v111RememberLazyListState("cinematic-main:" + kind.name)
    val heroVisible by remember(contentState) { derivedStateOf { contentState.firstVisibleItemIndex == 0 && !contentState.isScrollInProgress } }
    LaunchedEffect(kind, u.active?.id, newest.size, heroVisible) {''')
replace(hub, '        while (newest.size > 1) {', '        while (heroVisible && newest.size > 1) {')
replace(hub, '        heroIndex = 0\n        while (heroVisible', '        if (heroIndex >= newest.size) heroIndex = 0\n        while (heroVisible')
replace(hub, '    val hero = newest.getOrNull(heroIndex) ?: recent.firstOrNull() ?: firstCatalog\n    val contentState = v111RememberLazyListState("cinematic-main:" + kind.name)',
    '    val hero = newest.getOrNull(heroIndex) ?: recent.firstOrNull() ?: firstCatalog')

live = java / 'ui/V076LiveTv.kt'
between(live, '                Column(horizontalAlignment = Alignment.CenterHorizontally) {\n                    CircularProgressIndicator(color = accent)',
    '            }\n            return@Column',
    '                V128LoadingPanel("Sender werden geladen …", "Katalog wird vorbereitet", accent, isTv)\n')
replace(live, '                    AsyncImage(\n                        model = media.image,\n                        contentDescription = media.name,\n                        modifier = Modifier.fillMaxSize().padding(3.dp),\n                        contentScale = ContentScale.Fit\n                    )',
    '                    V128MediaArtwork(media, Modifier.fillMaxSize().padding(3.dp), ContentScale.Fit)')
replace(live, '''                            AsyncImage(
                                model = channel.image,
                                contentDescription = channel.name,
                                modifier = Modifier.fillMaxSize().padding(if (compact) 10.dp else 18.dp),
                                contentScale = ContentScale.Fit
                            )''', '                            V128MediaArtwork(channel, Modifier.fillMaxSize().padding(if (compact) 10.dp else 18.dp), ContentScale.Fit)')

rows = java / 'ui/BrowserRows.kt'
replace(rows, 'if (media.image.isNotBlank()) AsyncImage(media.image, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)',
    'if (media.image.isNotBlank() || LocalV128ArtworkLocked.current(media)) V128MediaArtwork(media, Modifier.fillMaxSize())')

# Persist the successful SmartTube client by account and let the core restore it directly.
media = root / '.smarttube/MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi'
service = media / 'videoinfo/V2/VideoInfoService.java'
replace(service, '    public void resetInfoType() {',
    '''    public boolean useClientForEpiMedia(String name) {
        if (name == null) return false;
        for (AppClient client : VIDEO_INFO_TYPE_LIST) {
            if (client.name().equals(name)) {
                mActualInfoType = client;
                mNextInfoType = client;
                return true;
            }
        }
        return false;
    }

    public void resetInfoType() {''')
bridge = media / 'service/internal/EpiMediaPlaybackBridge.kt'
replace(bridge, '        clickTrackingParams: String? = null\n',
    '        clickTrackingParams: String? = null,\n        preferredClient: String? = null\n')
replace(bridge, 'FormatInfoWrapper.getMedia3CompatibleFormatInfo(videoId, clickTrackingParams)',
    'FormatInfoWrapper.getMedia3CompatibleFormatInfo(videoId, clickTrackingParams, preferredClient)')
wrapper = media / 'service/internal/FormatInfoWrapper.kt'
replace(wrapper, '        clickTrackingParams: String?\n    ): MediaItemFormatInfo? {\n        invalidateCache()',
    '        clickTrackingParams: String?,\n        preferredClient: String? = null\n    ): MediaItemFormatInfo? {\n        invalidateCache()')
replace(wrapper, '        var fallback: MediaItemFormatInfo? = null\n',
    '''        var fallback: MediaItemFormatInfo? = null
        val restoredClient = getVideoInfoService().useClientForEpiMedia(preferredClient)
''')
replace(wrapper, '        } else {\n            // First playback:', '        } else if (!restoredClient) {\n            // First playback:')

core = java / 'ui/V108SmartTubeCore.kt'
replace(core, '    private val playbackCache = LinkedHashMap<String, CachedPlayback>()',
    '''    private val playbackCache = LinkedHashMap<String, CachedPlayback>()
    private val resolveMutex = kotlinx.coroutines.sync.Mutex()
    private var warmAccount: String? = null

    suspend fun warmPlayback(context: Context) = withContext(Dispatchers.IO) {
        val account = V112SmartTubeWatchHistory.accountKey(manager(context).signInService.selectedAccount)
        if (warmAccount == account) return@withContext
        try {
            com.liskovsoft.youtubeapi.app.AppService.instance().refreshCacheIfNeeded()
            warmAccount = account
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (_: Exception) { /* The normal video request can retry a failed warm-up. */ }
    }''')
replace(core, 'import kotlinx.coroutines.withContext', 'import kotlinx.coroutines.withContext\nimport kotlinx.coroutines.sync.withLock')
replace(core, '''        cachedPlayback(video.videoId)?.let {
            return@withContext Result.success(it)
        }

        runCatching {
            val info = EpiMediaPlaybackBridge.getMedia3CompatibleFormatInfo(video.videoId)''',
    '''        val service = manager(context)
        val account = V112SmartTubeWatchHistory.accountKey(service.signInService.selectedAccount)
        val cacheKey = account + ":" + video.videoId
        resolveMutex.withLock {
        cachedPlayback(cacheKey)?.let { cached ->
            if (!cached.url.startsWith("file:") || File(java.net.URI(cached.url)).isFile) {
                checkAccount(service, account)
                return@withContext Result.success(cached)
            }
        }
        val clients = V128SmartTubeClientStore(context)
        var selectedClient: String? = null
        runCatching {
            val info = EpiMediaPlaybackBridge.getMedia3CompatibleFormatInfo(video.videoId,
                preferredClient = clients.load(account))''')
replace(core, '            val hls = info.hlsManifestUrl?.takeIf',
    '''            selectedClient = (info.clientInfo as? com.liskovsoft.youtubeapi.common.helpers.AppClient)?.name
            checkAccount(service, account)
            val hls = info.hlsManifestUrl?.takeIf''')
replace(core, 'val file = File(context.cacheDir, "smarttube-${video.videoId}.mpd")',
    'val accountHash = java.security.MessageDigest.getInstance("SHA-256").digest(account.toByteArray()).take(8).joinToString("") { "%02x".format(it.toInt() and 255) }\n                    val file = File(context.cacheDir, "smarttube-$accountHash-${video.videoId}.mpd")')
replace(core, '        }.onSuccess { rememberPlayback(video.videoId, it) }',
    '''        }.onSuccess {
            checkAccount(service, account)
            selectedClient?.let { selected -> clients.remember(account, selected) }
            rememberPlayback(cacheKey, it)
        }.onFailure { if (it is CancellationException) throw it }
        }
''')

shell = java / 'ui/V112SmartTubeShell.kt'
replace(shell, '    val scope = rememberCoroutineScope()',
    '''    val scope = rememberCoroutineScope()
    val playerPool = remember(context) { V128SmartTubePlayerPool(context) }
    DisposableEffect(playerPool) { onDispose { playerPool.close() } }
    var firstFrameVideoId by remember { mutableStateOf<String?>(null) }''')
replace(shell, '    LaunchedEffect(activeVideoId, playbackAccountKey, relatedRevision) {\n        val id = activeVideoId ?: return@LaunchedEffect',
    '''    LaunchedEffect(activeVideoId, playbackAccountKey, relatedRevision, firstFrameVideoId) {
        val id = activeVideoId ?: return@LaunchedEffect
        if (id != firstFrameVideoId) return@LaunchedEffect''')
replace(shell, '        resolvingId = video.videoId', '        resolvingId = video.videoId\n        firstFrameVideoId = null')
replace(shell, '    val visibleRows = V112SmartTubeSuggestions.visible(rows, watched, hideWatched)',
    '    val visibleRows = remember(rows, watched, hideWatched) { V112SmartTubeSuggestions.visible(rows, watched, hideWatched) }')
replace(shell, '    LaunchedEffect(auth.accountKey) {',
    '''    LaunchedEffect(authReady, auth.accountKey) {
        if (authReady) V108SmartTubeCore.warmPlayback(context)
    }

    LaunchedEffect(auth.accountKey) {''')
replace(shell, '        V112SmartTubePlayer(\n',
    '        V112SmartTubePlayer(\n            preparedPlayer = playerPool, onFirstFrame = { firstFrameVideoId = video.videoId },\n')

player = java / 'ui/V112SmartTubePlayer.kt'
replace(player, '    historyAccountKey: String,',
    '    historyAccountKey: String,\n    preparedPlayer: V128SmartTubePlayerPool? = null, onFirstFrame: () -> Unit = {},')
replace(player, '    val reportProgress by rememberUpdatedState(onProgress)',
    '    val reportProgress by rememberUpdatedState(onProgress)\n    val firstFrame by rememberUpdatedState(onFirstFrame)')
replace(player, '    val playerResult = remember(context, video.videoId, playback.url) {\n        runCatching {',
    '    val playerResult = remember(context, video.videoId, playback.url, preparedPlayer) {\n        preparedPlayer?.result ?: runCatching {')
replace(player, '            val listener = object : Player.Listener {',
    '            val listener = object : Player.Listener {\n                override fun onRenderedFirstFrame() { firstFrame() }')
replace(player, '                runCatching { player.release() }',
    '                runCatching { if (preparedPlayer == null) player.release() else player.clearMediaItems() }')

tests = root / 'app/src/test/java/de/epimediahub/app/ui'
for source in here.glob('*Test.kt'):
    shutil.copyfile(source, tests / source.name)
print('Android 1.0.28: PIN gates, readable loading panels, bounded parallel catalogues and SmartTube cold-start preparation installed')
