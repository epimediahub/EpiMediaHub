#!/usr/bin/env python3
"""1.0.63: normal Live-TV navigation, focused boot card and prompt EPG information."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
here = Path(__file__).resolve().parent
java = root / 'app/src/main/java/de/epimediahub/app'
tests = root / 'app/src/test/java/de/epimediahub/app'

def replace(path, old, new, count=1):
    source = path.read_text()
    if source.count(old) != count:
        raise SystemExit(f'v163 expected {count} anchors in {path}: {old[:100]}')
    path.write_text(source.replace(old, new, count))

gradle = root / 'app/build.gradle.kts'
replace(gradle, 'versionCode = 1062', 'versionCode = 1063')
replace(gradle, 'versionName = "1.0.62"', 'versionName = "1.0.63"')
shutil.copyfile(here / 'V163EpgQueue.kt', java / 'data/V163EpgQueue.kt')
for name in ('V163LiveSelection.kt', 'V163EpgBanner.kt', 'V163BootSettings.kt', 'V163LiveInfo.kt'):
    shutil.copyfile(here / name, java / 'ui' / name)
for name, folder in (('V163EpgQueueTest.kt', 'data'), ('V163LiveUiTest.kt', 'ui'), ('V163LiveSelectionTest.kt', 'ui')):
    shutil.copyfile(here / name, tests / folder / name)

settings = java / 'ui/Screens.kt'
replace(settings, '''            item {
                GlassPanel(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        V159BootSettingsToggle()
                    }
                }
            }''', '''            item {
                V163BootSettingsCard(accent)
            }''')

vm = java / 'MainViewModel.kt'
replace(vm, '''    private val v162EpgRequests = V162EpgRequests()
    private val v162EpgSlots = kotlinx.coroutines.sync.Semaphore(2)''', '''    private var v163EpgRevision = 0L
    private val v163EpgQueue = V163EpgQueue(viewModelScope)''')
replace(vm, '''        _ui.value = state
        val refresh =''', '''        _ui.value = state
        if (state.active != old.active) {
            v163EpgRevision++
            v163EpgQueue.clear()
        }
        val refresh =''')
source = vm.read_text()
start = source.index('    fun ensureEpg(item: MediaEntry) {')
end = source.index('\n    fun play(', start)
source = source[:start] + '''    fun ensureEpg(item: MediaEntry, priority: Boolean = false) {
        val state = _ui.value
        if (item.kind != MediaKind.LIVE ||
            V163Epg.current(state.epg[item.id].orEmpty(), System.currentTimeMillis() / 1000L) != null) return
        val p = state.active ?: return
        if (item.sourceProfileId.isNotBlank() && item.sourceProfileId != p.id) return
        val revision = v163EpgRevision
        val requestKey = catalogueKey(p, MediaKind.LIVE) + "|" + item.id
        v163EpgQueue.submit(requestKey, priority) {
            if (revision != v163EpgRevision || _ui.value.active != p) return@submit true
            if (V163Epg.current(_ui.value.epg[item.id].orEmpty(), System.currentTimeMillis() / 1000L) != null)
                return@submit true
            val list = withContext(Dispatchers.IO) {
                currentCoroutineContext().ensureActive()
                if (revision != v163EpgRevision || _ui.value.active != p) emptyList()
                else if (p.type == PlaylistType.XTREAM) XtreamClient(p).shortEpg(item.id)
                else {
                    val playlist = m3uResult(p)
                    if (playlist.epgUrl.isBlank() || item.epgId.isBlank()) emptyList()
                    else XmlTvClient.nowNext(playlist.epgUrl, setOf(item.epgId))[item.epgId].orEmpty()
                }
            }
            currentCoroutineContext().ensureActive()
            if (revision != v163EpgRevision || _ui.value.active != p) return@submit true
            if (list.isNotEmpty()) set { it.copy(epg = it.epg + (item.id to list)) }
            V163Epg.current(list, System.currentTimeMillis() / 1000L) != null
        }
    }

    fun openLiveChannels(item: MediaEntry, channelList: List<MediaEntry>) {
        if (item.kind != MediaKind.LIVE || _ui.value.screen !is Screen.Player) return
        val source = _ui.value.playlists.firstOrNull { it.id == item.sourceProfileId }
        if (source != null && source != _ui.value.active) selectPlaylist(source.id)
        val profile = _ui.value.active ?: return
        val cached = libraryCatalogCache[catalogueKey(profile, MediaKind.LIVE)]
        val rows = cached?.rows ?: _ui.value.catalogRows.takeIf {
            _ui.value.contentFilterKind == MediaKind.LIVE
        }.orEmpty()
        val selected = de.epimediahub.app.ui.V163LiveSelection.resolve(item,
            rememberedLibraryCategory(MediaKind.LIVE), rows, channelList)
        rememberLibraryCategory(MediaKind.LIVE, selected.categoryId)
        rememberBrowserPosition(MediaKind.LIVE, selected.categoryId, selected.index, item.id)
        val key = de.epimediahub.app.ui.V113LiveTvKeys.channels(profile.id, selected.categoryId)
        de.epimediahub.app.ui.V111MenuMemory.rememberFocus(key, selected.index, item.id,
            de.epimediahub.app.ui.V113LiveTvKeys.focus(profile.id))
        de.epimediahub.app.ui.V111MenuMemory.rememberScroll(key, selected.index, 0)
        // Pop the old category screen instead of adding the player to its history.
        val categoryIndex = back.indexOfLast { it == Screen.Categories(MediaKind.LIVE) }
        if (categoryIndex >= 0) while (back.size > categoryIndex) back.removeLast()
        else back.removeAll { it is Screen.Player }
        navigate(Screen.Categories(MediaKind.LIVE), remember = false)
    }
''' + source[end:]
vm.write_text(source)
replace(vm, '''        val profile = sourceProfile ?: _ui.value.active
        if (item.kind == MediaKind.LIVE && profile''', '''        val profile = sourceProfile ?: _ui.value.active
        if (item.kind == MediaKind.LIVE) ensureEpg(item, priority = true)
        if (item.kind == MediaKind.LIVE && profile''')
replace(vm, '''        val profile = sourceProfile ?: _ui.value.active ?: return
        val index = channelList.indexOfFirst''', '''        val profile = sourceProfile ?: _ui.value.active ?: return
        ensureEpg(item, priority = true)
        val index = channelList.indexOfFirst''')

player = java / 'ui/PlayerScreen.kt'
replace(player, '    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()',
    '    val nowProgramme = V163EpgBanner(vm, item, u.epg[item.id].orEmpty())', 2)
replace(player, '    var showChannelList by remember(item.resumeKey) { mutableStateOf(false) }\n', '', 2)
for channels in ('channelList', 'episodeList'):
    replace(player, f'''    if (showChannelList) V159ChannelOverlay({channels}, item, isTv,
        onChoose = {{ channel -> showChannelList = false; vm.switchLiveChannel(channel, {channels}) }},
        onDismiss = {{ showChannelList = false }})\n''', '')
replace(player, '    BackHandler { if (showChannelList) showChannelList = false else vm.back() }', '    BackHandler { vm.back() }')
replace(player, '    BackHandler { if (showChannelList) showChannelList = false else leave() }', '    BackHandler { leave() }')
source = player.read_text()
anchor = 'if (it.nativeKeyEvent.repeatCount == 0 && !showPlaybackInfo) showChannelList = true'
replace(player, anchor, 'if (it.nativeKeyEvent.repeatCount == 0 && !showPlaybackInfo) vm.openLiveChannels(item, channelList)')
replace(player, 'if (e.nativeKeyEvent.repeatCount == 0 && !showPlaybackInfo) showChannelList = true',
    'if (e.nativeKeyEvent.repeatCount == 0 && !showPlaybackInfo) vm.openLiveChannels(item, episodeList)')
# Both mobile buttons have the same anchor; assign the appropriate player list in order.
source = player.read_text()
old = 'onClick = { showChannelList = true },'
if source.count(old) != 2: raise SystemExit('Expected two mobile channel buttons')
source = source.replace(old, 'onClick = { vm.openLiveChannels(item, channelList) },', 1)
source = source.replace(old, 'onClick = { vm.openLiveChannels(item, episodeList) },', 1)
source = source.replace('        if (!isTv) TextButton(', '        if (!isTv && item.kind == MediaKind.LIVE) TextButton(')
player.write_text(source)

live = java / 'ui/V076LiveTv.kt'
source = live.read_text()
start = source.index('@Composable\nprivate fun V076InfoPane(')
end = source.index('\n@Composable\nprivate fun V076ProgrammeLine(', start)
source = source[:start] + '''@Composable
private fun V076InfoPane(
    vm: MainViewModel, channel: MediaEntry?, accent: Color, compact: Boolean,
    modifier: Modifier = Modifier
) {
    val u by vm.ui.collectAsState()
    val skin = u.themeCatalog?.themes?.get(u.themeId)
    val mark = remember(u.themeId) {
        vm.themeRepo().bannerMarkRes(u.themeId).takeIf { it != 0 }
            ?: vm.themeRepo().centerMarkRes(u.themeId).takeIf { it != 0 }
            ?: vm.themeRepo().markRes(u.themeId)
    }
    V163LiveInfoPanel(channel, channel?.let { u.epg[it.id].orEmpty() }.orEmpty(),
        accent, compact, modifier, mark, skin?.logoUrl.orEmpty(),
        V097PrivateDisplayLabel(skin?.label.orEmpty(), skin?.family == true))
}
''' + source[end:]
live.write_text(source)
assert 'V159ChannelOverlay(' not in player.read_text()
assert 'showChannelList' not in player.read_text()
assert 'V161SmartEpg.enrich(' not in vm.read_text()
assert 'V153DirectPolicy.canPlay' in (java / 'vpn/V134VpnSession.kt').read_text()
assert 'V159BootSettingsToggle()' not in settings.read_text()
print('v1.0.63: full Live categories on OK, focused autostart, priority EPG and readable programme descriptions.')
