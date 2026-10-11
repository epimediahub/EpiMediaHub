    // v1.0.60: Warm one active Live-TV metadata catalogue while the 10s intro plays.
    // No decoder or HTTP stream is opened. Limit to one bounded background job.
    private var v160LiveWarmJob: kotlinx.coroutines.Job? = null
    private var v160LiveWarmKey: String? = null

    fun v160WarmLiveDuringIntro() {
        val profile = _ui.value.active ?: return
        val key = catalogueKey(profile, MediaKind.LIVE)
        if (libraryCatalogCache[key] != null) return
        if (v160LiveWarmKey == key && v160LiveWarmJob?.isActive == true) return
        v160LiveWarmJob?.cancel()
        v160LiveWarmKey = key
        v160LiveWarmJob = viewModelScope.launch(Dispatchers.IO) {
            val started = android.os.SystemClock.elapsedRealtime()
            // Intro must never wait for a slow provider; switch to ordinary lazy loading on timeout.
            val prepared = kotlinx.coroutines.withTimeoutOrNull(7500L) {
                val (categories, all) =
                    if (profile.type == PlaylistType.XTREAM) {
                        kotlinx.coroutines.coroutineScope {
                            val names = async { XtreamClient(profile).categories(MediaKind.LIVE).distinctBy { it.id } }
                            val entries = async { xtreamLibrary(profile, MediaKind.LIVE) }
                            val catalogCategories = names.await()
                            val list = V128AdultContent.bind(entries.await(), catalogCategories)
                            catalogCategories to list
                        }
                    } else {
                        // A single M3U download provides both categories and entries.
                        val result = m3uResult(profile)
                        result.groups.map { MediaCategory(it, it) } to
                            V128AdultContent.bind(result.entries.map { it.copy(sourceProfileId = profile.id) },
                                result.groups.map { MediaCategory(it, it) })
                    }

                // A very large provider catalogue should still use the regular on-demand route.
                if (all.size > 18000) return@withTimeoutOrNull null
                val grouped = all.groupBy { it.categoryId }
                val rows = linkedMapOf<String, List<MediaEntry>>()
                categories.forEach { category ->
                    val items = if (category.id == "__all__") all else grouped[category.id].orEmpty()
                    if (items.isNotEmpty()) rows[category.id] = items
                }
                V128LibraryCatalog(categories, rows)
            }
            if (prepared != null) {
                withContext(Dispatchers.Main.immediate) {
                    // Never expose stale results from a switched, deleted or modified playlist.
                    if (_ui.value.active?.id == profile.id &&
                        catalogueKey(profile, MediaKind.LIVE) == key &&
                        v160LiveWarmKey == key) {
                        libraryCatalogCache[key] = prepared
                        android.util.Log.i("EpiMediaHubIntroWarmup",
                            "Live metadata ready in " +
                                (android.os.SystemClock.elapsedRealtime() - started) +
                                " ms, categories=" + prepared.categories.size)
                    }
                }
            }
        }
    }

    private fun v160CancelLiveIntroWarmup() {
        v160LiveWarmJob?.cancel()
        v160LiveWarmJob = null
        v160LiveWarmKey = null
    }

