#!/usr/bin/env python3
"""EpiMediaHub 1.0.91 private QA: stable Live-TV browser and retained v188 Sportmodus.

- No HDMI display mode changes while switching live channels
- Build sport-name cross-category index off UI thread once per loaded catalogue
- Never flatten entire IPTV library from a Compose read
- Preserve category focus when moving right to channel list
- Hide conspicuous provider separator rows that are not watchable stations
- Do not reload an already-present same-playlist Live browser on OK/back
No customer updater or production release mutation.
"""
from pathlib import Path
import os
import shutil

root=Path(os.environ["PROJECT_ROOT"])
here=Path(__file__).resolve().parent
ui=root/"app/src/main/java/de/epimediahub/app/ui"
vm=root/"app/src/main/java/de/epimediahub/app/MainViewModel.kt"
surface=ui/"V121VodSurface.kt"
browser=ui/"V076LiveTv.kt"
gradle=root/"app/build.gradle.kts"
tests=root/"app/src/test/java/de/epimediahub/app/ui"

def once(path,old,new):
    s=path.read_text(encoding="utf-8")
    n=s.count(old)
    if n != 1: raise SystemExit(f"STOP_V191_SOURCE_DRIFT {path.name} occurrences={n} anchor={old[:110]!r}")
    path.write_text(s.replace(old,new,1),encoding="utf-8")

once(gradle,"versionCode = 1088","versionCode = 1091")
once(gradle,'versionName = "1.0.88"','versionName = "1.0.91"')
tests.mkdir(parents=True,exist_ok=True)
for name in ("V191LiveHeaders.kt","V191SportIndex.kt"):
    shutil.copy2(here/name,ui/name)
for name in ("V191LiveHeadersTest.kt","V191SportIndexTest.kt"):
    shutil.copy2(here/name,tests/name)

# The validated v188 frame detection is retained; only the active LIVE
# display change request is disabled. VOD cinema mode remains independent.
once(surface,
    'request = displayLease.match(fps, view, allow1080p = false, liveTv = true)',
    'request = "Live: stabile TV-Ausgabe ohne automatischen HDMI-Moduswechsel"')

# Sport catalogue indices are formed once off the Compose UI thread, then
# replaced atomically on the main thread when a new catalogue is ready.
once(vm,
    '    val liveBackgroundPlayer: Screen.Player? = null,',
    '    val liveBackgroundPlayer: Screen.Player? = null,\n    val v191SportsRevision: Int = 0,')
code=vm.read_text(encoding="utf-8")
start=code.index('    private fun v188AllLiveCandidates(')
end=code.index('    fun v187SportOfferAvailable(',start)
new='''    private var v191SportIndexKey: String = ""
    private var v191SportIndexRows: Map<String, List<MediaEntry>>? = null
    private var v191SportIndex: de.epimediahub.app.ui.V191SportIndex? = null
    private var v191SportJob: kotlinx.coroutines.Job? = null

    private fun v191ScheduleSportIndex(
        profileId: String, key: String, rows: Map<String, List<MediaEntry>>
    ) {
        if (v191SportIndexKey == key && v191SportIndexRows === rows) return
        v191SportJob?.cancel()
        v191SportIndexKey = key
        v191SportIndexRows = rows
        v191SportIndex = null
        v191SportJob = viewModelScope.launch(Dispatchers.Default) {
            val built = de.epimediahub.app.ui.V191SportIndex.build(profileId, rows)
            kotlinx.coroutines.withContext(Dispatchers.Main.immediate) {
                if (v191SportIndexKey == key && v191SportIndexRows === rows) {
                    v191SportIndex = built
                    set { it.copy(v191SportsRevision = it.v191SportsRevision + 1) }
                }
            }
        }
    }

    private fun v188AllLiveCandidates(
        item: MediaEntry, provided: List<MediaEntry>
    ): List<MediaEntry> {
        val profile = _ui.value.active ?: return listOf(item)
        val requested = item.sourceProfileId.ifBlank { profile.id }
        if (requested != profile.id) return listOf(item)
        // Until the asynchronous lookup is ready, stay responsive and do NOT
        // recompute the whole cached catalogue on the UI/remote focus thread.
        if (v191SportIndexKey != catalogueKey(profile, MediaKind.LIVE))
            return listOf(item)
        return v191SportIndex?.groupFor(item) ?: listOf(item)
    }

'''
code=code[:start]+new+code[end:]
vm.write_text(code,encoding="utf-8")
once(vm,
'''            set { it.copy(loading = false, catalogRowsLoading = false, categories = catalogue.categories,
                catalogRows = catalogue.rows, hiddenCategoryIds = hidden, error = "") }
        }''',
'''            set { it.copy(loading = false, catalogRowsLoading = false, categories = catalogue.categories,
                catalogRows = catalogue.rows, hiddenCategoryIds = hidden, error = "") }
            if (kind == MediaKind.LIVE) v191ScheduleSportIndex(
                profile.id, catalogueKey(profile, MediaKind.LIVE), catalogue.rows)
        }''')

