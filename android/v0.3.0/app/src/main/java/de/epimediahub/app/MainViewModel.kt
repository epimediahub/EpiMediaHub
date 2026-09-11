package de.epimediahub.app

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.epimediahub.app.data.*
import de.epimediahub.app.model.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

sealed interface Screen {
    data object Home : Screen
    data object AddPlaylist : Screen
    data object Playlists : Screen
    data object Settings : Screen
    data object Themes : Screen
    data object WebAdmin : Screen
    data object Search : Screen
    data object Favorites : Screen
    data object ContinueWatching : Screen
    data class Categories(val kind: MediaKind) : Screen
    data class Items(val kind: MediaKind, val category: MediaCategory) : Screen
    data class Epg(val category: MediaCategory) : Screen
    data class Episodes(val series: MediaEntry) : Screen
    data class Player(val item: MediaEntry, val episodeList: List<MediaEntry> = emptyList()) : Screen
}

data class UiState(
    val playlists: List<PlaylistProfile> = emptyList(),
    val active: PlaylistProfile? = null,
    val themeCatalog: ThemeCatalog? = null,
    val themeId: String = "default",
    val screen: Screen = Screen.Home,
    val loading: Boolean = false,
    val epgLoading: Boolean = false,
    val error: String = "",
    val categories: List<MediaCategory> = emptyList(),
    val items: List<MediaEntry> = emptyList(),
    val searchResults: List<MediaEntry> = emptyList(),
    val favorites: List<MediaEntry> = emptyList(),
    val continueWatching: List<ContinueItem> = emptyList(),
    val epg: Map<String, List<EpgItem>> = emptyMap(),
    val preferredAudioLanguage: String = "de",
    val preferredSubtitleLanguage: String = "de",
    val webAdminRunning: Boolean = false,
    val webAdminUrl: String = "",
    val webAdminPin: String = ""
)

class MainViewModel(app: Application) : AndroidViewModel(app) {
    private val prefs = PrefsRepository(app)
    private val themes = ThemeRepository(app)
    private val _ui = MutableStateFlow(
        UiState(
            themeCatalog = themes.load(),
            themeId = prefs.themeId,
            favorites = prefs.loadFavoriteEntries(),
            continueWatching = prefs.loadContinue(),
            preferredAudioLanguage = prefs.preferredAudioLanguage,
            preferredSubtitleLanguage = prefs.preferredSubtitleLanguage
        )
    )
    val ui: StateFlow<UiState> = _ui
    private val back = ArrayDeque<Screen>()
    private val m3uCache = mutableMapOf<String, M3uParser.Result>()
    private var webAdmin: LocalWebAdmin? = null

    init { refreshProfiles() }

    fun themeRepo() = themes
    private fun set(block: (UiState) -> UiState) { _ui.value = block(_ui.value) }

    private fun refreshCollections() {
        set {
            it.copy(
                favorites = prefs.loadFavoriteEntries(),
                continueWatching = prefs.loadContinue(),
                preferredAudioLanguage = prefs.preferredAudioLanguage,
                preferredSubtitleLanguage = prefs.preferredSubtitleLanguage
            )
        }
    }

    fun refreshProfiles() {
        val list = prefs.loadPlaylists()
        val active = list.firstOrNull { it.id == prefs.activePlaylistId } ?: list.firstOrNull()
        if (active != null && active.id != prefs.activePlaylistId) prefs.activePlaylistId = active.id
        set {
            it.copy(
                playlists = list,
                active = active,
                screen = if (list.isEmpty()) Screen.AddPlaylist else it.screen
            )
        }
        refreshCollections()
    }

    fun addPlaylist(name: String, url: String, goHome: Boolean = true) {
        if (url.isBlank()) {
            set { it.copy(error = "Bitte eine Playlist-URL eingeben.") }
            return
        }
        runCatching { PlaylistParser.parse(name, url) }
            .onSuccess { addProfile(it, goHome) }
            .onFailure { e -> set { it.copy(error = e.message ?: "Playlist konnte nicht gespeichert werden.") } }
    }

    fun addXtream(name: String, portal: String, username: String, password: String, goHome: Boolean = true) {
        runCatching { PlaylistParser.fromXtream(name, portal, username, password) }
            .onSuccess { addProfile(it, goHome) }
            .onFailure { e -> set { it.copy(error = e.message ?: "Xtream-Zugang konnte nicht gespeichert werden.") } }
    }

    private fun addProfile(p: PlaylistProfile, goHome: Boolean) {
        val list = _ui.value.playlists + p
        prefs.savePlaylists(list)
        prefs.activePlaylistId = p.id
        m3uCache.clear()
        set {
            it.copy(
                playlists = list,
                active = p,
                screen = if (goHome) Screen.Home else it.screen,
                error = "",
                epg = emptyMap()
            )
        }
    }

