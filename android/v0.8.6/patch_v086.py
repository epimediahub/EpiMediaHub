#!/usr/bin/env python3
"""Restore sound on live channels whose names do not advertise their codec."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
base = root / "app/src/main/java/de/epimediahub/app"

def change(path, old, new):
    value = path.read_text()
    if value.count(old) != 1:
        raise SystemExit(f"Expected exactly one anchor in {path}: {old[:90]}")
    path.write_text(value.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
change(gradle, 'versionCode = 805', 'versionCode = 806')
change(gradle, 'versionName = "0.8.5"', 'versionName = "0.8.6"')
for name in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt"):
    path = base / name
    if path.exists():
        path.write_text(path.read_text().replace("0.8.5", "0.8.6"))
weather = base / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.8.5", "EpiMediaHub-Android/0.8.6"))

path = base / "ui/PlayerScreen.kt"
change(path, 'import androidx.media3.common.TrackSelectionParameters\n',
       'import androidx.media3.common.TrackSelectionParameters\nimport androidx.media3.common.Tracks\n')
change(path, '''    isTv: Boolean
) {
    val context = LocalContext.current''', '''    isTv: Boolean,
    onSwitchPlayer: () -> Unit
) {
    val context = LocalContext.current''')
change(path, '''                    Surface(color = accent.copy(alpha = .18f), shape = MaterialTheme.shapes.small) {
                        Text(
                            if (isTv) "LIVE · KOMPATIBILITÄT" else "LIVE",''', '''                    TextButton(onClick = onSwitchPlayer) {
                        Text("Standardplayer", color = Color.White)
                    }
                    Surface(color = accent.copy(alpha = .18f), shape = MaterialTheme.shapes.small) {
                        Text(
                            if (isTv) "LIVE · KOMPATIBILITÄT" else "LIVE",''')
change(path, '''    if (V072UseVlcLiveFallback(item)) {
        V071VlcLivePlayer(vm, item, episodeList, accent, isTv)
        return
    }
    val context = LocalContext.current''', '''    var useVlc by remember(item.resumeKey) { mutableStateOf(V072UseVlcLiveFallback(item)) }
    var manualPlayerChoice by remember(item.resumeKey) { mutableStateOf(false) }
    if (useVlc) {
        V071VlcLivePlayer(vm, item, episodeList, accent, isTv) {
            manualPlayerChoice = true
            useVlc = false
        }
        return
    }
    val context = LocalContext.current''')
change(path, '''        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged''', '''        val listener = object : Player.Listener {
            override fun onTracksChanged(tracks: Tracks) {
                // A video decoder may render frames while Android offers no
                // decoder for the accompanying audio track. Inspect the actual
                // stream metadata instead of guessing from the channel name.
                if (item.kind == MediaKind.LIVE && !manualPlayerChoice &&
                    tracks.containsType(C.TRACK_TYPE_AUDIO) &&
                    !tracks.isTypeSupported(C.TRACK_TYPE_AUDIO)
                ) {
                    useVlc = true
                }
            }
            override fun onPlaybackStateChanged''')
change(path, '''            override fun onPlayerError(error: PlaybackException) {
                cancelWatchdog()
                var cause:''', '''            override fun onPlayerError(error: PlaybackException) {
                cancelWatchdog()
                if (item.kind == MediaKind.LIVE && !manualPlayerChoice &&
                    (error.errorCode == PlaybackException.ERROR_CODE_DECODING_FAILED ||
                        error.errorCode == PlaybackException.ERROR_CODE_DECODER_INIT_FAILED ||
                        error.errorCode == PlaybackException.ERROR_CODE_DECODING_FORMAT_UNSUPPORTED)
                ) {
                    useVlc = true
                    return
                }
                var cause:''')
change(path, '''                    Surface(color = accent.copy(alpha = .18f), shape = MaterialTheme.shapes.small) {
                        Text(
                            "LIVE",''', '''                    TextButton(onClick = {
                        manualPlayerChoice = true
                        useVlc = true
                    }) {
                        Text("Audio-Kompatibilität", color = Color.White)
                    }
                    Surface(color = accent.copy(alpha = .18f), shape = MaterialTheme.shapes.small) {
                        Text(
                            "LIVE",''')

# Fire TV remotes can reach the compatibility decoder via their menu key.
# This also works when the on-screen controls have already faded away.
change(path, '''                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                        controls = !controls
                        true
                    }
                    else -> false''', '''                    KeyEvent.KEYCODE_MENU -> {
                        onSwitchPlayer()
                        true
                    }
                    KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                        controls = !controls
                        true
                    }
                    else -> false''')
change(path, '''                    KeyEvent.KEYCODE_MENU -> { controls = true; true }
                    KeyEvent.KEYCODE_DPAD_CENTER,''', '''                    KeyEvent.KEYCODE_MENU -> {
                        manualPlayerChoice = true
                        useVlc = true
                        true
                    }
                    KeyEvent.KEYCODE_DPAD_CENTER,''')
print("Android 0.8.6 audio track fallback and manual player switch applied")
