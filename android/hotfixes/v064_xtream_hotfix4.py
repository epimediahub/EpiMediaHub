#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# Visible hotfix version.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 606', 'versionCode = 607', 'hotfix4 versionCode')
replace_once(gradle, 'versionName = "0.6.4.3"', 'versionName = "0.6.4.4"', 'hotfix4 versionName')

home = java / "ui/V044Home.kt"
home_text = home.read_text()
if "0.6.4.3" not in home_text:
    raise SystemExit("visible home version 0.6.4.3 not found")
home.write_text(home_text.replace("0.6.4.3", "0.6.4.4", 1))

# Ensure Live playback uses the exact URL from the provider M3U before entering
# PlayerScreen. The channel list remains fast because entries() still prefetches
# asynchronously; only a channel click waits for a cache miss, on Dispatchers.IO.
xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()
anchor = '''    fun streamCandidates(item: MediaEntry): List<String> {\n'''
method = '''    fun preparePlaybackItem(item: MediaEntry): MediaEntry {
        if (item.kind != MediaKind.LIVE && item.kind != MediaKind.MOVIE && item.kind != MediaKind.EPISODE) return item
        val exact = exactM3uStreamUrls()[item.id].orEmpty().trim()
        return if (exact.isBlank()) item else item.copy(streamUrl = exact)
    }

    fun streamCandidates(item: MediaEntry): List<String> {
'''
if anchor not in s:
    raise SystemExit("streamCandidates anchor missing")
s = s.replace(anchor, method, 1)
xtream.write_text(s)

vm = java / "MainViewModel.kt"
s = vm.read_text()
old_play = '''        if (item.kind == MediaKind.EPISODE && episodeList.isEmpty() && item.seriesId.isNotBlank() && profile != null && profile.type == PlaylistType.XTREAM) {
            set { it.copy(loading = true) }
            viewModelScope.launch {
                val siblings = runCatching {
                    withContext(Dispatchers.IO) { XtreamClient(profile).episodes(item.seriesId).map { it.copy(sourceProfileId = profile.id) } }
                }.getOrDefault(emptyList())
                set { it.copy(loading = false) }
                navigate(Screen.Player(item, siblings), remember = true)
            }
        } else {
            navigate(Screen.Player(item, episodeList))
        }
'''
new_play = '''        if (item.kind == MediaKind.LIVE && profile != null && profile.type == PlaylistType.XTREAM) {
            set { it.copy(loading = true) }
            viewModelScope.launch {
                val prepared = runCatching {
                    withContext(Dispatchers.IO) { XtreamClient(profile).preparePlaybackItem(item) }
                }.getOrDefault(item)
                set { it.copy(loading = false) }
                navigate(Screen.Player(prepared.copy(sourceProfileId = profile.id), episodeList))
            }
        } else if (item.kind == MediaKind.EPISODE && episodeList.isEmpty() && item.seriesId.isNotBlank() && profile != null && profile.type == PlaylistType.XTREAM) {
            set { it.copy(loading = true) }
            viewModelScope.launch {
                val siblings = runCatching {
                    withContext(Dispatchers.IO) { XtreamClient(profile).episodes(item.seriesId).map { it.copy(sourceProfileId = profile.id) } }
                }.getOrDefault(emptyList())
                set { it.copy(loading = false) }
                navigate(Screen.Player(item, siblings), remember = true)
            }
        } else {
            navigate(Screen.Player(item, episodeList))
        }
'''
if old_play not in s:
    raise SystemExit("MainViewModel play anchor missing")
s = s.replace(old_play, new_play, 1)
vm.write_text(s)

# Surface the real HTTP response code instead of only ERROR_CODE_IO_BAD_HTTP_STATUS.
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
if 'import androidx.media3.datasource.HttpDataSource.InvalidResponseCodeException\n' not in s:
    import_anchor = 'import androidx.media3.datasource.DefaultHttpDataSource\n'
    if import_anchor not in s:
        raise SystemExit("DefaultHttpDataSource import anchor missing")
    s = s.replace(import_anchor, import_anchor + 'import androidx.media3.datasource.HttpDataSource.InvalidResponseCodeException\n', 1)

old_error = '''            override fun onPlayerError(error: PlaybackException) {
                cancelWatchdog()
                val next = activeUrl + 1
                if (next < playbackUrls.size) {
                    openUrl(next)
                } else {
                    playbackError = "Der Anbieter hat alle kompatiblen Stream-Adressen abgelehnt (${error.errorCodeName})."
                }
            }
'''
new_error = '''            override fun onPlayerError(error: PlaybackException) {
                cancelWatchdog()
                var cause: Throwable? = error
                var httpCode: Int? = null
                while (cause != null) {
                    if (cause is InvalidResponseCodeException) {
                        httpCode = cause.responseCode
                        break
                    }
                    cause = cause.cause
                }
                val next = activeUrl + 1
                if (next < playbackUrls.size) {
                    openUrl(next)
                } else {
                    val detail = httpCode?.let { "HTTP $it" } ?: error.errorCodeName
                    playbackError = "Der Anbieter hat alle kompatiblen Stream-Adressen abgelehnt. Letzter Fehler: $detail (Kandidat ${activeUrl + 1}/${playbackUrls.size})."
                }
            }
'''
if old_error not in s:
    raise SystemExit("Player error anchor missing")
s = s.replace(old_error, new_error, 1)
player.write_text(s)

# Sanity markers.
for marker, path in [
    ('versionName = "0.6.4.4"', gradle),
    ('versionCode = 607', gradle),
    ('fun preparePlaybackItem(item: MediaEntry)', xtream),
    ('exactM3uStreamUrls()[item.id]', xtream),
    ('XtreamClient(profile).preparePlaybackItem(item)', vm),
    ('InvalidResponseCodeException', player),
    ('httpCode = cause.responseCode', player),
    ('Letzter Fehler: $detail', player),
]:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix4 marker {marker} in {path}")

print("Android v0.6.4.4 exact provider URL + HTTP status diagnostic hotfix applied")
