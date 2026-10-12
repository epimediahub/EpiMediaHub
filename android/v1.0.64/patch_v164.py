#!/usr/bin/env python3
"""Keep Live playback on OK, prompt programme banners and a visible boot switch."""
import hashlib
import os
import re
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
here = Path(__file__).resolve().parent
java = root / 'app/src/main/java/de/epimediahub/app'
tests = root / 'app/src/test/java/de/epimediahub/app'


def replace(path, old, new, count=1):
    source = path.read_text()
    if source.count(old) != count:
        raise SystemExit(f'v164 expected {count} anchors in {path}: {old[:100]}')
    path.write_text(source.replace(old, new, count))


gradle = root / 'app/build.gradle.kts'
replace(gradle, 'versionCode = 1063', 'versionCode = 1064')
replace(gradle, 'versionName = "1.0.63"', 'versionName = "1.0.64"')
for name, folder in [('V164LiveBrowser.kt', 'ui'), ('V164Epg.kt', 'data')]:
    shutil.copyfile(here / name, java / folder / name)
shutil.copyfile(here / 'V164BootSettings.kt', java / 'ui/V163BootSettings.kt')
for name, folder in [('V164LiveBrowserTest.kt', 'ui'), ('V164EpgTest.kt', 'data')]:
    shutil.copyfile(here / name, tests / folder / name)

vm = java / 'MainViewModel.kt'
replace(vm, '    val screen: Screen = Screen.Home,',
    '    val screen: Screen = Screen.Home,\n    val liveBackgroundPlayer: Screen.Player? = null,')
replace(vm, '        val state = block(old)\n        _ui.value = state',
    '        val state = de.epimediahub.app.ui.V164LiveNavigation.retain(old, block(old))\n        _ui.value = state')
replace(vm, '        if (remember) back.addLast(_ui.value.screen)',
    '        if (remember && !(_ui.value.liveBackgroundPlayer != null && screen is Screen.Player))\n            back.addLast(_ui.value.screen)')
replace(vm, '        set { it.copy(screen = screen, error = "") }',
    '        set { it.copy(screen = screen, liveBackgroundPlayer = null, error = "") }')
replace(vm, '    fun back() {', '''    fun back() {
        de.epimediahub.app.ui.V164LiveNavigation.resume(_ui.value)?.let { playing ->
            set { it.copy(screen = playing, liveBackgroundPlayer = null, error = "") }
            return
        }''')
old = '''        // Pop the old category screen instead of adding the player to its history.
        val categoryIndex = back.indexOfLast { it == Screen.Categories(MediaKind.LIVE) }
        if (categoryIndex >= 0) while (back.size > categoryIndex) back.removeLast()
        else back.removeAll { it is Screen.Player }
        navigate(Screen.Categories(MediaKind.LIVE), remember = false)'''
replace(vm, old, '''        val playing = _ui.value.screen as? Screen.Player ?: return
        // Preserve the existing back stack: only OK opens this retained session.
        set { it.copy(screen = Screen.Categories(MediaKind.LIVE), liveBackgroundPlayer = playing,
            contentFilterKind = MediaKind.LIVE, error = "") }
        loadCategories(MediaKind.LIVE)''')
replace(vm, '    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {',
    '''    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {
        val held = de.epimediahub.app.ui.V164LiveNavigation.resume(_ui.value)
        if (held != null && item.kind == MediaKind.LIVE && item.id == held.item.id &&
            (item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() } ==
                held.item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() })) {
            back()
            return
        }''')

# Build the safe station index even before the first guide has arrived.
replace(vm, '        if (profile == null || state.epg.isEmpty()) {', '        if (profile == null) {')
replace(vm, '        if (state.active != old.active) {',
    '''        if (state.active?.let { catalogueKey(it, MediaKind.LIVE) } !=
                old.active?.let { catalogueKey(it, MediaKind.LIVE) }) {''')
# Credential/catalogue identity governs EPG work, rather than unrelated metadata.
start = vm.read_text().index('    fun ensureEpg(item: MediaEntry, priority: Boolean = false) {')
end = vm.read_text().index('\n    fun openLiveChannels(', start)
source = vm.read_text()
epg = source[start:end]
epg = epg.replace('        val revision = v163EpgRevision',
    '        val profileKey = catalogueKey(p, MediaKind.LIVE)\n        val revision = v163EpgRevision')
