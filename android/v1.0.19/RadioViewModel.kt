package de.epimediahub.app.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import de.epimediahub.app.data.*
import de.epimediahub.app.radio.RadioController
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.*
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import java.io.File

internal enum class RadioMode(val label: String) { DISCOVER("Entdecken"), FAVORITES("Favoriten"), RECENT("Zuletzt gehört") }

internal data class RadioUiState(
    val mode: RadioMode = RadioMode.DISCOVER,
    val query: RadioQuery = RadioQuery(),
    val stations: List<RadioStation> = emptyList(),
    val favorites: List<RadioStation> = emptyList(),
    val recent: List<RadioStation> = emptyList(),
    val countries: List<RadioOption> = listOf(RadioOption("DE", "Deutschland"), RadioOption("IT", "Italien")),
    val languages: List<RadioOption> = listOf(RadioOption("german", "Deutsch"), RadioOption("italian", "Italienisch"), RadioOption("english", "Englisch")),
    val loading: Boolean = false,
    val page: Int = 0,
    val more: Boolean = false,
    val cached: Boolean = false,
    val partial: Boolean = false,
    val error: String = ""
) {
    val visible: List<RadioStation> get() = when (mode) {
        RadioMode.DISCOVER -> stations
        RadioMode.FAVORITES -> favorites.filter(query::accepts)
        RadioMode.RECENT -> recent.filter(query::accepts)
    }
    val favoriteIds: Set<String> get() = favorites.mapTo(mutableSetOf()) { it.uuid }
}

internal class RadioViewModel(application: Application) : AndroidViewModel(application) {
    private val client = RadioBrowserClient(File(application.cacheDir, "radio-directory"))
    private val prefs = RadioPreferences(application)
    private val mutable = MutableStateFlow(RadioUiState())
    val ui: StateFlow<RadioUiState> = mutable
    val player = RadioController(application)
    private var request: Job? = null
    private val favoritesLock = Mutex()

    init {
        load(false)
        viewModelScope.launch(Dispatchers.IO) { client.discoverServers() }
        viewModelScope.launch {
            val stored = withContext(Dispatchers.IO) { prefs.read("favorites") to prefs.read("recent") }
            mutable.update { it.copy(favorites = stored.first, recent = stored.second) }
        }
        viewModelScope.launch {
            try { val countries = client.countries(); mutable.update { it.copy(countries = countries.ifEmpty { it.countries }) } }
            catch (_: Exception) { }
        }
        viewModelScope.launch {
            try { val languages = client.languages(); mutable.update { it.copy(languages = languages.ifEmpty { it.languages }) } }
            catch (_: Exception) { }
        }
        viewModelScope.launch {
            player.state.map { it.station?.uuid }.distinctUntilChanged().filterNotNull().collect {
                val recent = withContext(Dispatchers.IO) { prefs.read("recent") }
                mutable.update { state -> state.copy(recent = recent) }
            }
        }
    }

    fun query(value: RadioQuery) {
        request?.cancel()
        mutable.update { it.copy(query = value, stations = emptyList(), page = 0, more = false, error = "", cached = false, partial = false) }
        if (mutable.value.mode == RadioMode.DISCOVER) load(false)
    }
    fun mode(value: RadioMode) {
        request?.cancel()
        mutable.update { it.copy(mode = value, loading = false, error = "") }
        if (value == RadioMode.DISCOVER && mutable.value.stations.isEmpty()) load(false)
    }
    fun load(append: Boolean, refresh: Boolean = false) {
        if (append && mutable.value.loading) return
        request?.cancel()
        val original = mutable.value
        val page = if (append) original.page + 1 else 0
        mutable.update { it.copy(loading = true, error = "") }
        request = viewModelScope.launch {
            try {
                val result = client.stations(original.query, page, refresh)
                mutable.update {
                    it.copy(stations = radioUniqueStations((if (append) it.stations else emptyList()) + result.stations),
                        page = page, more = result.hasMore, loading = false, cached = result.cached, partial = result.partial)
                }
            } catch (e: CancellationException) { throw e }
            catch (_: Exception) { mutable.update { it.copy(loading = false, error = "Senderverzeichnis gerade nicht erreichbar. Favoriten bleiben verfügbar.") } }
        }
    }
    fun favorite(station: RadioStation) {
        mutable.update { state -> state.copy(favorites = if (station.uuid in state.favoriteIds)
            state.favorites.filterNot { it.uuid == station.uuid } else state.favorites + station) }
        viewModelScope.launch(Dispatchers.IO) { favoritesLock.withLock { prefs.saveFavorites(mutable.value.favorites) } }
    }
    fun play(station: RadioStation) {
        player.play(station, mutable.value.visible)
        viewModelScope.launch { try { client.recordClick(station.uuid) } catch (_: Exception) { } }
    }
    fun refresh() {
        load(false, true)
        viewModelScope.launch {
            try { val countries = client.countries(); mutable.update { it.copy(countries = countries.ifEmpty { it.countries }) } }
            catch (_: Exception) { }
        }
        viewModelScope.launch {
            try { val languages = client.languages(); mutable.update { it.copy(languages = languages.ifEmpty { it.languages }) } }
            catch (_: Exception) { }
        }
    }
    override fun onCleared() { player.close(); super.onCleared() }
}