    fun removePlaylist(id: String) {
        val list = _ui.value.playlists.filterNot { it.id == id }
        prefs.savePlaylists(list)
        prefs.activePlaylistId = list.firstOrNull()?.id.orEmpty()
        m3uCache.remove(id)
        set {
            it.copy(
                playlists = list,
                active = list.firstOrNull(),
                screen = if (list.isEmpty()) Screen.AddPlaylist else Screen.Playlists,
                epg = emptyMap()
            )
        }
    }

    fun selectPlaylist(id: String) {
        val p = _ui.value.playlists.firstOrNull { it.id == id } ?: return
        prefs.activePlaylistId = id
        set { it.copy(active = p, screen = Screen.Home, categories = emptyList(), items = emptyList(), epg = emptyMap()) }
    }

    fun selectTheme(id: String) {
        prefs.themeId = id
        set { it.copy(themeId = id) }
    }

    fun setAudioLanguage(code: String) {
        prefs.preferredAudioLanguage = code
        set { it.copy(preferredAudioLanguage = code) }
    }

    fun setSubtitleLanguage(code: String) {
        prefs.preferredSubtitleLanguage = code
        set { it.copy(preferredSubtitleLanguage = code) }
    }

    fun navigate(screen: Screen, remember: Boolean = true) {
        if (remember) back.addLast(_ui.value.screen)
        set { it.copy(screen = screen, error = "") }
        when (screen) {
            is Screen.Categories -> loadCategories(screen.kind)
            is Screen.Items -> loadItems(screen.kind, screen.category.id)
            is Screen.Episodes -> loadEpisodes(screen.series)
            Screen.Favorites, Screen.ContinueWatching -> refreshCollections()
            else -> Unit
        }
    }

    fun back() {
        val s = back.removeLastOrNull() ?: Screen.Home
        refreshCollections()
        set { it.copy(screen = s, error = "") }
    }

    private suspend fun m3uResult(p: PlaylistProfile): M3uParser.Result {
        return m3uCache[p.id] ?: M3uParser.download(p.originalUrl).also { m3uCache[p.id] = it }
    }

