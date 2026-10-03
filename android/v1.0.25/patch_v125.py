#!/usr/bin/env python3
"""Clearable radio search and lightweight support for the central skip worker."""
import os
from pathlib import Path
import shutil

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent

def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f'{path}: expected one anchor: {old[:90]}'
    path.write_text(text.replace(old, new, 1))

gradle = root / 'app/build.gradle.kts'
replace_once(gradle, 'versionCode = 1024', 'versionCode = 1025')
replace_once(gradle, 'versionName = "1.0.24"', 'versionName = "1.0.25"')
for path in java.rglob('*.kt'):
    text = path.read_text()
    if '1.0.24' in text:
        path.write_text(text.replace('1.0.24', '1.0.25'))

keyboard = java / 'ui/V110SmartTubeShell.kt'
replace_once(keyboard, '    onValueChange: (String) -> Unit = {},\n    onSubmit: (String) -> Unit',
    '    onValueChange: (String) -> Unit = {},\n    allowEmpty: Boolean = false,\n    onSubmit: (String) -> Unit')
replace_once(keyboard, '''                enabled = value.isNotBlank(),
                onClick = { onSubmit(value) }
            ,
            modifier = Modifier.v114FocusRing()
        ) { Text("Suchen") }''',
    '''                enabled = allowEmpty || value.isNotBlank(),
                modifier = Modifier.v114FocusRing().testTag("tv-keyboard-submit"),
                onClick = { onSubmit(value.trim()) }
            ) { Text(if (allowEmpty && value.isBlank()) "Übernehmen" else "Suchen") }''')
text = keyboard.read_text()
if 'import androidx.compose.ui.platform.testTag' not in text:
    text = text.replace('import androidx.compose.ui.Modifier\n',
        'import androidx.compose.ui.Modifier\nimport androidx.compose.ui.platform.testTag\n', 1)
    keyboard.write_text(text)
replace_once(java / 'ui/RadioScreen.kt',
    'if (isTv) V110TvKeyboardDialog(title, initial, accent, dismiss, onSubmit = submit)',
    'if (isTv) V110TvKeyboardDialog(title, initial, accent, dismiss, allowEmpty = true, onSubmit = submit)')

repo = java / 'data/V116SkipRepository.kt'
replace_once(repo, 'internal class V116SkipRepository(private val context: Context) {',
    '''internal class V116SkipRepository(private val context: Context) {
    companion object { private val presenceLock = kotlinx.coroutines.sync.Mutex() }''')
if 'import kotlinx.coroutines.sync.withLock' not in repo.read_text():
    replace_once(repo, 'import kotlinx.coroutines.*', 'import kotlinx.coroutines.*\nimport kotlinx.coroutines.sync.withLock')
replace_once(repo, '''    suspend fun presence(item: MediaEntry) {
        val id = playlistId(item)
        if (id > 0) request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/presence", JSONObject().put("playlist_id", id), true)
    }''', '''    suspend fun presence(item: MediaEntry, presenceId: String = "", active: Boolean = true) {
        val id = playlistId(item)
        if (id > 0) presenceLock.withLock {
            request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/presence",
                JSONObject().put("playlist_id", id).put("presence_id", presenceId).put("active", active), true)
        }
    }

    suspend fun loadCentral(item: MediaEntry, duration: Long): V116SkipResult? {
        val remote = request("${SetupCodeProvisioning.provisioningBaseUrl(context)}/v1/device/skip/lookup",
            payload(item, duration), true) ?: return null
        if (remote.optString("asset_key") != V116SkipKeys.asset(item) ||
            remote.optString("source_key") != V116SkipKeys.series(item) ||
            abs(remote.optLong("duration_ms") - duration) > 2_000L) return null
        val (central, disabled) = approved(remote, item, duration)
        return V116SkipResult(central, if (central.isNotEmpty()) "Passende Zeitmarken verfügbar" else "", disabled)
    }''')
player = java / 'ui/PlayerScreen.kt'
replace_once(player, '        while (true) { skipRepository.presence(item); delay(25_000L) }',
    '''        val presenceId = java.util.UUID.randomUUID().toString()
        de.epimediahub.app.data.v125KeepSkipPresence { active ->
            skipRepository.presence(item, presenceId, active)
        }''')
vod = java / 'ui/V116VodPlayer.kt'
replace_once(vod, '''            repeat(2) { attempt ->
                val loaded = repository.load(item, duration)
                automatic = loaded.segments; disabled = loaded.disabled
                if (synchronized.isBlank()) status = loaded.status
                if (loaded.segments.isNotEmpty()) return@LaunchedEffect
                if (attempt == 0) delay(15_000L)
            }''', '''            val loaded = repository.load(item, duration)
            automatic = loaded.segments; disabled = loaded.disabled
            if (synchronized.isBlank()) status = loaded.status
            // Poll only the central API. This opens no second provider stream
            // and avoids repeatedly querying all public metadata services.
            while (true) {
                delay(30_000L)
                val central = repository.loadCentral(item, duration) ?: continue
                automatic = v125MergeCentral(automatic, central); disabled = central.disabled
                if (central.status.isNotBlank()) status = central.status
            }''')
shutil.copyfile(here / 'V125SkipPresence.kt', java / 'data/V125SkipPresence.kt')
for package, name in [('data', 'V125SkipPresenceTest.kt'), ('ui', 'V125RadioSearchTest.kt')]:
    target = root / 'app/src/test/java/de/epimediahub/app' / package / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(here / name, target)
print('Android 1.0.25: empty radio search, immediate playback release and central marker refresh installed')
