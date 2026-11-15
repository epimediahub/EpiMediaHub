#!/usr/bin/env python3
"""Netflix-oriented VOD controls and episode/version-aware skip metadata."""
import os
import shutil
from pathlib import Path

root = Path(os.environ['PROJECT_ROOT'])
java = root / 'app/src/main/java/de/epimediahub/app'
here = Path(__file__).resolve().parent
gradle = root / 'app/build.gradle.kts'
s = gradle.read_text()
assert s.count('versionCode = 1014') == 1
assert s.count('versionName = "1.0.14"') == 1
gradle.write_text(s.replace('versionCode = 1014', 'versionCode = 1015').replace('versionName = "1.0.14"', 'versionName = "1.0.15"'))
for p in java.rglob('*.kt'):
    text = p.read_text()
    if '1.0.14' in text:
        p.write_text(text.replace('1.0.14', '1.0.15'))

model = java / 'model/Models.kt'
s = model.read_text()
anchor = '    val sourceProfileId: String = ""\n'
assert s.count(anchor) == 1
model.write_text(s.replace(anchor, '    val sourceProfileId: String = "",\n    val imdbId: String = "",\n    val tmdbId: String = ""\n'))

prefs = java / 'data/PrefsRepository.kt'
s = prefs.read_text()
s = s.replace('put("sourceProfileId",m.sourceProfileId)', 'put("sourceProfileId",m.sourceProfileId);put("imdbId",m.imdbId);put("tmdbId",m.tmdbId)')
s = s.replace('sourceProfileId=o.optString("sourceProfileId")', 'sourceProfileId=o.optString("sourceProfileId"),imdbId=o.optString("imdbId"),tmdbId=o.optString("tmdbId")')
prefs.write_text(s)

client = java / 'data/XtreamClient.kt'
s = client.read_text()
# Provider catalog/detail IDs survive navigation, favourites and playback history.
anchor = '                                addedAt = o.optString("added").toLongOrNull() ?: 0L\n'
assert s.count(anchor) == 2
s = s.replace(anchor, '                                addedAt = o.optString("added").toLongOrNull() ?: 0L,\n                                imdbId = V115SkipPolicy.firstImdb(o.optString("imdb_id"), o.optString("imdb")),\n                                tmdbId = V115SkipPolicy.firstTmdb(o.optString("tmdb_id"), o.optString("tmdb")).takeIf { it > 0 }?.toString().orEmpty()\n')
anchor = '            trailer = firstNonBlank(info.optString("youtube_trailer"), info.optString("trailer"), item.trailer)\n'
assert s.count(anchor) == 2
s = s.replace(anchor, '            trailer = firstNonBlank(info.optString("youtube_trailer"), info.optString("trailer"), item.trailer),\n            imdbId = V115SkipPolicy.firstImdb(info.optString("imdb_id"), info.optString("imdb"), item.imdbId),\n            tmdbId = V115SkipPolicy.firstTmdb(info.optString("tmdb_id"), info.optString("tmdb"), item.tmdbId).takeIf { it > 0 }?.toString().orEmpty()\n')
anchor = '                    releaseDate = info.optString("releasedate")\n'
assert s.count(anchor) == 1
# Episode metadata may expose an episode TMDB ID. Only series_info IDs identify
# the parent show for timestamp services, which also require season + episode.
s = s.replace(anchor, '                    releaseDate = info.optString("releasedate"),\n                    year = firstNonBlank(seriesInfo.optString("year"), seriesInfo.optString("releaseDate").take(4), seriesInfo.optString("releasedate").take(4)),\n                    imdbId = V115SkipPolicy.firstImdb(seriesInfo.optString("imdb_id"), seriesInfo.optString("imdb")),\n                    tmdbId = V115SkipPolicy.firstTmdb(seriesInfo.optString("tmdb_id"), seriesInfo.optString("tmdb")).takeIf { it > 0 }?.toString().orEmpty()\n')
client.write_text(s)

vm = java / 'MainViewModel.kt'
s = vm.read_text()
anchor = '    fun skipEpisode(current: MediaEntry, episodeList: List<MediaEntry>, direction: Int) {'
assert anchor in s
s = s.replace(anchor, '''    fun selectV115Episode(current: MediaEntry, selected: MediaEntry, episodeList: List<MediaEntry>) {
        val ordered = de.epimediahub.app.ui.v115OrderedEpisodes(current, episodeList)
        val target = ordered.firstOrNull { it.resumeKey == selected.resumeKey } ?: return
        prefs.recordRecentlyWatched(target)
        refreshCollections()
        set { it.copy(screen = Screen.Player(target, ordered), error = "") }
    }

''' + anchor, 1)
s = s.replace('navigate(Screen.Player(item, siblings), remember = true)', 'val prepared = siblings.firstOrNull { it.id == item.id && it.seriesId == item.seriesId } ?: item.copy(sourceProfileId = profile.id)\n                navigate(Screen.Player(prepared, siblings), remember = true)')
vm.write_text(s)

player = java / 'ui/PlayerScreen.kt'
s = player.read_text()
anchor = '    Box(\n        Modifier\n            .fillMaxSize()\n            .background(Color.Black)\n            .onPreviewKeyEvent { e ->'
assert s.count(anchor) == 1
s = s.replace(anchor, '''    if (item.kind != MediaKind.LIVE) {
        V115VodPlayer(
            player = player, item = item, episodes = episodeList, isTv = isTv, error = playbackError,
            onBack = ::leave,
            onEpisode = { selected -> save(); vm.selectV115Episode(item, selected, episodeList) },
            onAudioLanguage = vm::setAudioLanguage, onSubtitleLanguage = vm::setSubtitleLanguage
        )
        return
    }

''' + anchor, 1)
player.write_text(s)

for name in ('V115PlayerChrome.kt', 'V115PlayerDialogs.kt', 'V115Tracks.kt', 'V115VodPlayer.kt'):
    shutil.copyfile(here / name, java / 'ui' / name)
shutil.copyfile(here / 'V115SkipRepository.kt', java / 'data/V115SkipRepository.kt')
for package, filename in (('data', 'V115SkipPolicyTest.kt'), ('ui', 'V115PlayerTest.kt'), ('ui', 'V115TracksTest.kt')):
    source = here / filename
    if source.exists():
        target = root / 'app/src/test/java/de/epimediahub/app' / package / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
licenses = root / 'app/src/main/assets/licenses'
licenses.mkdir(parents=True, exist_ok=True)
(licenses / 'V115-skip-data.txt').write_text('''Episode timestamps are requested from public APIs on demand.
SkipDB: https://skipdb.tv/ — data ODbL 1.0 + reciprocity. https://skipdb.tv/licenses
TheIntroDB: https://theintrodb.org/ — public read API. https://theintrodb.org/docs
IntroDB: https://introdb.app/ — reasonable media-player integration, no bulk redistribution. https://introdb.app/docs/terms
TVmaze show identifiers: https://www.tvmaze.com/ — CC BY-SA. https://www.tvmaze.com/api
No complete database is redistributed. Cached responses remain private to the installed app.
''')
print('Android 1.0.15: VOD controls, track selection, episode picker and strict skip matching installed')