    private fun loadCategories(kind: MediaKind) {
        val p = _ui.value.active ?: return
        set { it.copy(loading = true, categories = emptyList(), error = "") }
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    if (p.type == PlaylistType.XTREAM) {
                        XtreamClient(p).categories(kind)
                    } else if (kind == MediaKind.LIVE) {
                        m3uResult(p).groups.map { MediaCategory(it, it) }
                    } else {
                        emptyList()
                    }
                }
            }.onSuccess { categories ->
                set { it.copy(loading = false, categories = categories) }
            }.onFailure { e ->
                set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
        }
    }

    private fun loadItems(kind: MediaKind, cat: String) {
        val p = _ui.value.active ?: return
        set { it.copy(loading = true, items = emptyList(), epg = if (kind == MediaKind.LIVE) emptyMap() else it.epg, error = "") }
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    if (p.type == PlaylistType.XTREAM) {
                        XtreamClient(p).entries(kind, cat)
                    } else {
                        m3uResult(p).entries.filter { it.categoryId == cat }
                    }
                }
            }.onSuccess { entries ->
                set { it.copy(loading = false, items = entries) }
                if (kind == MediaKind.LIVE) loadLiveEpg(entries)
            }.onFailure { e ->
                set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
        }
    }

    private fun loadEpisodes(series: MediaEntry) {
        val p = _ui.value.active ?: return
        set { it.copy(loading = true, items = emptyList(), error = "") }
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) { XtreamClient(p).episodes(series.seriesId) }
            }.onSuccess { entries ->
                set { it.copy(loading = false, items = entries) }
            }.onFailure { e ->
                set { it.copy(loading = false, error = e.message ?: "Fehler beim Laden") }
            }
        }
    }

    private fun loadLiveEpg(entries: List<MediaEntry>) {
        val p = _ui.value.active ?: return
        if (entries.isEmpty()) return
        set { it.copy(epgLoading = true) }
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    if (p.type == PlaylistType.XTREAM) {
                        val client = XtreamClient(p)
                        val out = mutableMapOf<String, List<EpgItem>>()
                        for (chunk in entries.take(72).chunked(8)) {
                            coroutineScope {
                                chunk.map { channel ->
                                    async {
                                        channel.id to runCatching { client.shortEpg(channel.id) }.getOrDefault(emptyList())
                                    }
                                }.awaitAll()
                            }.forEach { (id, list) -> if (list.isNotEmpty()) out[id] = list }
                        }
                        out
                    } else {
                        val playlist = m3uResult(p)
                        if (playlist.epgUrl.isBlank()) return@withContext emptyMap()
                        val wanted = entries.mapNotNull { entry -> entry.epgId.takeIf { value -> value.isNotBlank() } }.toSet()
                        val xml = XmlTvClient.nowNext(playlist.epgUrl, wanted)
                        entries.mapNotNull { channel ->
                            val key = channel.epgId
                            xml[key]?.takeIf { it.isNotEmpty() }?.let { channel.id to it }
                        }.toMap()
                    }
                }
            }.onSuccess { map ->
                set { it.copy(epgLoading = false, epg = it.epg + map) }
            }.onFailure {
                set { it.copy(epgLoading = false) }
            }
        }
    }

    fun ensureEpg(item: MediaEntry) {
        if (_ui.value.epg[item.id]?.isNotEmpty() == true || item.kind != MediaKind.LIVE) return
        val p = _ui.value.active ?: return
        viewModelScope.launch {
            val list = runCatching {
                withContext(Dispatchers.IO) {
                    if (p.type == PlaylistType.XTREAM) {
                        XtreamClient(p).shortEpg(item.id)
                    } else {
                        val playlist = m3uResult(p)
                        if (playlist.epgUrl.isBlank() || item.epgId.isBlank()) emptyList()
                        else XmlTvClient.nowNext(playlist.epgUrl, setOf(item.epgId))[item.epgId].orEmpty()
                    }
                }
            }.getOrDefault(emptyList())
            if (list.isNotEmpty()) set { it.copy(epg = it.epg + (item.id to list)) }
        }
    }

    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {
        val profile = _ui.value.active
        if (item.kind == MediaKind.EPISODE && episodeList.isEmpty() && item.seriesId.isNotBlank() && profile != null && profile.type == PlaylistType.XTREAM) {
            set { it.copy(loading = true) }
            viewModelScope.launch {
                val siblings = runCatching {
                    withContext(Dispatchers.IO) { XtreamClient(profile).episodes(item.seriesId) }
                }.getOrDefault(emptyList())
                set { it.copy(loading = false) }
                navigate(Screen.Player(item, siblings), remember = true)
            }
        } else {
            navigate(Screen.Player(item, episodeList))
        }
    }

    fun skipEpisode(current: MediaEntry, episodeList: List<MediaEntry>, direction: Int) {
        if (episodeList.isEmpty()) return
        val currentIndex = episodeList.indexOfFirst { it.id == current.id }
        if (currentIndex < 0) return
        val nextIndex = currentIndex + direction
        if (nextIndex !in episodeList.indices) return
        set { it.copy(screen = Screen.Player(episodeList[nextIndex], episodeList)) }
    }

    fun search(q: String) {
        val p = _ui.value.active ?: return
        if (q.length < 2) {
            set { it.copy(searchResults = emptyList()) }
            return
        }
        set { it.copy(loading = true, error = "") }
        viewModelScope.launch {
            runCatching {
                withContext(Dispatchers.IO) {
                    if (p.type == PlaylistType.XTREAM) {
                        val c = XtreamClient(p)
                        (c.entries(MediaKind.LIVE) + c.entries(MediaKind.MOVIE) + c.entries(MediaKind.SERIES))
                            .filter { it.name.contains(q, true) }
                            .take(250)
                    } else {
                        m3uResult(p).entries.filter { it.name.contains(q, true) }.take(250)
                    }
                }
            }.onSuccess { results ->
                set { it.copy(loading = false, searchResults = results) }
            }.onFailure { e ->
                set { it.copy(loading = false, error = e.message ?: "Suche fehlgeschlagen") }
            }
        }
    }

    fun startWebAdmin() {
        if (webAdmin != null) return
        val pin = (100000..999999).random().toString()
        val server = LocalWebAdmin(
            pin = pin,
            playlistsProvider = { prefs.loadPlaylists() },
            onAddM3u = { name, url -> viewModelScope.launch { addPlaylist(name, url, goHome = false) } },
            onAddXtream = { name, portal, username, password ->
                viewModelScope.launch { addXtream(name, portal, username, password, goHome = false) }
            }
        )
        runCatching {
            server.start(5000, false)
            webAdmin = server
            set { it.copy(webAdminRunning = true, webAdminUrl = server.address, webAdminPin = pin, error = "") }
        }.onFailure { e ->
            runCatching { server.stop() }
            set { it.copy(error = e.message ?: "PC-Verwaltung konnte nicht gestartet werden.") }
        }
    }

    fun stopWebAdmin() {
        webAdmin?.stop()
        webAdmin = null
        set { it.copy(webAdminRunning = false, webAdminUrl = "", webAdminPin = "") }
    }

    override fun onCleared() {
        webAdmin?.stop()
        webAdmin = null
        super.onCleared()
    }

    fun resume(item: MediaEntry) = prefs.getResume(item.resumeKey)

    fun savePlayback(item: MediaEntry, pos: Long, duration: Long) {
        prefs.savePlayback(item, pos, duration)
    }

    fun toggleFavorite(item: MediaEntry): Boolean {
        val added = prefs.toggleFavorite(item)
        refreshCollections()
        return added
    }

    fun isFavorite(item: MediaEntry) = prefs.isFavorite(item)
}
