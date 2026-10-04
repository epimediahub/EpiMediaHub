    private val libraryCatalogCache = V128TimedCache<V128LibraryCatalog>()
    private var libraryLoadJob: kotlinx.coroutines.Job? = null
    private var libraryLoadGeneration = 0L

    private fun catalogueKey(profile: PlaylistProfile, kind: MediaKind): String =
        profile.id + "|" + kind.name + "|" + listOf(profile.server, profile.username, profile.password, profile.originalUrl, profile.output).hashCode()

    private fun loadCategories(kind: MediaKind) {
        val profile = _ui.value.active ?: return
        val generation = ++libraryLoadGeneration
        libraryLoadJob?.cancel()
        val hidden = prefs.loadHiddenCategories(profile.id, kind)
        fun applyCatalogue(catalogue: V128LibraryCatalog) {
            catalogue.categories.forEach { parentalCategories["${profile.id}|$kind|${it.id}"] = it.name }
            set { it.copy(loading = false, catalogRowsLoading = false, categories = catalogue.categories,
                catalogRows = catalogue.rows, hiddenCategoryIds = hidden, error = "") }
        }
        libraryCatalogCache[catalogueKey(profile, kind)]?.let { applyCatalogue(it); return }
        set { it.copy(loading = true, categories = emptyList(), catalogRows = emptyMap(), catalogRowsLoading = true,
            hiddenCategoryIds = hidden, error = "") }
        libraryLoadJob = viewModelScope.launch {
            try {
                val catalogue = withContext(Dispatchers.IO) {
                    coroutineScope {
                        // Metadata only: this does not start a second provider stream.
                        val categoryRequest = async {
                            if (profile.type == PlaylistType.XTREAM) XtreamClient(profile).categories(kind)
                            else if (kind == MediaKind.LIVE) m3uResult(profile).groups.map { MediaCategory(it, it) }
                            else emptyList()
                        }
                        val libraryRequest = async {
                            if (profile.type == PlaylistType.XTREAM) xtreamLibrary(profile, kind)
                            else if (kind == MediaKind.LIVE) m3uResult(profile).entries.map { it.copy(sourceProfileId = profile.id) }
                            else emptyList()
                        }
                        val categories = categoryRequest.await()
                        val all = V128AdultContent.bind(libraryRequest.await(), categories)
                        if (profile.type == PlaylistType.XTREAM) xtreamLibraryCache[catalogueKey(profile, kind)] = all
                        val rows = linkedMapOf<String, List<MediaEntry>>()
                        if (kind == MediaKind.MOVIE || kind == MediaKind.SERIES) {
                            val newest = all.asSequence().filter { it.addedAt > 0 }.sortedByDescending { it.addedAt }.take(36).toList()
                            if (newest.isNotEmpty()) rows["__recently_added__"] = newest
                        }
                        val grouped = all.groupBy { it.categoryId }
                        categories.forEach { category ->
                            val entries = if (category.id == "__all__") all else grouped[category.id].orEmpty()
                            if (entries.isNotEmpty()) rows[category.id] = entries
                        }
                        val visible = if (kind == MediaKind.MOVIE || kind == MediaKind.SERIES)
                            listOf(MediaCategory("__recently_added__", "Zuletzt hinzugefügt")) + categories else categories
                        V128LibraryCatalog(visible, rows)
                    }
                }
                if (generation == libraryLoadGeneration && _ui.value.active?.id == profile.id && _ui.value.contentFilterKind == kind) {
                    libraryCatalogCache[catalogueKey(profile, kind)] = catalogue
                    applyCatalogue(catalogue)
                }
            } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
            catch (failure: Exception) {
                if (generation == libraryLoadGeneration && _ui.value.active?.id == profile.id) {
                    set { it.copy(loading = false, catalogRowsLoading = false, error = failure.message ?: "Katalog konnte nicht geladen werden.") }
                }
            }
        }
    }
