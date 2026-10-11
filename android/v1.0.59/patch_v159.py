#!/usr/bin/env python3
"""v1.0.59 development patch: Live channel overlay, repeat seek and boot opt-in.

Apply only on top of v1.0.58. No changes to player URL routing, VPN or updater.
"""
from pathlib import Path
import os, shutil

root=Path(os.environ["PROJECT_ROOT"])
here=Path(__file__).resolve().parent
java=root/"app/src/main/java/de/epimediahub/app"

def replace(path, old, new, count=1):
    src=path.read_text()
    actual=src.count(old)
    if actual!=count:
        raise SystemExit(f"Anchor failed: {path} ({actual} != {count}): {old[:140]}")
    path.write_text(src.replace(old,new,count))

gradle=root/"app/build.gradle.kts"
replace(gradle,"versionCode = 1058","versionCode = 1059")
replace(gradle,'versionName = "1.0.58"','versionName = "1.0.59"')

# New opt-in preference/receiver and lightweight list dialog.
for name in ["V159ChannelOverlay.kt","V159BootAutostart.kt"]:
    shutil.copyfile(here/name,java/"ui"/name)

manifest=root/"app/src/main/AndroidManifest.xml"
replace(manifest,
        '    <uses-permission android:name="android.permission.INTERNET" />',
        '    <uses-permission android:name="android.permission.INTERNET" />\n'
        '    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />')
replace(manifest,"    </application>",
'''        <receiver android:name="de.epimediahub.app.ui.V159BootReceiver"
            android:enabled="true" android:exported="false">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>
    </application>''')

settings=java/"ui/Screens.kt"
replace(settings,
'''            item {
                GlassPanel(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        Text("Android v1.0.33", fontWeight = FontWeight.Bold)''',
'''            item {
                GlassPanel(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        V159BootSettingsToggle()
                    }
                }
            }
            item {
                GlassPanel(Modifier.fillMaxWidth()) {
                    Column(Modifier.padding(20.dp)) {
                        Text("Android v1.0.33", fontWeight = FontWeight.Bold)''')

chrome=java/"ui/V115PlayerChrome.kt"
replace(chrome,
'''    var consumeCenterUp by remember { mutableStateOf(false) }''',
'''    var consumeCenterUp by remember { mutableStateOf(false) }
    var heldSeekDirection by remember(item.resumeKey) { mutableIntStateOf(0) }
    val seekLatest by rememberUpdatedState(onSeekBy)
    // Native D-pad repeat cadence differs across Fire TV/Android TV/GalaBox.
    // Drive smooth seeking ourselves only after the initial short 10-second step.
    LaunchedEffect(heldSeekDirection) {
        if (heldSeekDirection != 0) {
            delay(340L)
            while (true) {
                seekLatest(heldSeekDirection * 10_000L)
                delay(300L)
            }
        }
    }''')
replace(chrome,
'''                if (native.action == KeyEvent.ACTION_UP) {
                    if (center && consumeCenterUp) { consumeCenterUp = false; true } else mediaKey
                } else if (native.action != KeyEvent.ACTION_DOWN || dialog != null) false''',
'''                val seekKey = code == KeyEvent.KEYCODE_DPAD_LEFT || code == KeyEvent.KEYCODE_DPAD_RIGHT
                if (native.action == KeyEvent.ACTION_UP) {
                    when {
                        seekKey && heldSeekDirection != 0 -> { heldSeekDirection = 0; true }
                        center && consumeCenterUp -> { consumeCenterUp = false; true }
                        else -> mediaKey
                    }
                } else if (native.action != KeyEvent.ACTION_DOWN || dialog != null) {
                    if (seekKey) heldSeekDirection = 0
                    false
                }''')
replace(chrome,
'''                        !isTv -> false
                        center && rootFocused -> {''',
'''                        !isTv -> false
                        seekKey && heldSeekDirection != 0 -> true // prevent repeat events from duplicating timed seeks
                        center && rootFocused -> {''')
replace(chrome,
'''                        code == KeyEvent.KEYCODE_DPAD_LEFT && !controls && (!nextVisible || rootFocused) -> { onSeekBy(-10_000L); touch(cancelAutomaticNext = true); restore = "play"; true }
                        code == KeyEvent.KEYCODE_DPAD_RIGHT && !controls && (!nextVisible || rootFocused) -> { onSeekBy(10_000L); touch(cancelAutomaticNext = true); restore = "play"; true }''',
'''                        code == KeyEvent.KEYCODE_DPAD_LEFT && !controls && (!nextVisible || rootFocused) -> {
                            heldSeekDirection = -1
                            onSeekBy(-10_000L); touch(cancelAutomaticNext = true); restore = "play"; true
                        }
                        code == KeyEvent.KEYCODE_DPAD_RIGHT && !controls && (!nextVisible || rootFocused) -> {
                            heldSeekDirection = 1
                            onSeekBy(10_000L); touch(cancelAutomaticNext = true); restore = "play"; true
                        }''')