epg = epg.replace('_ui.value.active != p',
    '_ui.value.active?.let { catalogueKey(it, MediaKind.LIVE) } != profileKey')
epg = epg.replace('else if (p.type == PlaylistType.XTREAM) XtreamClient(p).shortEpg(item.id)',
    '''else if (p.type == PlaylistType.XTREAM) V164Epg.load(item.id,
                    peers = { v162EpgWorker.peers(profileKey, item.id) },
                    cached = { id -> _ui.value.epg[id].orEmpty() },
                    fetch = { id -> XtreamClient(p).shortEpg(id) },
                    publish = { id, events ->
                        // These callbacks run off-thread; publish only after returning to Main.
                    })''')
# A donor is returned to the playing ID; the existing worker safely shares it.
# Keep the loader callback empty here to avoid writing StateFlow from the IO thread.
vm.write_text(source[:start] + epg + source[end:])
worker = java / 'data/V162SmartEpg.kt'
source = worker.read_text()
anchor = '    fun submit(input: V162EpgInput?) = synchronized(lock) {'
replace(worker, anchor, '''    fun peers(profileKey: String, id: String): List<String> = synchronized(lock) {
        if (indexedInput?.profileKey != profileKey) emptyList()
        else index?.groups?.firstOrNull { id in it }?.filter { it != id }?.take(2).orEmpty()
    }

''' + anchor)
queue = java / 'data/V163EpgQueue.kt'
replace(queue,
    '        if (failedAt[key]?.let { clock() - it < retryAfterMs } == true) return@synchronized false',
    '''        val cooldown = if (priority) minOf(retryAfterMs, 1_500L) else retryAfterMs
        if (failedAt[key]?.let { clock() - it < cooldown } == true) return@synchronized false''')
banner = java / 'ui/V163EpgBanner.kt'
replace(banner, '    LaunchedEffect(item.resumeKey, now) { vm.ensureEpg(item, priority = true) }',
    '''    LaunchedEffect(item.resumeKey, current?.start, current?.end, now) {
        // Missing/empty first replies retry while the same sender stays open.
        // The queue coalesces pending work and applies the playback cooldown.
        repeat(if (current == null) 8 else 1) {
            vm.ensureEpg(item, priority = true)
            if (current == null) delay(1_600L)
        }
    }''')
client = java / 'data/XtreamClient.kt'
replace(client, '                connectTimeout = 10000\n                readTimeout = 25000',
    '''                connectTimeout = if (safeRequestName(url) == "get_short_epg") 3_000 else 10000
                readTimeout = if (safeRequestName(url) == "get_short_epg") 5_000 else 25000''')
replace(client, '&limit=4', '&limit=12')
replace(client, '                        o.optLong("start_timestamp"),\n                        o.optLong("stop_timestamp")',
    '''                        V164Epg.seconds(o.optLong("start_timestamp")),
                        V164Epg.seconds(o.optLong("stop_timestamp", o.optLong("end_timestamp")))''')

player = java / 'ui/PlayerScreen.kt'
replace(player, 'import androidx.compose.ui.focus.focusRequester',
    'import androidx.compose.ui.focus.focusRequester\nimport androidx.compose.ui.focus.focusProperties')
replace(player, '    startUrl: String,\n    onSwitchPlayer:',
    '    startUrl: String,\n    covered: Boolean,\n    onSwitchPlayer:')
replace(player, 'accent: Color, isTv: Boolean) {\n    // Fire OS',
    'accent: Color, isTv: Boolean, covered: Boolean = false) {\n    // Fire OS')
replace(player, 'V071VlcLivePlayer(vm, item, episodeList, accent, isTv, compatibilityUrl)',
    'V071VlcLivePlayer(vm, item, episodeList, accent, isTv, compatibilityUrl, covered)')
replace(player, '    BackHandler { vm.back() }', '    BackHandler(enabled = !covered) { vm.back() }')
replace(player, '    BackHandler { leave() }', '    BackHandler(enabled = !covered) { leave() }')
source = player.read_text()
source = source.replace('if (it.nativeKeyEvent.action != KeyEvent.ACTION_DOWN)',
    'if (covered || it.nativeKeyEvent.action != KeyEvent.ACTION_DOWN)')
