#!/usr/bin/env python3
"""Private, provider-file-bound skip corrections and explicit resume after skipping."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent
gradle = root / 'app/build.gradle.kts'
s = gradle.read_text()
assert s.count('versionCode = 1015') == 1 and s.count('versionName = "1.0.15"') == 1
gradle.write_text(s.replace('versionCode = 1015', 'versionCode = 1016').replace('versionName = "1.0.15"', 'versionName = "1.0.16"'))
for p in java.rglob('*.kt'):
    s = p.read_text()
    if '1.0.15' in s:
        p.write_text(s.replace('1.0.15', '1.0.16'))

player = java / 'ui/PlayerScreen.kt'
s = player.read_text()
assert s.count('V115VodPlayer(') == 1
player.write_text(s.replace('V115VodPlayer(', 'V116VodPlayer('))

chrome = java / 'ui/V115PlayerChrome.kt'
s = chrome.read_text()
anchor = '    video: @Composable (Modifier) -> Unit\n'
assert s.count(anchor) == 1
s = s.replace(anchor, '    onSkipSegment: ((V115Segment) -> Unit)? = null,\n    skipTools: (@Composable (() -> Unit) -> Unit)? = null,\n' + anchor)
s = s.replace('    val nextFocus = remember(item.resumeKey) { FocusRequester() }', '    val nextFocus = remember(item.resumeKey) { FocusRequester() }\n    val skipFocus = remember(item.resumeKey) { FocusRequester() }')
s = s.replace('"audio" -> audioFocus; "episodes" -> episodesFocus; "next" -> nextFocus;', '"audio" -> audioFocus; "episodes" -> episodesFocus; "next" -> nextFocus; "skip" -> skipFocus;')
anchor = 'Button(onClick = { onSeekTo(segment.endMs); touch() },'
assert s.count(anchor) == 1
s = s.replace(anchor, 'Button(onClick = { if (onSkipSegment != null) onSkipSegment(segment) else onSeekTo(segment.endMs); touch() },')
anchor = '                    if (ordered.isNotEmpty()) TextButton('
assert s.count(anchor) == 1
s = s.replace(anchor, '''                    if (skipTools != null) TextButton(onClick = { restore = "skip"; dialog = "skip"; touch() },
                        modifier = Modifier.heightIn(min = 54.dp).focusRequester(skipFocus).v114FocusRing().testTag("vod-skip-tools")) {
                        Icon(Icons.Default.Edit, null, tint = Color.White); Spacer(Modifier.width(8.dp)); Text("Intro & Abspann", color = Color.White, fontSize = if (isTv) 18.sp else 15.sp)
                    }
''' + anchor)
anchor = '        video(Modifier.fillMaxSize())'
assert s.count(anchor) == 1
s = s.replace(anchor, anchor + '\n        if (dialog == "skip") skipTools?.invoke(::closeDialog)')
chrome.write_text(s)

repo = java / 'data/V115SkipRepository.kt'
s = repo.read_text()
start = s.index('    fun cleanTitle(value: String): String =')
end = s.index('    fun normalized(value: String): String =', start)
s = s[:start] + '    fun cleanTitle(value: String): String = V116Names.clean(value)\n' + s[end:]
repo.write_text(s)

worker = java / 'data/DashboardSyncWorker.kt'
s = worker.read_text()
anchor = 'is DeviceSyncResult.Success -> Result.success()'
assert s.count(anchor) == 1
worker.write_text(s.replace(anchor, 'is DeviceSyncResult.Success -> { V116SkipRepository(applicationContext).flushPending(); Result.success() }'))
provisioning = java / 'data/SetupCodeProvisioning.kt'
s = provisioning.read_text()
anchor = '    fun clearDeviceConfiguration(context: Context) {'
assert s.count(anchor) == 1
provisioning.write_text(s.replace(anchor, anchor + '\n        context.getSharedPreferences("v116_own_skip", Context.MODE_PRIVATE).edit().clear().apply()'))

for package, names in {'ui': ('V116VodPlayer.kt', 'V116SkipEditor.kt'), 'data': ('V116SkipRepository.kt', 'V116Chapters.kt')}.items():
    for name in names:
        shutil.copyfile(here / name, java / package / name)
for package, name in (('data', 'V116SkipPolicyTest.kt'), ('ui', 'V116SkipEditorTest.kt')):
    if (here / name).exists():
        dest = root / 'app/src/test/java/de/epimediahub/app' / package / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(here / name, dest)
print('Android 1.0.16: own skip markers, central review, chapter metadata and skip/resume installed')