player=java/"ui/PlayerScreen.kt"
replace(player,
'''    var showPlaybackInfo by remember(item.resumeKey) { mutableStateOf(false) }''',
'''    var showPlaybackInfo by remember(item.resumeKey) { mutableStateOf(false) }
    var showChannelList by remember(item.resumeKey) { mutableStateOf(false) }''',count=2)
replace(player,
'''    if (showPlaybackInfo) V122PlaybackInfoDialog(isTv, { showPlaybackInfo = false },
        compatibility = true, onSwitchPlayer = onSwitchPlayer)''',
'''    if (showPlaybackInfo) V122PlaybackInfoDialog(isTv, { showPlaybackInfo = false },
        compatibility = true, onSwitchPlayer = onSwitchPlayer)
    if (showChannelList) V159ChannelOverlay(channelList, item, isTv,
        onChoose = { channel -> showChannelList = false; vm.switchLiveChannel(channel, channelList) },
        onDismiss = { showChannelList = false })''')
replace(player,
'''    if (showPlaybackInfo) V122PlaybackInfoDialog(isTv, { showPlaybackInfo = false },
        onSwitchPlayer = { manualPlayerChoice = true; useVlc = true })''',
'''    if (showPlaybackInfo) V122PlaybackInfoDialog(isTv, { showPlaybackInfo = false },
        onSwitchPlayer = { manualPlayerChoice = true; useVlc = true })
    if (showChannelList) V159ChannelOverlay(episodeList, item, isTv,
        onChoose = { channel -> showChannelList = false; vm.switchLiveChannel(channel, episodeList) },
        onDismiss = { showChannelList = false })''')
replace(player,'    BackHandler { vm.back() }','    BackHandler { if (showChannelList) showChannelList = false else vm.back() }')
replace(player,'    BackHandler { leave() }','    BackHandler { if (showChannelList) showChannelList = false else leave() }')
replace(player,
'''                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                        controls = !controls
                        true
                    }''',
'''                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER,
                    KeyEvent.KEYCODE_NUMPAD_ENTER -> {
                        if (it.nativeKeyEvent.repeatCount == 0 && !showPlaybackInfo) showChannelList = true
                        true
                    }''')
replace(player,
'''                    KeyEvent.KEYCODE_DPAD_CENTER,
                    KeyEvent.KEYCODE_ENTER -> { controls = !controls; true }''',
'''                    KeyEvent.KEYCODE_DPAD_CENTER,
                    KeyEvent.KEYCODE_ENTER,
                    KeyEvent.KEYCODE_NUMPAD_ENTER -> {
                        if (e.nativeKeyEvent.repeatCount == 0 && !showPlaybackInfo) showChannelList = true
                        true
                    }''')
replace(player,
'''        if (controls) {
            Surface(
                modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(horizontal = 24.dp, vertical = 26.dp),''',
'''        if (!isTv) TextButton(
            onClick = { showChannelList = true },
            modifier = Modifier.align(Alignment.TopEnd).padding(16.dp)
        ) { Text("Kanalliste", color = Color.White) }
        if (controls) {
            Surface(
                modifier = Modifier.align(Alignment.BottomCenter).fillMaxWidth().padding(horizontal = 24.dp, vertical = 26.dp),''')
replace(player,
'''        V121VodSurface(player, isTv, Modifier.fillMaxSize())

        if (item.kind == MediaKind.LIVE && controls) {''',
'''        V121VodSurface(player, isTv, Modifier.fillMaxSize())
        if (!isTv) TextButton(
            onClick = { showChannelList = true },
            modifier = Modifier.align(Alignment.TopEnd).padding(16.dp)
        ) { Text("Kanalliste", color = Color.White) }

        if (item.kind == MediaKind.LIVE && controls) {''')

assert 'V159ChannelOverlay(channelList, item, isTv' in player.read_text()
assert 'V159ChannelOverlay(episodeList, item, isTv' in player.read_text()
assert 'heldSeekDirection' in chrome.read_text()
assert 'android.permission.RECEIVE_BOOT_COMPLETED' in manifest.read_text()
assert 'V159BootSettingsToggle()' in settings.read_text()
assert 'V156ExactM3uCache.resolve(' in (java/"data/XtreamClient.kt").read_text()
print("v1.0.59 development: OK Live channel list, hold seek, opt-in boot toggle.")
print("No automatic update release. No playback URL or VPN modifications.")