source = source.replace('if (!isTv || e.nativeKeyEvent.action != KeyEvent.ACTION_DOWN)',
    'if (covered || !isTv || e.nativeKeyEvent.action != KeyEvent.ACTION_DOWN)')
source = source.replace('.focusRequester(focusRequester)',
    '.focusProperties { canFocus = !covered }.focusRequester(focusRequester)')
source = re.sub(r'(?<!\})\.focusRequester\((\w+)\)',
    r'.focusProperties { canFocus = !covered }.focusRequester(\1)', source)
source = source.replace('    LaunchedEffect(item.resumeKey) {\n        runCatching { focusRequester.requestFocus() }',
    '    LaunchedEffect(item.resumeKey, covered) {\n        if (!covered) runCatching { focusRequester.requestFocus() }')
source = source.replace('    LaunchedEffect(item.resumeKey, controls) {',
    '    LaunchedEffect(item.resumeKey, controls, nowProgramme) {')
source = source.replace('        if (controls) {', '        if (controls && !covered) {')
source = source.replace('    val nowProgramme = V163EpgBanner(vm, item, u.epg[item.id].orEmpty())',
    '''    val nowProgramme = V163EpgBanner(vm, item, u.epg[item.id].orEmpty())
    LaunchedEffect(nowProgramme) {
        if (nowProgramme.isNotBlank() && !covered) controls = true
    }''')
# Returning from the browser restores the player's own focus target as well.
main_start = source.index('fun PlayerScreen(')
for begin, end in [(0, main_start), (main_start, len(source))][::-1]:
    block = source[begin:end]
    targets = re.findall(r'val (\w+)\s*=\s*remember[^\n]*\{ FocusRequester\(\) \}', block)
    if targets:
        anchor = '    BackHandler(enabled = !covered)'
        pos = block.index(anchor)
        restoration = '''    LaunchedEffect(covered) {
        if (!covered) {
            controls = true
            runCatching { %s.requestFocus() }
        }
    }

''' % targets[0]
        block = block[:pos] + restoration + block[pos:]
        source = source[:begin] + block + source[end:]
player.write_text(source)

app = java / 'EpiMediaHubApp.kt'
source = app.read_text()
anchor = '            when (val s = u.screen) {'
if source.count(anchor) != 1: raise SystemExit('Expected one application screen switch')
source = source.replace(anchor, '''            V164PlayerHost(u.screen, u.liveBackgroundPlayer,
                player = { playing, covered ->
                    PlayerScreen(vm, playing.item, playing.episodeList, accent, isTv, covered)
                }, browser = {
            when (val s = u.screen) {''', 1)
source = source.replace('                is Screen.Player -> PlayerScreen(vm, s.item, s.episodeList, accent, isTv)',
    '                is Screen.Player -> Unit')
anchor = '                is Screen.Player -> Unit\n            }'
if source.count(anchor) != 1: raise SystemExit('Expected application player route at end of switch')
source = source.replace(anchor, anchor + '\n            })', 1)
app.write_text(source)

# Add a trailing content slot to the shared focus card; other callers keep defaults.
common = java / 'ui/Common.kt'
source = common.read_text()
start = source.index('fun FocusCard(')
end = source.index('\n@Composable\nfun EpiTopBar(', start)
card = source[start:end]
card = card.replace('    modifier: Modifier = Modifier\n',
    '    modifier: Modifier = Modifier,\n    trailing: (@Composable () -> Unit)? = null\n', 1)
anchor = '            }\n        }\n    }\n}'
if card.count(anchor) != 1: raise SystemExit('Expected FocusCard content-row ending')
card = card.replace(anchor, '            }\n            trailing?.invoke()\n        }\n    }\n}', 1)
common.write_text(source[:start] + card + source[end:])

video = here / 'epimedia_intro_v6.mp4'
if not video.is_file(): raise SystemExit('Orchestral video must be generated before v164 patch')
shutil.copyfile(video, root / 'app/src/main/res/raw/epimedia_intro_v5.mp4')
print('v1.0.64: retained Live OK session, visible boot switch, prompt EPG and sampled orchestra intro.')
print('Embedded orchestral intro SHA256:', hashlib.sha256(video.read_bytes()).hexdigest())
