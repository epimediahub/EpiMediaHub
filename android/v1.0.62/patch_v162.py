#!/usr/bin/env python3
"""1.0.62: keep Live TV responsive while matching programme data."""
import ast
import os
from pathlib import Path
import shutil

root = Path(os.environ['PROJECT_ROOT'])
here = Path(__file__).resolve().parent
java = root / 'app/src/main/java/de/epimediahub/app'

def replace(path, old, new):
    source = path.read_text()
    if source.count(old) != 1:
        raise SystemExit(f'v162 expected one anchor in {path}: {old[:100]}')
    path.write_text(source.replace(old, new, 1))

gradle = root / 'app/build.gradle.kts'
replace(gradle, 'versionCode = 1061', 'versionCode = 1062')
replace(gradle, 'versionName = "1.0.61"', 'versionName = "1.0.62"')
shutil.copyfile(here / 'V162SmartEpg.kt', java / 'data/V162SmartEpg.kt')
tests = root / 'app/src/test/java/de/epimediahub/app/data'
tests.mkdir(parents=True, exist_ok=True)
shutil.copyfile(here / 'V162SmartEpgTest.kt', tests / 'V162SmartEpgTest.kt')

# Preserve the exact v161 matching policy while avoiding repeated Regex compilation.
replace(java / 'data/V161SmartEpg.kt',
    '    fun stationKey(name: String): String = Regex("[\\\\p{L}\\\\p{N}]+")',
    '    private val nameWords = Regex("[\\\\p{L}\\\\p{N}]+")\n\n'
    '    fun stationKey(name: String): String = nameWords')

vm = java / 'MainViewModel.kt'
replace(vm, 'import kotlinx.coroutines.sync.withLock',
    'import kotlinx.coroutines.sync.withLock\nimport kotlinx.coroutines.sync.withPermit')
replace(vm, '    private val back = ArrayDeque<Screen>()', '''    private val v162EpgRequests = V162EpgRequests()
    private val v162EpgSlots = kotlinx.coroutines.sync.Semaphore(2)
    private val v162EpgWorker = V162EpgWorker(viewModelScope) { input, guides ->
        val current = _ui.value
        val profile = current.active
        if (profile == null || catalogueKey(profile, MediaKind.LIVE) != input.profileKey ||
            current.epg !== input.guides || current.items !== input.items ||
            current.catalogRows !== input.rows) false
        else {
            val cached = libraryCatalogCache[input.profileKey]?.rows.orEmpty()
            if (cached !== input.cachedRows) false
            else _ui.compareAndSet(current, current.copy(epg = guides))
        }
    }
    private val back = ArrayDeque<Screen>()''')

# The central setter publishes immediately. It only passes immutable references
# to the background worker; no catalogue iteration, normalization or map copy.
source = vm.read_text()
start = source.index('    private fun set(block: (UiState) -> UiState) {')
end = source.index('\n    private fun refreshCollections()', start)
old = source[start:end]
if 'V161SmartEpg.enrich(channels, state.epg)' not in old:
    raise SystemExit('Expected the official v161 synchronous matcher')
new = '''    private fun set(block: (UiState) -> UiState) {
        val old = _ui.value
        val state = block(old)
        _ui.value = state
        val refresh = state.active != old.active || state.epg !== old.epg ||
            state.items !== old.items || state.catalogRows !== old.catalogRows
        if (!refresh) return
        val profile = state.active
        if (profile == null || state.epg.isEmpty()) {
            v162EpgWorker.submit(null)
            return
        }
        val key = catalogueKey(profile, MediaKind.LIVE)
        v162EpgWorker.submit(V162EpgInput(profile.id, key, state.items,
            state.catalogRows, libraryCatalogCache[key]?.rows.orEmpty(), state.epg))
    }
'''
vm.write_text(source[:start] + new + source[end:])

source = vm.read_text()
start = source.index('    fun ensureEpg(item: MediaEntry) {')
end = source.index('\n    fun play(', start)
new = '''    fun ensureEpg(item: MediaEntry) {
        val state = _ui.value
        if (state.epg[item.id]?.isNotEmpty() == true || item.kind != MediaKind.LIVE) return
        val p = state.active ?: return
        if (item.sourceProfileId.isNotBlank() && item.sourceProfileId != p.id) return
        val profileKey = catalogueKey(p, MediaKind.LIVE)
        val requestKey = profileKey + "|" + item.id
        if (!v162EpgRequests.acquire(requestKey, android.os.SystemClock.elapsedRealtime())) return
        viewModelScope.launch {
            var success = false
            try {
                val list = withContext(Dispatchers.IO) {
                    v162EpgSlots.withPermit {
                        currentCoroutineContext().ensureActive()
                        // A queued request from a previous playlist must not
                        // contact that provider after the user switches away.
                        if (_ui.value.active != p || _ui.value.epg[item.id]?.isNotEmpty() == true) emptyList()
                        else if (p.type == PlaylistType.XTREAM) XtreamClient(p).shortEpg(item.id)
                        else {
                            val playlist = m3uResult(p)
                            if (playlist.epgUrl.isBlank() || item.epgId.isBlank()) emptyList()
                            else XmlTvClient.nowNext(playlist.epgUrl, setOf(item.epgId))[item.epgId].orEmpty()
                        }
                    }
                }
                currentCoroutineContext().ensureActive()
                if (_ui.value.active == p && list.isNotEmpty()) {
                    success = true
                    set { it.copy(epg = it.epg + (item.id to list)) }
                }
            } catch (cancelled: kotlinx.coroutines.CancellationException) { throw cancelled }
            catch (_: Exception) { /* A missing programme must never block the channel list. */ }
            finally {
                v162EpgRequests.complete(requestKey, success, android.os.SystemClock.elapsedRealtime())
            }
        }
    }
'''
vm.write_text(source[:start] + new + source[end:])

live = java / 'ui/V076LiveTv.kt'
replace(live, '''    LaunchedEffect(selectedChannel?.id) {
        selectedChannel?.let { channel ->
            if (u.epg[channel.id].orEmpty().isEmpty()) vm.ensureEpg(channel)
        }
    }''', '''    LaunchedEffect(u.active?.id, selectedChannel?.id) {
        // Holding DOWN should move focus, not start a request for every row.
        delay(180L)
        selectedChannel?.let { channel -> vm.ensureEpg(channel) }
    }''')

assert 'state.catalogRows.values.flatten()' not in vm.read_text()
assert 'V161SmartEpg.enrich(' not in vm.read_text()
assert 'V113LiveTvKeys.channels' in live.read_text()
assert 'V153DirectPolicy.canPlay' in (java / 'vpn/V134VpnSession.kt').read_text()
print('v1.0.62: background indexed EPG, bounded requests and uninterrupted Live-TV focus.')
