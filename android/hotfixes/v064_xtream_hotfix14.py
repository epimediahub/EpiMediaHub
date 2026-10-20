#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace missing: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace missing: {signature}")


# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
build = root / "app/build.gradle.kts"
s = build.read_text()
require_once(s, 'versionCode = 616', 'v0.6.4.13 versionCode')
require_once(s, 'versionName = "0.6.4.13"', 'v0.6.4.13 versionName')
s = s.replace('versionCode = 616', 'versionCode = 617', 1)
s = s.replace('versionName = "0.6.4.13"', 'versionName = "0.6.4.14"', 1)
build.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.6.4.13", "0.6.4.14"))


# ---------------------------------------------------------------------------
# Xtream memory fix.
#
# The provider M3U can be >160 MB. The legacy exact-M3U fallback used readText()
# and therefore tried to allocate the complete response as one String. On TV/
# Fire-TV heaps (~192 MB) that produces the observed ~170 MB allocation failure.
# Live now has a proven canonical MPEG-TS URL and VOD/series have normal Xtream
# API URLs, so the giant fallback playlist must never be downloaded at all.
# ---------------------------------------------------------------------------
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()

# Keep the helper API for compatibility with previous hotfixes, but make it a
# zero-allocation cache lookup. This also protects any forgotten call site.
a, b = function_span(s, "    private fun exactM3uStreamUrls()")
safe_exact = '''    private fun exactM3uStreamUrls(): Map<String, String> {
        val key = m3uStreamKey()
        return m3uStreamUrlCache[key] ?: emptyMap<String, String>().also {
            m3uStreamUrlCache[key] = it
        }
    }'''
s = s[:a] + safe_exact + s[b:]

# Background prefetch is no longer needed and was the source of the OOM while
# opening Movies. Leave a no-op method so existing callers remain source-stable.
a, b = function_span(s, "    private fun prefetchExactM3uAsync()")
safe_prefetch = '''    private fun prefetchExactM3uAsync() {
        // Intentionally disabled: provider get.php M3U may exceed the Android TV heap.
        // Xtream API/direct_source URLs are used for VOD/series and canonicalMpegTsLiveUrl for Live.
    }'''
s = s[:a] + safe_prefetch + s[b:]

# Older episode code still forced a synchronous full-M3U scan. Make that map an
# empty fallback so episodes use direct_source/standard /series/ URLs immediately.
s = s.replace(
    '        val exactM3u = exactM3uStreamUrls()\n',
    '        val exactM3u = emptyMap<String, String>()\n',
)
xtream.write_text(s)


# ---------------------------------------------------------------------------
# Dashboard sync visibility fix.
#
# WorkManager correctly updated SharedPreferences, but the already-created
# MainViewModel kept its old in-memory playlist list. Run one foreground sync
# on Activity start; when a new config is actually applied, recreate once so
# the ViewModel reloads the managed playlist immediately. The saved config
# version prevents a recreate loop.
# ---------------------------------------------------------------------------
main = java / "MainActivity.kt"
ms = main.read_text()

imports = {
    'import androidx.lifecycle.lifecycleScope\n': 'import androidx.activity.result.contract.ActivityResultContracts\n',
    'import de.epimediahub.app.data.SetupCodeProvisioning\n': 'import de.epimediahub.app.data.DashboardSyncWorker\n',
    'import de.epimediahub.app.data.DeviceSyncResult\n': 'import de.epimediahub.app.data.SetupCodeProvisioning\n',
    'import kotlinx.coroutines.Dispatchers\n': 'import de.epimediahub.app.data.DeviceSyncResult\n',
    'import kotlinx.coroutines.launch\n': 'import kotlinx.coroutines.Dispatchers\n',
    'import kotlinx.coroutines.withContext\n': 'import kotlinx.coroutines.launch\n',
}
for wanted, after in imports.items():
    if wanted not in ms:
        if after not in ms:
            raise SystemExit(f"MainActivity import anchor missing for {wanted.strip()}: {after.strip()}")
        ms = ms.replace(after, after + wanted, 1)

schedule = '        DashboardSyncWorker.schedule(applicationContext)\n'
if schedule not in ms:
    raise SystemExit("DashboardSyncWorker schedule anchor missing")
foreground_sync = '''        DashboardSyncWorker.schedule(applicationContext)
        lifecycleScope.launch {
            val result = withContext(Dispatchers.IO) {
                SetupCodeProvisioning.sync(applicationContext)
            }
            if (result is DeviceSyncResult.Success && result.changed && !isFinishing && !isDestroyed) {
                recreate()
            }
        }
'''
ms = ms.replace(schedule, foreground_sync, 1)
main.write_text(ms)


# Sanity checks: never re-introduce a whole-provider M3U String allocation.
xf = xtream.read_text()
checks = [
    (build, 'versionName = "0.6.4.14"'),
    (build, 'versionCode = 617'),
    (xtream, 'provider get.php M3U may exceed the Android TV heap'),
    (xtream, 'val exactM3u = emptyMap<String, String>()'),
    (main, 'SetupCodeProvisioning.sync(applicationContext)'),
    (main, 'result is DeviceSyncResult.Success && result.changed'),
    (main, 'recreate()'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.6.4.14 marker {marker} in {path}")

if 'text(providerM3uUrl()).lineSequence()' in xf:
    raise SystemExit("unsafe full provider M3U read still present")

print("Android v0.6.4.14 OOM-free Xtream catalog + visible Dashboard sync applied")
