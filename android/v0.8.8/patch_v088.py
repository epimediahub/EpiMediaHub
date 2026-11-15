#!/usr/bin/env python3
"""Hardware video + software audio, normal clock recovery and stable VLC ownership."""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def change(path, old, new):
    text = path.read_text()
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one anchor in {path}: {old[:100]}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
change(gradle, 'versionCode = 807', 'versionCode = 808')
change(gradle, 'versionName = "0.8.7"', 'versionName = "0.8.8"')
for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.8.7", "0.8.8"))

player = java / "ui/PlayerScreen.kt"
s = player.read_text()
# Remove the old native owner. Its effect could release remembered objects while
# the same channel received a new URL, then attempt to play on the released owner.
start = s.index('    val videoLayout = remember(item.resumeKey)')
end = s.index('    var controls by remember(item.resumeKey)', start)
s = s[:start] + s[end:]
start = s.index('    DisposableEffect(item.resumeKey, request.url)')
end = s.index('\n    Box(', start)
s = s[:start] + s[end:]
for line in (
    'import android.net.Uri\n',
    'import org.videolan.libvlc.LibVLC\n',
    'import org.videolan.libvlc.Media\n',
    'import org.videolan.libvlc.MediaPlayer as VlcMediaPlayer\n',
    'import org.videolan.libvlc.util.VLCVideoLayout\n',
):
    s = s.replace(line, '')
player.write_text(s)
change(player, '''        AndroidView(
            factory = { videoLayout },
            modifier = Modifier.fillMaxSize()
        )''', '''        V088VlcVideo(
            url = request.url,
            userAgent = request.userAgent,
            referer = request.referer,
            modifier = Modifier.fillMaxSize(),
            onError = { playbackError = it }
        )''')

# Retain the exact working URL when Media3 has tried provider alternatives.
change(player, '''    isTv: Boolean,
    onSwitchPlayer: () -> Unit''', '''    isTv: Boolean,
    startUrl: String,
    onSwitchPlayer: () -> Unit''')
change(player, '''    val request = remember(item.resumeKey, playbackUrls) {
        parseIptvHttpRequest(playbackUrls.firstOrNull().orEmpty().ifBlank { item.streamUrl })
    }''', '''    val request = remember(item.resumeKey, playbackUrls, startUrl) {
        parseIptvHttpRequest(startUrl.ifBlank { playbackUrls.firstOrNull().orEmpty().ifBlank { item.streamUrl } })
    }''')
change(player, '''    var manualPlayerChoice by remember(item.resumeKey) { mutableStateOf(false) }
    if (useVlc) {
        V071VlcLivePlayer(vm, item, episodeList, accent, isTv) {''', '''    var manualPlayerChoice by remember(item.resumeKey, item.streamUrl) { mutableStateOf(false) }
    var compatibilityUrl by remember(item.resumeKey, item.streamUrl) { mutableStateOf("") }
    if (useVlc) {
        V071VlcLivePlayer(vm, item, episodeList, accent, isTv, compatibilityUrl) {''')
change(player, 'var useVlc by remember(item.resumeKey) {', 'var useVlc by remember(item.resumeKey, item.streamUrl) {')
change(player, '''            val request = parseIptvHttpRequest(playbackUrls[index])
            httpFactory.setUserAgent''', '''            compatibilityUrl = playbackUrls[index]
            val request = parseIptvHttpRequest(compatibilityUrl)
            httpFactory.setUserAgent''')

# A held MENU key generates repeated ACTION_DOWN events. One physical press
# must not keep restarting both native players while the new stream buffers.
change(player, '''                    KeyEvent.KEYCODE_MENU -> {
                        onSwitchPlayer()
                        true
                    }''', '''                    KeyEvent.KEYCODE_MENU -> {
                        if (it.nativeKeyEvent.repeatCount == 0) onSwitchPlayer()
                        true
                    }''')
change(player, '''                    KeyEvent.KEYCODE_MENU -> {
                        manualPlayerChoice = true
                        useVlc = true
                        true
                    }''', '''                    KeyEvent.KEYCODE_MENU -> {
                        if (item.kind == MediaKind.LIVE && e.nativeKeyEvent.repeatCount == 0) {
                            manualPlayerChoice = true
                            useVlc = true
                        } else if (item.kind != MediaKind.LIVE) controls = true
                        true
                    }''')
change(player, '''    fun leave() {
        save()
        player.release()
        vm.back()
    }''', '''    fun leave() {
        save()
        vm.back() // DisposableEffect is the sole owner of player.release().
    }''')
shutil.copyfile(Path(__file__).with_name("V088VlcVideo.kt"), java / "ui/V088VlcVideo.kt")
print("Android 0.8.8 hardware video, software audio and stable player switching applied")
