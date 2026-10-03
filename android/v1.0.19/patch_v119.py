#!/usr/bin/env python3
"""International radio, header shortcut, persistent favorites and background audio."""
import os
from pathlib import Path
import shutil
import xml.etree.ElementTree as ET

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent

def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f'{path}: expected one anchor {old!r}, got {text.count(old)}'
    path.write_text(text.replace(old, new, 1))

gradle = root / 'app/build.gradle.kts'
replace_once(gradle, 'versionCode = 1018', 'versionCode = 1019')
replace_once(gradle, 'versionName = "1.0.18"', 'versionName = "1.0.19"')
replace_once(gradle, '    implementation("androidx.media3:media3-ui:1.9.4")',
    '    implementation("androidx.media3:media3-ui:1.9.4")\n    implementation("androidx.media3:media3-session:1.9.4")\n    implementation("com.squareup.okhttp3:okhttp:4.12.0")')
for path in java.rglob('*.kt'):
    text = path.read_text()
    if '1.0.18' in text:
        path.write_text(text.replace('1.0.18', '1.0.19'))
for filename, package in [('RadioModels.kt', 'data'), ('RadioRepository.kt', 'data'), ('RadioPlayback.kt', 'radio'),
                          ('RadioViewModel.kt', 'ui'), ('RadioScreen.kt', 'ui')]:
    (java / package).mkdir(exist_ok=True)
    shutil.copyfile(here / filename, java / package / filename)

home = java / 'ui/V083Home.kt'
replace_once(home, 'import androidx.compose.runtime.*', 'import androidx.compose.runtime.*\nimport androidx.compose.runtime.saveable.rememberSaveable')
replace_once(home, '    var smartTubeOpen by remember { mutableStateOf(false) }',
    '''    var smartTubeOpen by remember { mutableStateOf(false) }
    var radioOpen by rememberSaveable { mutableStateOf(false) }
    if (radioOpen) {
        RadioScreen(isTv, accent, onBack = { radioOpen = false })
        return
    }''')
replace_once(home, '                onPlaylistSwitch = { vm.navigate(Screen.Playlists) },',
    '                onPlaylistSwitch = { vm.navigate(Screen.Playlists) },\n                onRadio = { radioOpen = true },')
replace_once(home, '    onPlaylistSwitch: () -> Unit,', '    onPlaylistSwitch: () -> Unit,\n    onRadio: () -> Unit,')
text = home.read_text()
start = text.index('            if (showPlaylistSwitch) {')
end = text.index('\n        }\n\n        if (!compact || isTv)', start)
text = text[:start] + '''            Spacer(Modifier.height(if (isTv) 8.dp else 4.dp))
            RadioHomeActions(showPlaylistSwitch, isTv, accent, onPlaylistSwitch, onRadio)
''' + text[end:]
text = text.replace('compact -> 78.dp', 'compact -> 94.dp')
home.write_text(text)

# Every video path funnels through one of these players. Pause radio before its
# player is created; returning to menus does not unexpectedly resume radio.
replace_once(java / 'ui/PlayerScreen.kt', '    val v116Context = LocalContext.current.applicationContext',
    '    LaunchedEffect(item.resumeKey) { de.epimediahub.app.radio.RadioPlaybackService.pauseForVideo() }\n    val v116Context = LocalContext.current.applicationContext')
replace_once(java / 'ui/V112SmartTubePlayer.kt', '    val reportProgress by rememberUpdatedState(onProgress)',
    '    LaunchedEffect(video.videoId) { de.epimediahub.app.radio.RadioPlaybackService.pauseForVideo() }\n    val reportProgress by rememberUpdatedState(onProgress)')

manifest = root / 'app/src/main/AndroidManifest.xml'
text = manifest.read_text()
anchor = '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE" />'
assert text.count(anchor) == 1
for name in ('FOREGROUND_SERVICE_MEDIA_PLAYBACK', 'WAKE_LOCK'):
    permission = f'    <uses-permission android:name="android.permission.{name}" />'
    if permission not in text:
        text = text.replace(anchor, anchor + '\n' + permission, 1)
service = '''        <service
            android:name=".radio.RadioPlaybackService"
            android:foregroundServiceType="mediaPlayback"
            android:exported="true">
            <intent-filter>
                <action android:name="androidx.media3.session.MediaSessionService" />
            </intent-filter>
        </service>
'''
assert text.count('    </application>') == 1
text = text.replace('    </application>', service + '    </application>', 1)
ET.fromstring(text)
manifest.write_text(text)

for filename in ('RadioModelsTest.kt', 'RadioRepositoryTest.kt', 'RadioScreenTest.kt', 'RadioPlaybackTest.kt'):
    package = 'ui' if filename == 'RadioScreenTest.kt' else 'radio' if filename == 'RadioPlaybackTest.kt' else 'data'
    target = root / 'app/src/test/java/de/epimediahub/app' / package
    target.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(here / filename, target / filename)
assert home.read_text().count('V083Tile(') == 7  # data class plus existing six tiles
print('Android 1.0.19: radio header button, international filters, favorites and background player installed')
