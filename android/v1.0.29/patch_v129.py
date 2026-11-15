#!/usr/bin/env python3
"""Large catalogue regression fixes, reachable parental controls and automatic SmartTube Kids."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent

def replace(path, old, new, count=1):
    text = path.read_text()
    assert text.count(old) == count, f'{path}: expected {count} anchors, got {text.count(old)}: {old[:110]}'
    path.write_text(text.replace(old, new))

def between(path, first, last, new):
    text = path.read_text()
    start = text.index(first)
    end = text.index(last, start)
    path.write_text(text[:start] + new + text[end:])

replace(root / 'app/build.gradle.kts', 'versionCode = 1028', 'versionCode = 1029')
replace(root / 'app/build.gradle.kts', 'versionName = "1.0.28"', 'versionName = "1.0.29"')
for path in java.rglob('*.kt'):
    text = path.read_text()
    if '1.0.28' in text: path.write_text(text.replace('1.0.28', '1.0.29'))
for name in ('V129JsonRows.kt',):
    shutil.copyfile(here / name, java / 'data' / name)

parental = java / 'data/V128ParentalControl.kt'
between(parental, '    fun providerAdult(', '    fun restricted(', r'''    private val numericAge = Regex("(?:0|6|7|10|12|13|14|15|16|17|18|21)\\+?")
    private val namedAge = Regex("(?i)\\b(?:FSK|ab|age|rated)\\s*[:=-]?\\s*(0|6|12|16|18)\\b")
    private fun trueFlag(value: Any?): Boolean = value == true || value?.toString()?.trim()?.let {
        it == "1" || it.equals("true", true) || it.equals("yes", true)
    } == true
    fun providerAdult(data: JSONObject): Boolean = trueFlag(data.opt("is_adult")) || trueFlag(data.opt("adult"))

    fun providerAge(data: JSONObject): Int {
        var age = -1
        for (key in ageFields) {
            if (!data.has(key) || data.isNull(key)) continue
            val raw = data.optString(key).trim()
            if (raw.isEmpty()) continue
            val parsed = when {
                marked(raw) -> 18
                numericAge.matches(raw) -> raw.removeSuffix("+").toInt()
                else -> namedAge.find(raw)?.groupValues?.get(1)?.toInt() ?: -1
            }
            age = maxOf(age, parsed)
        }
        return age
    }

    fun bind(entries: List<MediaEntry>, categories: List<MediaCategory>): List<MediaEntry> {
        // Classify a category once, instead of repeating the expression for every title.
        val names = categories.associate { it.id to (it.name to (it.adult || marked(it.name))) }
        return entries.map { item ->
            val category = names[item.categoryId]
            val name = category?.first ?: item.categoryName
            val adult = item.adult || (category?.second ?: marked(name))
            if (item.categoryName == name && item.adult == adult) item
            else item.copy(categoryName = name, adult = adult)
        }
    }

''')

client = java / 'data/XtreamClient.kt'
text = client.read_text()
start = text.index('    fun entries(')
end = text.index('    fun details(', start)
entry = text[start:end]
entry = entry.replace('categoryId: String? = null)', 'categoryId: String? = null, checkActive: () -> Unit = {})')
a = entry.index('        val a = if (requestedCategory.isBlank())')
b = entry.index('        val streamServer', a)
entry = entry[:a] + entry[b:]
entry = entry.replace('''        return buildList {
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
''', '''        fun request(query: String): List<MediaEntry> = V129JsonRows.load(apiCandidates(action, query), checkActive) { o ->
                if (requestedCategory.isNotBlank() && query.isBlank() && o.optString("category_id") != requestedCategory) return@load null
''')
assert entry.count('                        add(\n                            MediaEntry(') == 3
entry = entry.replace('                        add(\n                            MediaEntry(', '                        MediaEntry(')
entry = entry.replace('                            )\n                        )', '                        )')
entry = entry.replace('                                kind = kind,', '                                kind = kind,\n                                sourceProfileId = p.id,')
entry = entry.replace('                    else -> Unit', '                    else -> null')
old_tail = '''                }
            }
        }
    }

'''
assert entry.endswith(old_tail)
entry = entry[:-len(old_tail)] + '''                }
        }
        return try { request(extra).filter { it.id.isNotBlank() }.distinctBy { it.id } }
        catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
        catch (failure: Exception) {
            if (requestedCategory.isBlank()) throw failure
            request("").filter { it.id.isNotBlank() }.distinctBy { it.id }
        }
    }

'''
client.write_text(text[:start] + entry + text[end:])
# VM-fatal errors and cancellation must never initiate another full response download.
replace(client, 'catch (t: Throwable)', 'catch (t: Exception)', count=2)

vm = java / 'MainViewModel.kt'
replace(vm, 'import kotlinx.coroutines.withContext', 'import kotlinx.coroutines.withContext\nimport kotlinx.coroutines.ensureActive\nimport kotlinx.coroutines.currentCoroutineContext\nimport kotlinx.coroutines.sync.withLock')
replace(vm, 'V128TimedCache<List<MediaEntry>>()', 'V128TimedCache<List<MediaEntry>>(limit = 1)')
replace(vm, 'V128TimedCache<V128LibraryCatalog>()', 'V128TimedCache<V128LibraryCatalog>(limit = 1)')
between(vm, '    private fun xtreamLibrary(', '    private fun catalogueKey(', '''    private val catalogueMutex = kotlinx.coroutines.sync.Mutex()
    private suspend fun xtreamLibrary(profile: PlaylistProfile, kind: MediaKind): List<MediaEntry> = catalogueMutex.withLock {
        val key = catalogueKey(profile, kind)
        xtreamLibraryCache[key]?.let { return@withLock it }
        // Only one large catalogue is retained on memory-constrained television sticks.
        xtreamLibraryCache.clear()
        val requestContext = currentCoroutineContext()
        XtreamClient(profile).entries(kind, checkActive = { requestContext.ensureActive() }).also {
            requestContext.ensureActive()
            xtreamLibraryCache[key] = it
        }
    }

''')
replace(vm, '        set { it.copy(loading = true, categories = emptyList(), catalogRows = emptyMap(), catalogRowsLoading = true,',
    '        libraryCatalogCache.clear()\n        set { it.copy(loading = true, categories = emptyList(), items = emptyList(), catalogRows = emptyMap(), catalogRowsLoading = true,')
replace(vm, '        val effective = parentalItem(item)\n        return V128AdultContent.restricted',
    '        if (!_ui.value.parentalSettings.hasPin || !_ui.value.parentalSettings.lockAdult) return false\n        val effective = parentalItem(item)\n        return V128AdultContent.restricted')
replace(vm, '            is Screen.Categories -> loadCategories(screen.kind)',
    '            is Screen.Categories -> { set { it.copy(contentFilterKind = screen.kind) }; loadCategories(screen.kind) }')
replace(vm, '        if (remember) back.addLast(_ui.value.screen)', '''        contentAccessJob?.cancel()
        if (screen !is Screen.Categories) { libraryLoadGeneration++; libraryLoadJob?.cancel() }
        if (screen != Screen.Search) { searchGeneration++; searchJob?.cancel() }
        if (remember) back.addLast(_ui.value.screen)''')
# Catch failed age-metadata requests; fail closed through the same PIN prompt instead of crashing.
replace(vm, '                        val categoriesRequest = async { if (needsCategories) XtreamClient(profile).categories(categoryKind) else null }',
    '                        val categoriesRequest = async { if (needsCategories) XtreamClient(profile).categories(categoryKind) else null }')
replace(vm, '                val (categories, detail) = withContext(Dispatchers.IO) {',
    '                try {\n                val (categories, detail) = withContext(Dispatchers.IO) {')
replace(vm, '                if (authorizeContent(item, approved)) approved()\n            }', '''                if (authorizeContent(item, approved)) approved()
                } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
                catch (_: Exception) {
                    set { it.copy(parentalChecking = false) }
                    requestParentalPin("Altersfreigabe nicht verfügbar · PIN erforderlich") {
                        set { it.copy(parentalGranted = it.parentalGranted + scope) }
                        approved()
                    }
                }
            }''')

ui = java / 'ui/V128ParentalUi.kt'
replace(ui, '    var removeConfirmation by remember { mutableStateOf(false) }', '''    var removeConfirmation by remember { mutableStateOf(false) }
    val setupFocus = remember { FocusRequester() }
    LaunchedEffect(Unit) { withFrameNanos { }; runCatching { setupFocus.requestFocus() } }
    fun configure(action: () -> Unit) {
        if (!settings.hasPin) { firstPin = null; setupError = ""; changePin = true }
        else action()
    }''')
replace(ui, 'modifier = Modifier.fillMaxWidth(), onClick = { firstPin = null;',
    'modifier = Modifier.fillMaxWidth().focusRequester(setupFocus).testTag("parental-setup"), onClick = { firstPin = null;')
replace(ui, 'settings.hasPin, accent) { vm.updateParentalSettings(adult = !settings.lockAdult) }',
    'settings.hasPin, accent) { configure { vm.updateParentalSettings(adult = !settings.lockAdult) } }')
replace(ui, 'settings.hasPin && settings.lockAdult, accent) { vm.updateParentalSettings(unrated = !settings.lockUnrated) }',
    'settings.hasPin && settings.lockAdult, accent) { configure { vm.updateParentalSettings(adult = true, unrated = !settings.lockUnrated) } }')
replace(ui, 'settings.hasPin, accent) { vm.updateParentalSettings(menu = !settings.lockMenu) }',
    'settings.hasPin, accent) { configure { vm.updateParentalSettings(menu = !settings.lockMenu) } }')
replace(ui, 'TextButton(onClick = onClick, enabled = enabled, modifier = Modifier.fillMaxWidth().v114FocusRing())',
    'TextButton(onClick = onClick, modifier = Modifier.fillMaxWidth().testTag("parental-toggle-$title").v114FocusRing())')
replace(ui, 'Text(title, color = if(enabled) Color.White else Color.White.copy(.5f)', 'Text(title, color = Color.White')
replace(ui, 'Text(detail, color = Color.White.copy(.68f)', 'Text(if (enabled) detail else "Auswählen, um die PIN und diesen Schutz einzurichten", color = Color.White.copy(.68f)')

replace(ui, '    val setupFocus = remember { FocusRequester() }',
    '    var pendingSetting by remember { mutableStateOf<(() -> Unit)?>(null) }\n    val setupFocus = remember { FocusRequester() }')
replace(ui, 'if (!settings.hasPin) { firstPin = null; setupError = ""; changePin = true }',
    'if (!settings.hasPin) { pendingSetting = action; firstPin = null; setupError = ""; changePin = true }')
replace(ui, 'if (success) { changePin = false; firstPin = null }',
    'if (success) { changePin = false; firstPin = null; pendingSetting?.invoke(); pendingSetting = null }')
replace(ui, 'onCancel = { changePin = false; firstPin = null }',
    'onCancel = { changePin = false; firstPin = null; pendingSetting = null }')

replace(vm, '    fun removeParentalPin() {', '''    fun refreshParentalSettings() {
        set { it.copy(parentalSettings = parental.settings(), parentalGranted = emptySet()) }
    }

    fun removeParentalPin() {''')
replace(vm, '                        val categories = categoryRequest.await()',
    '                        val categories = categoryRequest.await().distinctBy { it.id }')
# Discard outdated catalogue results even when a provider changes under the same playlist ID.
replace(vm, '        if (list != _ui.value.playlists) {',
    '        if (list != _ui.value.playlists) {\n            libraryLoadGeneration++; libraryLoadJob?.cancel()\n            contentAccessJob?.cancel(); cancelParentalPin()')

for name in ('V129KidsStore.kt', 'V129SmartTubeGate.kt'):
    shutil.copyfile(here / name, java / 'ui' / name)
home = java / 'ui/V083Home.kt'
replace(home, '        V112SmartTubeShell(', '        V129SmartTubeGate(')
app = java / 'EpiMediaHubApp.kt'
replace(app, '    val scope = rememberCoroutineScope()',
    '    val scope = rememberCoroutineScope()\n    val kidsSessionActive = v129RememberKidsActive()')
replace(app, '        } else if (u.parentalSettings.lockMenu && !u.parentalMenuUnlocked) {',
    '''        } else if (kidsSessionActive) {
            V129SmartTubeGate(vm, accent, isTv, onBack = {})
        } else if (u.parentalSettings.lockMenu && !u.parentalMenuUnlocked) {''')

core = java / 'ui/V108SmartTubeCore.kt'
replace(core, '    private var warmAccount: String? = null',
    '    private var warmAccount: String? = null\n    private val warmMutex = kotlinx.coroutines.sync.Mutex()')
replace(core, '    suspend fun warmPlayback(context: Context) = withContext(Dispatchers.IO) {',
    '    suspend fun warmPlayback(context: Context) = withContext(Dispatchers.IO) {\n        warmMutex.withLock {')
replace(core, '        catch (_: Exception) { /* The normal video request can retry a failed warm-up. */ }\n    }',
    '        catch (_: Exception) { /* The normal video request can retry a failed warm-up. */ }\n        }\n    }')
replace(core, '    suspend fun search(context:', '''    /** Isolated discovery: never replace an empty/failed Kids feed with the normal home feed. */
    suspend fun kids(context: Context): Result<List<V100SmartTubeRow>> = withContext(Dispatchers.IO) {
        try {
            val groups = collectGroups(manager(context).contentService.getKidsHomeObserve())
                .filter { it.type == MediaGroup.TYPE_KIDS_HOME }
            val rows = V129KidsCatalogue(mapGroups(groups)).rows
            check(rows.isNotEmpty()) { "Keine Kinderinhalte verfügbar. Bitte erneut versuchen." }
            Result.success(rows)
        } catch (cancelled: CancellationException) { throw cancelled }
        catch (failure: Exception) { Result.failure(failure) }
    }

    suspend fun search(context:''')
# Warm-up now starts on the mode chooser, before opening the normal video catalogue.
# Record distinct resolve/first-frame timing, without logging video URLs or accounts.
replace(core, '        val service = manager(context)\n        val account =',
    '        val resolveStarted = android.os.SystemClock.elapsedRealtime()\n        val service = manager(context)\n        val account =')
replace(core, '            rememberPlayback(cacheKey, it)',
    '            rememberPlayback(cacheKey, it)\n            android.util.Log.i("EpiSmartTube", "resolve_ms=" + (android.os.SystemClock.elapsedRealtime() - resolveStarted))')
shell = java / 'ui/V112SmartTubeShell.kt'
replace(shell, '    var firstFrameVideoId by remember { mutableStateOf<String?>(null) }',
    '    var firstFrameVideoId by remember { mutableStateOf<String?>(null) }\n    var clickStarted by remember { mutableLongStateOf(0L) }')
replace(shell, '        resolvingId = video.videoId',
    '        resolvingId = video.videoId\n        clickStarted = android.os.SystemClock.elapsedRealtime()')
replace(shell, 'onFirstFrame = { firstFrameVideoId = video.videoId }',
    'onFirstFrame = { firstFrameVideoId = video.videoId; android.util.Log.i("EpiSmartTube", "first_frame_ms=" + (android.os.SystemClock.elapsedRealtime() - clickStarted)) }')

tests = root / 'app/src/test/java/de/epimediahub/app/ui'
for source in here.glob('*Test.kt'):
    shutil.copyfile(source, tests / source.name)
print('Android 1.0.29: streaming catalogues, cheap age parsing, reachable PIN controls and automatic Kids catalogue installed')
