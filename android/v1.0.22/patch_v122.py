#!/usr/bin/env python3
"""Use the stable video surface for live TV, recover absent FPS and expose real playback data."""
import os
from pathlib import Path
import shutil

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent


def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f"{path}: expected one anchor, got {text.count(old)}: {old[:100]}"
    path.write_text(text.replace(old, new, 1))


gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 1021', 'versionCode = 1022')
replace_once(gradle, 'versionName = "1.0.21"', 'versionName = "1.0.22"')
for path in java.rglob("*.kt"):
    text = path.read_text()
    if "1.0.21" in text:
        path.write_text(text.replace("1.0.21", "1.0.22"))
for name in ("V121VodSurface.kt", "V122FrameRateEstimator.kt", "V122PlaybackInfo.kt"):
    shutil.copyfile(here / name, java / "ui" / name)

player = java / "ui/PlayerScreen.kt"
replace_once(player, '''        AndroidView(
            factory = {
                PlayerView(it).apply {
                    this.player = player
                    useController = item.kind != MediaKind.LIVE && !isTv
                    controllerAutoShow = item.kind != MediaKind.LIVE && !isTv
                    if (item.kind == MediaKind.LIVE || isTv) hideController()
                }
            },
            update = {
                it.player = player
                it.useController = item.kind != MediaKind.LIVE && !isTv
                it.controllerAutoShow = item.kind != MediaKind.LIVE && !isTv
                if (item.kind == MediaKind.LIVE || isTv) it.hideController()
            },
            modifier = Modifier.fillMaxSize()
        )''', '''        V121VodSurface(player, isTv, Modifier.fillMaxSize())''')

# The Fire TV Menu button opens diagnostics without silently switching the decoder.
# Compatibility remains a clearly labelled action inside the dialog and the controls.
replace_once(player, '''                    KeyEvent.KEYCODE_MENU -> {
                        if (it.nativeKeyEvent.repeatCount == 0) onSwitchPlayer()
                        true
                    }''', '''                    KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_INFO -> {
                        if (it.nativeKeyEvent.repeatCount == 0) showPlaybackInfo = true
                        true
                    }''')
replace_once(player, '''                    KeyEvent.KEYCODE_MENU -> {
                        if (item.kind == MediaKind.LIVE && e.nativeKeyEvent.repeatCount == 0) {
                            manualPlayerChoice = true
                            useVlc = true
                        } else if (item.kind != MediaKind.LIVE) controls = true
                        true
                    }''', '''                    KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_INFO -> {
                        if (e.nativeKeyEvent.repeatCount == 0) showPlaybackInfo = true
                        true
                    }''')
replace_once(player, '''    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()

    fun switchLiveBy''', '''    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()
    var showPlaybackInfo by remember(item.resumeKey) { mutableStateOf(false) }
    if (showPlaybackInfo) V122PlaybackInfoDialog(isTv, { showPlaybackInfo = false },
        compatibility = true, onSwitchPlayer = onSwitchPlayer)

    fun switchLiveBy''')
replace_once(player, '''    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()

    LaunchedEffect''', '''    val nowProgramme = u.epg[item.id]?.firstOrNull()?.title.orEmpty()
    var showPlaybackInfo by remember(item.resumeKey) { mutableStateOf(false) }
    if (showPlaybackInfo) V122PlaybackInfoDialog(isTv, { showPlaybackInfo = false },
        onSwitchPlayer = { manualPlayerChoice = true; useVlc = true })

    LaunchedEffect''')
for anchor in ('                    TextButton(onClick = onSwitchPlayer,',
               '                    TextButton(onClick = {\n                        manualPlayerChoice = true\n                        useVlc = true\n                    },'):
    replace_once(player, anchor,
        '                    TextButton(onClick = { showPlaybackInfo = true }, modifier = Modifier.v114FocusRing()) {\n'
        '                        Text("Info · Menü", color = Color.White)\n'
        '                    }\n' + anchor)

dialog = java / "ui/V115PlayerDialogs.kt"
replace_once(dialog, '    onTrack: (V115TrackChoice) -> Unit, onOff: () -> Unit) {',
    '    onTrack: (V115TrackChoice) -> Unit, onOff: () -> Unit, onInfo: (() -> Unit)? = null) {')
replace_once(dialog, '                if (isTv) V121FrameRateControl()',
    '                if (onInfo != null) TextButton(onClick = onInfo, modifier = Modifier.fillMaxWidth().v114FocusRing().testTag("vod-playback-info")) {\n'
    '                    Text("Wiedergabe-Info", color = Color.White, fontSize = 17.sp)\n'
    '                }\n'
    '                if (isTv) V121FrameRateControl()')
chrome = java / "ui/V115PlayerChrome.kt"
replace_once(chrome, '''        if (dialog == "audio") V115TrackDialog(state, isTv, ::closeDialog,
            onTrack = { onTrack(it); closeDialog() }, onOff = { onSubtitlesOff(); closeDialog() })''',
    '''        if (dialog == "info") V122PlaybackInfoDialog(isTv, ::closeDialog)
        if (dialog == "audio") V115TrackDialog(state, isTv, ::closeDialog,
            onTrack = { onTrack(it); closeDialog() }, onOff = { onSubtitlesOff(); closeDialog() },
            onInfo = { dialog = "info" })''')

tests = root / "app/src/test/java/de/epimediahub/app/ui"
for source in here.glob("*Test.kt"):
    shutil.copyfile(source, tests / source.name)
assert 'versionCode = 1022' in gradle.read_text()
assert 'V121VodSurface(player, isTv, Modifier.fillMaxSize())' in player.read_text()
assert 'v120RememberLicenseState' in (java / "EpiMediaHubApp.kt").read_text()
print("Android 1.0.22: stable live-TV surface, timestamp frame-rate fallback and playback diagnostics installed")
