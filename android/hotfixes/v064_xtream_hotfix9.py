#!/usr/bin/env python3
from pathlib import Path
import os
import re

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# Version.
build = root / "app/build.gradle.kts"
replace_once(build, 'versionCode = 611', 'versionCode = 612', 'hotfix9 versionCode')
replace_once(build, 'versionName = "0.6.4.8"', 'versionName = "0.6.4.9"', 'hotfix9 versionName')
home = java / "ui/V044Home.kt"
replace_once(home, "0.6.4.8", "0.6.4.9", "hotfix9 visible version")

# Live zapping must replace the Player screen in-place rather than adding back-stack entries.
vm = java / "MainViewModel.kt"
s = vm.read_text()
old_state = '''    private val browsePositions = mutableMapOf<String, Int>()
    private val browseSelections = mutableMapOf<String, String>()
'''
new_state = '''    private val browsePositions = mutableMapOf<String, Int>()
    private val browseSelections = mutableMapOf<String, String>()
    private var liveZapGeneration = 0L
'''
if old_state not in s:
    raise SystemExit("live zap generation anchor missing")
s = s.replace(old_state, new_state, 1)
anchor = '''    fun playbackUrls(item: MediaEntry): List<String> {
'''
method = '''    fun switchLiveChannel(item: MediaEntry, channelList: List<MediaEntry>) {
        if (item.kind != MediaKind.LIVE || channelList.isEmpty()) return
        val sourceProfile = _ui.value.playlists.firstOrNull { it.id == item.sourceProfileId }
        val profile = sourceProfile ?: _ui.value.active ?: return
        val index = channelList.indexOfFirst { candidate ->
            candidate.id == item.id && (candidate.sourceProfileId == item.sourceProfileId || item.sourceProfileId.isBlank())
        }
        if (index >= 0 && item.categoryId.isNotBlank()) {
            rememberBrowserPosition(MediaKind.LIVE, item.categoryId, index, item.id)
        }
        val generation = ++liveZapGeneration
        if (profile.type == PlaylistType.XTREAM) {
            viewModelScope.launch {
                val prepared = runCatching {
                    withContext(Dispatchers.IO) { XtreamClient(profile).preparePlaybackItem(item) }
                }.getOrDefault(item)
                if (generation != liveZapGeneration || _ui.value.screen !is Screen.Player) return@launch
                set {
                    it.copy(
                        loading = false,
                        screen = Screen.Player(prepared.copy(sourceProfileId = profile.id), channelList),
                        error = ""
                    )
                }
            }
        } else {
            if (_ui.value.screen is Screen.Player) {
                set { it.copy(screen = Screen.Player(item.copy(sourceProfileId = profile.id), channelList), error = "") }
            }
        }
    }

    fun playbackUrls(item: MediaEntry): List<String> {
'''
if anchor not in s:
    raise SystemExit("switchLiveChannel insertion anchor missing")
s = s.replace(anchor, method, 1)
vm.write_text(s)

# Sender list: remember and restore the actual focused channel, and carry the category list into Player.
screens = java / "ui/Screens.kt"
s = screens.read_text()
import_anchor = 'import androidx.compose.ui.focus.onFocusChanged\n'
if import_anchor not in s:
    raise SystemExit("Screens focus import anchor missing")
s = s.replace(import_anchor, 'import androidx.compose.ui.focus.FocusRequester\nimport androidx.compose.ui.focus.focusRequester\n' + import_anchor, 1)
old_list_state = '''    val initial=remember(kind,cat.id,u.active?.id){vm.browserPosition(kind,cat.id)}
    val listState=rememberLazyListState(initialFirstVisibleItemIndex=initial)
'''
new_list_state = '''    val initial=remember(kind,cat.id,u.active?.id){vm.browserPosition(kind,cat.id)}
    val listState=rememberLazyListState(initialFirstVisibleItemIndex=initial)
    val rememberedId=vm.browserSelectedId(kind,cat.id)
    val channelFocusRequester=remember(kind,cat.id,u.active?.id){FocusRequester()}
    LaunchedEffect(isTv,kind,cat.id,rememberedId,u.items.size,u.loading){
        if(isTv && kind==MediaKind.LIVE && rememberedId.isNotBlank() && !u.loading){
            val rememberedIndex=u.items.indexOfFirst{it.id==rememberedId}
            if(rememberedIndex>=0){
                listState.scrollToItem(rememberedIndex)
                kotlinx.coroutines.delay(80)
                runCatching{channelFocusRequester.requestFocus()}
            }
        }
    }
'''
if old_list_state not in s:
    raise SystemExit("ItemsScreen list-state anchor missing")