# The V164 player remains retained while the category browser is open.
# Re-entering that already loaded browser should NOT flash the loading panel.
once(vm,
'''        set { it.copy(screen = Screen.Categories(MediaKind.LIVE), liveBackgroundPlayer = playing,
            contentFilterKind = MediaKind.LIVE, error = "") }
        loadCategories(MediaKind.LIVE)''',
'''        val liveBrowserReady = _ui.value.contentFilterKind == MediaKind.LIVE &&
            _ui.value.catalogRows.isNotEmpty() && _ui.value.categories.isNotEmpty() &&
            (playing.item.sourceProfileId.isBlank() ||
                playing.item.sourceProfileId == profile.id)
        set { it.copy(screen = Screen.Categories(MediaKind.LIVE), liveBackgroundPlayer = playing,
            contentFilterKind = MediaKind.LIVE, error = "") }
        if (!liveBrowserReady) loadCategories(MediaKind.LIVE)''')

# Real playable channels only; remove provider-created ---GROUP--- rows from
# UI without modifying the original IPTV/EPG catalogue or customer data.
once(browser,
    '    val channels = selectedCategory?.let { u.catalogRows[it.id].orEmpty() }.orEmpty()',
    '''    val channels = remember(u.catalogRows, selectedCategory?.id) {
        selectedCategory?.let { category ->
            u.catalogRows[category.id].orEmpty().filterNot {
                V191LiveHeaders.isNonPlayableName(it.name)
            }
        }.orEmpty()
    }''')

# The prior key-based FocusRequester recreated and requested focus on EACH
# category change, stealing remote input back from the channel pane.
once(browser,
'''    val selectedFocus = remember(selectedId, categories.size) { FocusRequester() }

    LaunchedEffect(selectedId, categories.size) {
        if (categories.isNotEmpty()) {
            railState.scrollToItem(selectedIndex)
            delay(90)
            runCatching { selectedFocus.requestFocus() }
        }
    }''',
'''    val selectedFocus = remember { FocusRequester() }

    LaunchedEffect(selectedId, categories.size) {
        if (categories.isNotEmpty()) {
            val first = railState.firstVisibleItemIndex
            val last = railState.layoutInfo.visibleItemsInfo.lastOrNull()?.index
                ?: (first + 6)
            if (selectedIndex !in first..last) railState.scrollToItem(selectedIndex)
        }
    }
    LaunchedEffect(categories.isNotEmpty()) {
        if (categories.isNotEmpty()) {
            delay(90)
            runCatching { selectedFocus.requestFocus() }
        }
    }''')

code=vm.read_text(encoding="utf-8")
assert "v191SportIndex?.groupFor(item)" in code
assert "v191ScheduleSportIndex(" in code
assert 'V188SportMode.verifiedAlternatives(' in code
assert 'V188VerifiedFps.verifiedCandidate(' in (ui/"PlayerScreen.kt").read_text()
assert 'V188SportContext.automaticOfferAllowed(' in (ui/"PlayerScreen.kt").read_text()
assert 'displayLease.match(fps, view, allow1080p = false, liveTv = true)' not in surface.read_text()
print("V191_VERIFIED_SPORTMODE_RETAINED_NO_LIVE_HDMI_SWITCH")
print("V191_CATEGORY_FOCUS_NOT_STOLEN_AND_NO_RELOAD_ON_WARM_OK")
print("V191_HEADER_ROWS_HIDDEN_AND_SPORT_LOOKUP_OFF_MAIN_THREAD")
