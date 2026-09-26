#!/usr/bin/env python3
"""Android 0.9.0: Exo-first Live TV audio and Fire TV-safe search."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def change(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))

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

# Version and current Media3. Keep all Media3 modules on exactly the same version.
gradle = root / "app/build.gradle.kts"
change(gradle, 'versionCode = 809', 'versionCode = 900', 'versionCode')
change(gradle, 'versionName = "0.8.9"', 'versionName = "0.9.0"', 'versionName')
g = gradle.read_text()
for artifact in ("media3-exoplayer", "media3-exoplayer-hls", "media3-ui"):
    old = f'implementation("androidx.media3:{artifact}:1.4.1")'
    new = f'implementation("androidx.media3:{artifact}:1.11.1")'
    if g.count(old) != 1:
        raise SystemExit(f"Media3 dependency anchor missing: {old}")
    g = g.replace(old, new, 1)
gradle.write_text(g)

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        text = path.read_text()
        text = text.replace("0.8.9", "0.9.0")
        path.write_text(text)

# IBO-style strategy: Exo/Media3 is always the primary Live TV engine.
# Never route a channel to VLC just because its display name contains RAW/HEVC/MP2.
# VLC remains available manually and as a true decoder-error fallback.
player = java / "ui/PlayerScreen.kt"
change(
    player,
    'var useVlc by remember(item.resumeKey, item.streamUrl) { mutableStateOf(V072UseVlcLiveFallback(item)) }',
    'var useVlc by remember(item.resumeKey, item.streamUrl) { mutableStateOf(false) }',
    'Exo-first player routing',
)

# Fire TV search: the old implementation launched three Xtream requests for every
# keystroke. Debounce, cancel stale work, prefer the already-loaded catalog and
# only hit the provider when there is no local catalog available.
vm = java / "MainViewModel.kt"
change(
    vm,
    '    private var liveZapGeneration = 0L\n',
    '''    private var liveZapGeneration = 0L
    private var searchJob: kotlinx.coroutines.Job? = null
    private var searchGeneration = 0L
''',
    'search job state',
)

s = vm.read_text()
start, end = function_span(s, "    fun search(q: String)")
search_impl = r'''    fun search(q: String) {
        val profile = _ui.value.active ?: return
        val filterKind = _ui.value.contentFilterKind
        val needle = q.trim()
        val generation = ++searchGeneration
        searchJob?.cancel()

        if (needle.length < 2) {
            set { it.copy(loading = false, searchResults = emptyList(), error = "") }
            return
        }

        // Snapshot immutable row lists; actual filtering happens off the main thread.
        val localRows = _ui.value.catalogRows.values.toList()
        searchJob = viewModelScope.launch {
            // Fire TV on-screen keyboards emit several edits in a very short burst.
            kotlinx.coroutines.delay(320)
            if (generation != searchGeneration || _ui.value.active?.id != profile.id) return@launch

            try {
                if (localRows.any { it.isNotEmpty() }) {
                    val results = withContext(kotlinx.coroutines.Dispatchers.Default) {
                        val seen = HashSet<String>()
                        localRows.asSequence()
                            .flatten()
                            .filter { item ->
                                val matchesKind = filterKind == null || item.kind == filterKind ||
                                    (filterKind == MediaKind.SERIES && item.kind == MediaKind.EPISODE)
                                matchesKind && item.name.contains(needle, ignoreCase = true)
                            }
                            .filter { item -> seen.add(item.resumeKey) }
                            .take(120)
                            .map { item -> item.copy(sourceProfileId = profile.id) }
                            .toList()
                    }
                    if (generation == searchGeneration && _ui.value.active?.id == profile.id) {
                        set { it.copy(loading = false, searchResults = results, error = "") }
                    }
                    return@launch
                }

                if (generation == searchGeneration) set { it.copy(loading = true, error = "") }
                val results = withContext(Dispatchers.IO) {
                    val source = if (profile.type == PlaylistType.XTREAM) {
                        val client = XtreamClient(profile)
                        when (filterKind) {
                            MediaKind.LIVE -> client.entries(MediaKind.LIVE)
                            MediaKind.MOVIE -> client.entries(MediaKind.MOVIE)
                            MediaKind.SERIES, MediaKind.EPISODE -> client.entries(MediaKind.SERIES)
                            null -> client.entries(MediaKind.LIVE) +
                                client.entries(MediaKind.MOVIE) +
                                client.entries(MediaKind.SERIES)
                        }
                    } else {
                        m3uResult(profile).entries
                    }

                    source.asSequence()
                        .filter { item ->
                            val matchesKind = filterKind == null || item.kind == filterKind ||
                                (filterKind == MediaKind.SERIES && item.kind == MediaKind.EPISODE)
                            matchesKind && item.name.contains(needle, ignoreCase = true)
                        }
                        .take(120)
                        .map { item -> item.copy(sourceProfileId = profile.id) }
                        .toList()
                }

                if (generation == searchGeneration && _ui.value.active?.id == profile.id) {
                    set { it.copy(loading = false, searchResults = results, error = "") }
                }
            } catch (cancelled: kotlinx.coroutines.CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (generation == searchGeneration && _ui.value.active?.id == profile.id) {
                    set { it.copy(loading = false, error = error.message ?: "Suche fehlgeschlagen") }
                }
            }
        }
    }'''
vm.write_text(s[:start] + search_impl + s[end:])

checks = [
    (gradle, 'versionCode = 900'),
    (gradle, 'versionName = "0.9.0"'),
    (gradle, 'androidx.media3:media3-exoplayer:1.11.1'),
    (gradle, 'androidx.media3:media3-exoplayer-hls:1.11.1'),
    (gradle, 'androidx.media3:media3-ui:1.11.1'),
    (player, 'mutableStateOf(false)'),
    (player, '.setEnableDecoderFallback(true)'),
    (player, 'tracks.isTypeSupported(C.TRACK_TYPE_AUDIO)'),
    (vm, 'private var searchJob: kotlinx.coroutines.Job? = null'),
    (vm, 'kotlinx.coroutines.delay(320)'),
    (vm, 'localRows.asSequence()'),
    (vm, '.take(120)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.0 marker missing in {path}: {marker}")

# Regression guard: the legacy name heuristic may remain for diagnostics, but it
# must no longer choose the initial player.
if 'mutableStateOf(V072UseVlcLiveFallback(item))' in player.read_text():
    raise SystemExit("Legacy name-based VLC auto-routing is still active")

print("Android 0.9.0 Exo-first audio and Fire TV-safe search applied")