s = s.replace(old_list_state, new_list_state, 1)
old_tv_live = '''                                LiveChannelRow(m,now?.let{"${clock(it.start)}–${clock(it.end)}  ${it.title}"}.orEmpty(),accent,isTv=true){
                                    vm.rememberBrowserPosition(kind,cat.id,index,m.id);vm.play(m)
                                }
'''
new_tv_live = '''                                val channelFocusModifier=if(rememberedId.isNotBlank()&&m.id==rememberedId) Modifier.focusRequester(channelFocusRequester) else Modifier
                                LiveChannelRow(m,now?.let{"${clock(it.start)}–${clock(it.end)}  ${it.title}"}.orEmpty(),accent,modifier=channelFocusModifier,isTv=true){
                                    vm.rememberBrowserPosition(kind,cat.id,index,m.id);vm.play(m,u.items)
                                }
'''
if old_tv_live not in s:
    raise SystemExit("TV LiveChannelRow anchor missing")
s = s.replace(old_tv_live, new_tv_live, 1)
old_mobile_live = '''                            LiveChannelRow(m,now?.title.orEmpty(),accent,isTv=false){vm.rememberBrowserPosition(kind,cat.id,index,m.id);vm.play(m)}
'''
new_mobile_live = '''                            LiveChannelRow(m,now?.title.orEmpty(),accent,isTv=false){vm.rememberBrowserPosition(kind,cat.id,index,m.id);vm.play(m,u.items)}
'''
if old_mobile_live not in s:
    raise SystemExit("mobile LiveChannelRow anchor missing")
s = s.replace(old_mobile_live, new_mobile_live, 1)
screens.write_text(s)

# Fire TV: Up = next channel, Down = previous channel. Key repeats are consumed to avoid provider flooding.
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
leave_anchor = '''    fun leave() {
'''
live_helpers = '''    fun switchLiveBy(direction: Int): Boolean {
        if (item.kind != MediaKind.LIVE) return false
        val channels = episodeList.filter { it.kind == MediaKind.LIVE }
        if (channels.isEmpty()) return true
        val currentIndex = channels.indexOfFirst { it.resumeKey == item.resumeKey }
        if (currentIndex < 0) return true
        val nextIndex = (currentIndex + direction + channels.size) % channels.size
        controls = true
        vm.switchLiveChannel(channels[nextIndex], channels)
        return true
    }

    fun leave() {
'''
if leave_anchor not in s:
    raise SystemExit("Player leave() anchor missing")
s = s.replace(leave_anchor, live_helpers, 1)
up_pattern = re.compile(r'(?m)^(\s*)KeyEvent\.KEYCODE_DPAD_UP\s*->\s*\{[^\n]*\}\s*$')
up_match = up_pattern.search(s)
if not up_match:
    raise SystemExit("Player DPAD_UP anchor missing")
up_indent = up_match.group(1)
s = up_pattern.sub(up_indent + 'KeyEvent.KEYCODE_DPAD_UP -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(1) else true}else{controls=true;false}', s, count=1)
down_pattern = re.compile(r'(?m)^(\s*)KeyEvent\.KEYCODE_DPAD_DOWN\s*->\s*\{[^\n]*\}\s*$')
down_match = down_pattern.search(s)
if not down_match:
    raise SystemExit("Player DPAD_DOWN anchor missing")
down_indent = down_match.group(1)
s = down_pattern.sub(down_indent + 'KeyEvent.KEYCODE_DPAD_DOWN -> if(item.kind==MediaKind.LIVE){if(e.nativeKeyEvent.repeatCount==0)switchLiveBy(-1) else true}else{controls=false;false}', s, count=1)
player.write_text(s)

# Only PlayerScreen handles Back while a Player is visible. Patch the stable Home clause instead of formatting around it.
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
back_marker = 'u.screen != Screen.Home &&'
if s.count(back_marker) != 1:
    raise SystemExit(f"global BackHandler Home marker count was {s.count(back_marker)}")
s = s.replace(back_marker, back_marker + '\n            u.screen !is Screen.Player &&', 1)
app.write_text(s)

checks = [
    (build, 'versionName = "0.6.4.9"'),
    (build, 'versionCode = 612'),
    (vm, 'fun switchLiveChannel(item: MediaEntry, channelList: List<MediaEntry>)'),
    (vm, 'private var liveZapGeneration = 0L'),
    (screens, 'val rememberedId=vm.browserSelectedId(kind,cat.id)'),
    (screens, 'Modifier.focusRequester(channelFocusRequester)'),
    (screens, 'vm.play(m,u.items)'),
    (player, 'fun switchLiveBy(direction: Int): Boolean'),
    (player, 'KeyEvent.KEYCODE_DPAD_UP -> if(item.kind==MediaKind.LIVE)'),
    (player, 'KeyEvent.KEYCODE_DPAD_DOWN -> if(item.kind==MediaKind.LIVE)'),
    (app, 'u.screen !is Screen.Player'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix9 marker {marker} in {path}")

print("Android v0.6.4.9 Live TV return-focus + Fire TV D-pad channel zapping hotfix applied")
