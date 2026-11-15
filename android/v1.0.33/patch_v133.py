#!/usr/bin/env python3
"""Clean installed updater downloads and move home actions into the central clock row."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
here = Path(__file__).resolve().parent
java = root / 'app/src/main/java/de/epimediahub/app'

def replace(path, old, new, count=1):
    text = path.read_text()
    assert text.count(old) == count, f'{path}: expected {count} anchors for {old[:90]}'
    path.write_text(text.replace(old, new))

replace(root/'app/build.gradle.kts', 'versionCode = 1032', 'versionCode = 1033')
replace(root/'app/build.gradle.kts', 'versionName = "1.0.32"', 'versionName = "1.0.33"')
for path in java.rglob('*.kt'):
    text = path.read_text()
    if '1.0.32' in text:
        path.write_text(text.replace('1.0.32', '1.0.33'))
for path in here.glob('V133*.kt'):
    category = 'data' if 'Storage' in path.name else 'ui'
    parent = root/'app/src/test/java/de/epimediahub/app' if path.name.endswith('Test.kt') else java
    dest = parent/category
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, dest/path.name)

activity = java/'MainActivity.kt'
replace(activity, 'import de.epimediahub.app.data.DashboardSyncWorker',
    'import de.epimediahub.app.data.DashboardSyncWorker\nimport de.epimediahub.app.data.V133UpdateStorage')
replace(activity, '        super.onCreate(savedInstanceState)', '''        super.onCreate(savedInstanceState)
        lifecycleScope.launch(Dispatchers.IO) {
            V133UpdateStorage.cleanupInstalled(applicationContext)
        }''')
updater = java/'data/UpdateManager.kt'
replace(updater, '        val partial = File(dir, "EpiMediaHub-$safeVersion.apk.part")',
    '''        val partial = File(dir, "EpiMediaHub-$safeVersion.apk.part")
        V133UpdateStorage.cleanupDirectory(dir, BuildConfig.VERSION_NAME, setOf(target.name, partial.name))''')

home = java/'ui/V083Home.kt'
replace(home, '''            Spacer(Modifier.height(if (isTv) 8.dp else 4.dp))
            RadioHomeActions(showPlaylistSwitch, isTv, accent, onPlaylistSwitch, onRadio)
''', '')
replace(home, '        if (!compact || isTv) {\n            Column(', '        run {\n            Column(')
replace(home, '.padding(top = if (isTv) 10.dp else 86.dp)',
    '.padding(top = if (isTv) 10.dp else if (compact) 2.dp else 86.dp)')
replace(home, '                weather?.let {', '                weather?.takeIf { !compact || isTv }?.let {')
replace(home, '''                Text(
                    time,
                    color = Color.White,
                    fontSize = if (isTv) 32.sp else 19.sp,
                    fontWeight = FontWeight.Black
                )
                Text(
                    date,
                    color = Color.White.copy(.60f),
                    fontSize = if (isTv) 12.sp else 10.sp,
                    fontWeight = FontWeight.Medium
                )''', '''                Row(
                    modifier = Modifier.testTag("home-center-toolbar"),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(if (isTv) 12.dp else 8.dp)
                ) {
                    Text(
                        time, color = Color.White,
                        fontSize = if (isTv) 32.sp else if (compact) 16.sp else 19.sp,
                        fontWeight = FontWeight.Black
                    )
                    RadioHomeActions(showPlaylistSwitch, isTv, accent, onPlaylistSwitch, onRadio)
                }
                if (!compact || isTv) {
                    Text(
                        date, color = Color.White.copy(.60f),
                        fontSize = if (isTv) 12.sp else 10.sp,
                        fontWeight = FontWeight.Medium
                    )
                }''')
replace(home, 'Modifier.align(Alignment.TopCenter).padding(top = 18.dp)',
    'Modifier.align(Alignment.TopCenter).padding(top = 118.dp)')
print('Installed Android 1.0.33: updater cleanup and central home shortcuts')
