    private var pinRequestSequence = 0L
    private var pendingPinAction: (() -> Unit)? = null
    private var parentalSettingsAuthorized = false
    private var contentAccessJob: kotlinx.coroutines.Job? = null
    private val parentalMetadataChecked = mutableSetOf<String>()
    private val parentalCategories = mutableMapOf<String, String>()

    private fun requestParentalPin(title: String, approved: () -> Unit) {
        val request = V128PinPrompt(++pinRequestSequence, title)
        pendingPinAction = approved
        set { it.copy(pinPrompt = request, pinError = "", parentalBusy = false) }
    }

    fun cancelParentalPin() {
        pinRequestSequence++
        pendingPinAction = null
        set { it.copy(pinPrompt = null, pinError = "", parentalBusy = false) }
    }

    fun submitParentalPin(pin: String) {
        val prompt = _ui.value.pinPrompt ?: return
        if (_ui.value.parentalBusy) return
        set { it.copy(parentalBusy = true, pinError = "") }
        viewModelScope.launch {
            val result = withContext(Dispatchers.IO) { parental.verify(pin) }
            if (_ui.value.pinPrompt?.id != prompt.id || pinRequestSequence != prompt.id) return@launch
            if (result.accepted) {
                val action = pendingPinAction
                pendingPinAction = null
                set { it.copy(pinPrompt = null, parentalBusy = false, pinError = "") }
                action?.invoke()
            } else set { it.copy(parentalBusy = false, pinError = result.message) }
        }
    }

    fun requestMenuUnlock() {
        if (!_ui.value.parentalSettings.lockMenu || _ui.value.parentalMenuUnlocked || _ui.value.pinPrompt != null) return
        requestParentalPin("Hauptmenü entsperren") { set { it.copy(parentalMenuUnlocked = true) } }
    }

    fun lockParentalSession() {
        contentAccessJob?.cancel()
        parentalSettingsAuthorized = false
        parentalMetadataChecked.clear()
        cancelParentalPin()
        val state = _ui.value
        val current = when (val screen = state.screen) {
            is Screen.Player -> screen.item
            is Screen.Details -> screen.item
            is Screen.Episodes -> screen.series
            else -> null
        }
        val unsafeReturn = current?.let { V128AdultContent.restricted(parentalItem(it), state.parentalSettings) } == true ||
            state.screen == Screen.ParentalSettings
        if (unsafeReturn) back.clear()
        set { it.copy(parentalMenuUnlocked = false, parentalGranted = emptySet(), parentalChecking = false,
            screen = if (unsafeReturn) Screen.Home else it.screen) }
    }

    private fun parentalItem(item: MediaEntry): MediaEntry {
        val enriched = _ui.value.details[item.resumeKey] ?: item
        val profileId = item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() }
        val categoryName = enriched.categoryName.ifBlank { parentalCategories["$profileId|${item.kind}|${item.categoryId}"].orEmpty() }
        val series = if (item.kind == MediaKind.EPISODE) _ui.value.details.values.firstOrNull {
            it.kind == MediaKind.SERIES && it.sourceProfileId == profileId && (it.seriesId == item.seriesId || it.id == item.seriesId)
        } else null
        return enriched.copy(sourceProfileId = profileId, categoryName = categoryName,
            adult = enriched.adult || series?.adult == true, ageRating = maxOf(enriched.ageRating, series?.ageRating ?: -1))
    }

    fun isContentLocked(item: MediaEntry): Boolean {
        val effective = parentalItem(item)
        return V128AdultContent.restricted(effective, _ui.value.parentalSettings) &&
            V128AdultContent.scope(effective) !in _ui.value.parentalGranted
    }

    /** Guard every entry point, including favourites, search, zapping and next episode. */
    private fun authorizeContent(item: MediaEntry, approved: () -> Unit): Boolean {
        val effective = parentalItem(item)
        val state = _ui.value
        if (!state.parentalSettings.hasPin || !state.parentalSettings.lockAdult) return true
        val scope = V128AdultContent.scope(effective)
        if (scope in state.parentalGranted) return true
        // Some providers expose FSK only on the detail endpoint, not in the catalogue.
        val profile = state.playlists.firstOrNull { it.id == effective.sourceProfileId } ?: state.active
        val metadataItem = when {
            item.kind == MediaKind.MOVIE || item.kind == MediaKind.SERIES -> effective
            item.kind == MediaKind.EPISODE && item.seriesId.isNotBlank() ->
                MediaEntry(item.seriesId, item.name, MediaKind.SERIES, sourceProfileId = effective.sourceProfileId, seriesId = item.seriesId)
            else -> null
        }
        if (!V128AdultContent.restricted(effective, state.parentalSettings.copy(lockUnrated = false)) && profile?.type == PlaylistType.XTREAM &&
            metadataItem != null && metadataItem.resumeKey !in parentalMetadataChecked && metadataItem.resumeKey !in state.details) {
            contentAccessJob?.cancel()
            set { it.copy(parentalChecking = true) }
            contentAccessJob = viewModelScope.launch {
                val detail = try { withContext(Dispatchers.IO) { XtreamClient(profile).details(metadataItem) } }
                    catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
                    catch (_: Exception) { null }
                parentalMetadataChecked += metadataItem.resumeKey
                set { it.copy(parentalChecking = false, details = if (detail == null) it.details else
                    it.details + (metadataItem.resumeKey to detail.copy(sourceProfileId = effective.sourceProfileId))) }
                if (authorizeContent(item, approved)) approved()
            }
            return false
        }
        if (!V128AdultContent.restricted(parentalItem(item), state.parentalSettings)) return true
        requestParentalPin("Geschützten Inhalt freigeben") {
            set { it.copy(parentalGranted = it.parentalGranted + scope) }
            approved()
        }
        return false
    }

    private fun allowParentalNavigation(screen: Screen, remember: Boolean): Boolean {
        if (screen == Screen.ParentalSettings && _ui.value.parentalSettings.hasPin && !parentalSettingsAuthorized) {
            requestParentalPin("Kindersicherung öffnen") {
                parentalSettingsAuthorized = true
                navigate(screen, remember)
            }
            return false
        }
        val item = when (screen) {
            is Screen.Details -> screen.item
            is Screen.Player -> screen.item
            is Screen.Episodes -> screen.series
            else -> null
        }
        if (item != null && !authorizeContent(item) { navigate(screen, remember) }) return false
        if (screen != Screen.ParentalSettings) parentalSettingsAuthorized = false
        return true
    }

    fun setParentalPin(pin: String, complete: (Boolean) -> Unit) {
        if (_ui.value.screen != Screen.ParentalSettings || (_ui.value.parentalSettings.hasPin && !parentalSettingsAuthorized)) return
        if (_ui.value.parentalBusy || !V128ParentalControl.validPin(pin)) return
        val first = !_ui.value.parentalSettings.hasPin
        val requestSequence = pinRequestSequence
        set { it.copy(parentalBusy = true) }
        viewModelScope.launch {
            val saved = withContext(Dispatchers.IO) { runCatching {
                parental.setPin(pin)
                if (first) parental.update(adult = true, menu = false, unrated = false)
            }.isSuccess }
            parentalSettingsAuthorized = saved && requestSequence == pinRequestSequence && _ui.value.screen == Screen.ParentalSettings
            set { it.copy(parentalSettings = parental.settings(), parentalBusy = false, parentalGranted = emptySet()) }
            complete(saved)
        }
    }

    fun updateParentalSettings(adult: Boolean = _ui.value.parentalSettings.lockAdult,
        menu: Boolean = _ui.value.parentalSettings.lockMenu, unrated: Boolean = _ui.value.parentalSettings.lockUnrated) {
        if (_ui.value.screen != Screen.ParentalSettings || !parentalSettingsAuthorized) return
        parental.update(adult, menu, unrated)
        set { it.copy(parentalSettings = parental.settings(), parentalMenuUnlocked = true, parentalGranted = emptySet()) }
    }

    fun removeParentalPin() {
        if (_ui.value.screen != Screen.ParentalSettings || !parentalSettingsAuthorized) return
        parental.removePin()
        set { it.copy(parentalSettings = parental.settings(), parentalMenuUnlocked = true, parentalGranted = emptySet()) }
    }
