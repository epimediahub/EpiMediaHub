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
require_once(s, 'versionCode = 701', 'v0.7.1 versionCode')
require_once(s, 'versionName = "0.7.1"', 'v0.7.1 versionName')
s = s.replace('versionCode = 701', 'versionCode = 702', 1)
s = s.replace('versionName = "0.7.1"', 'versionName = "0.7.2"', 1)
build.write_text(s)

home = java / "ui/V070Home.kt"
hs = home.read_text()
if "0.7.1" not in hs:
    raise SystemExit("visible v0.7.1 marker missing")
home.write_text(hs.replace("0.7.1", "0.7.2"))

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.1", "EpiMediaHub-Android/0.7.2"))


# ---------------------------------------------------------------------------
# RAW/MP2 Live audio.
#
# v0.7.1 used double backslashes inside a Kotlin raw string. The resulting
# regular expression searched for literal "\\b" text, so even "Rai 1 RAW"
# never reached LibVLC and stayed on ExoPlayer, which commonly cannot decode
# MPEG Audio Layer II on Android/Fire TV. Also accept provider suffixes after
# RAW (for example "RAW 4K") while avoiding unrelated words such as STRAW.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
old_detector = r'''private fun V071UseVlcLiveFallback(item: MediaEntry): Boolean {
    if (item.kind != MediaKind.LIVE) return false
    val label = item.name.trim()
    return Regex("""(?i)(?:\\bRAW\\b|\\bHEVC\\b|\\bH\\.?265\\b)\\s*$""").containsMatchIn(label)
}'''
new_detector = r'''private fun V072UseVlcLiveFallback(item: MediaEntry): Boolean {
    if (item.kind != MediaKind.LIVE) return false
    val label = item.name.trim()
    return Regex("""(?i)(?:^|[^A-Z0-9])(?:RAW|HEVC|H\.?265)(?:$|[^A-Z0-9])""").containsMatchIn(label)
}'''
require_once(s, old_detector, 'v0.7.1 RAW detector')
s = s.replace(old_detector, new_detector, 1)
require_once(s, 'if (V071UseVlcLiveFallback(item)) {', 'v0.7.1 player routing call')
s = s.replace('if (V071UseVlcLiveFallback(item)) {', 'if (V072UseVlcLiveFallback(item)) {', 1)
player.write_text(s)


# ---------------------------------------------------------------------------
# Refresh playlists whenever the app enters the foreground.
#
# Dashboard sync already runs on startup, but a race could let MainViewModel
# retain the pre-sync list. Provider results also survived a background/resume
# in the ViewModel caches. Always reload saved dashboard profiles after a
# successful sync, and invalidate provider/M3U caches on every ON_START so the
# next category open fetches fresh channel, movie and series data.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
a, b = function_span(s, "    fun refreshProfiles()")
refresh_method = r'''

    fun refreshPlaylistsAtAppStart() {
        m3uCache.clear()
        xtreamLibraryCache.clear()
        refreshProfiles()
    }'''
s = s[:b] + refresh_method + s[b:]
vm.write_text(s)

app = java / "EpiMediaHubApp.kt"
s = app.read_text()
if 'import androidx.compose.runtime.DisposableEffect\n' not in s:
    require_once(s, 'import androidx.compose.runtime.Composable\n', 'Compose import anchor')
    s = s.replace(
        'import androidx.compose.runtime.Composable\n',
        'import androidx.compose.runtime.Composable\nimport androidx.compose.runtime.DisposableEffect\n',
        1,
    )
if 'import androidx.lifecycle.Lifecycle\n' not in s:
    require_once(s, 'import androidx.lifecycle.viewmodel.compose.viewModel\n', 'Lifecycle import anchor')
    s = s.replace(
        'import androidx.lifecycle.viewmodel.compose.viewModel\n',
        'import androidx.lifecycle.Lifecycle\n'
        'import androidx.lifecycle.LifecycleEventObserver\n'
        'import androidx.lifecycle.compose.LocalLifecycleOwner\n'
        'import androidx.lifecycle.viewmodel.compose.viewModel\n',
        1,
    )

context_anchor = '    val context = LocalContext.current\n'
require_once(s, context_anchor, 'app context anchor')
lifecycle_refresh = r'''    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_START) vm.refreshPlaylistsAtAppStart()
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
'''
s = s.replace(context_anchor, lifecycle_refresh, 1)

old_sync = '            if (sync is DeviceSyncResult.Success && sync.changed) vm.refreshProfiles()\n'
new_sync = '            if (sync is DeviceSyncResult.Success) vm.refreshProfiles()\n'
require_once(s, old_sync, 'conditional dashboard UI refresh')
s = s.replace(old_sync, new_sync, 1)
app.write_text(s)


checks = [
    (build, 'versionName = "0.7.2"'),
    (build, 'versionCode = 702'),
    (player, 'private fun V072UseVlcLiveFallback(item: MediaEntry)'),
    (player, r'(?:RAW|HEVC|H\.?265)'),
    (player, 'if (V072UseVlcLiveFallback(item))'),
    (vm, 'fun refreshPlaylistsAtAppStart()'),
    (vm, 'm3uCache.clear()'),
    (vm, 'xtreamLibraryCache.clear()'),
    (app, 'Lifecycle.Event.ON_START'),
    (app, 'if (sync is DeviceSyncResult.Success) vm.refreshProfiles()'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.2 marker {marker} in {path}")

print("Android v0.7.2 RAW/MP2 routing and startup playlist refresh applied")
