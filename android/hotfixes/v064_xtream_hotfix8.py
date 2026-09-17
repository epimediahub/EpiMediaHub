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

# Version
build = root / "app/build.gradle.kts"
replace_once(build, 'versionCode = 610', 'versionCode = 611', 'hotfix8 versionCode')
replace_once(build, 'versionName = "0.6.4.7"', 'versionName = "0.6.4.8"', 'hotfix8 versionName')

home = java / "ui/V044Home.kt"
replace_once(home, "0.6.4.7", "0.6.4.8", "hotfix8 visible version")

# Media identity must include source playlist so identical Xtream ids from different
# providers never collide in resume/favorites/recent keys.
models = java / "model/Models.kt"
replace_once(
    models,
    '    val resumeKey: String get() = "${kind.name}:$id"\n',
    '    val resumeKey: String get() = "${sourceProfileId.ifBlank { "legacy" }}:${kind.name}:$id"\n',
    'source-scoped resumeKey'
)

prefs = java / "data/PrefsRepository.kt"
s = prefs.read_text()

anchor = '    fun getResume(key:String)=p.getLong("resume_$key",0L)\n\n'
helper = '''    private fun collectionKey(base: String, profileId: String): String =
        if (profileId.isBlank()) base else "${base}_$profileId"

    fun getResume(key:String)=p.getLong("resume_$key",0L)

'''
if anchor not in s:
    raise SystemExit("Prefs collectionKey anchor missing")
s = s.replace(anchor, helper, 1)

old_save = '''    fun savePlayback(item: MediaEntry, pos: Long, duration: Long) {
        if(item.kind==MediaKind.LIVE) return
        val safe=pos.coerceAtLeast(0L)
        val done=duration>0 && safe >= (duration*.93).toLong()
        if(done) p.edit().remove("resume_${item.resumeKey}").apply() else p.edit().putLong("resume_${item.resumeKey}",safe).apply()
        val list=loadContinue().filterNot{it.media.resumeKey==item.resumeKey}.toMutableList()
        if(!done && safe>=15_000) list.add(0,ContinueItem(item,safe,duration.coerceAtLeast(0),System.currentTimeMillis()))
        writeArray("continue",list.take(60).map(::continueJson))
    }

    fun loadContinue(): List<ContinueItem> = readArray("continue").mapNotNull { o ->
        runCatching { ContinueItem(mediaFromJson(o.getJSONObject("media")),o.optLong("position"),o.optLong("duration"),o.optLong("updated")) }.getOrNull()
    }.sortedByDescending{it.updatedAt}

    fun recordRecentlyWatched(item: MediaEntry) {
        if (item.kind == MediaKind.LIVE) return
        val list = loadRecentlyWatched().filterNot { it.resumeKey == item.resumeKey }.toMutableList()
        list.add(0, item)
        writeArray("recently_watched", list.take(80).map(::mediaJson))
    }

    fun loadRecentlyWatched(): List<MediaEntry> = readArray("recently_watched")
        .mapNotNull { runCatching { mediaFromJson(it) }.getOrNull() }

    fun toggleFavorite(item: MediaEntry): Boolean {
        val list=loadFavoriteEntries().toMutableList()
        val i=list.indexOfFirst{it.resumeKey==item.resumeKey}
        val added=i<0
        if(added) list.add(0,item) else list.removeAt(i)
        writeArray("favorites_items",list.take(200).map(::mediaJson))
        return added
    }
    fun isFavorite(item: MediaEntry)=loadFavoriteEntries().any{it.resumeKey==item.resumeKey}
    fun loadFavoriteEntries(): List<MediaEntry> = readArray("favorites_items").mapNotNull { runCatching{mediaFromJson(it)}.getOrNull() }
'''
new_save = '''    fun savePlayback(item: MediaEntry, pos: Long, duration: Long) {
        if(item.kind==MediaKind.LIVE) return
        val profileId = item.sourceProfileId
        val safe=pos.coerceAtLeast(0L)
        val done=duration>0 && safe >= (duration*.93).toLong()
        if(done) p.edit().remove("resume_${item.resumeKey}").apply() else p.edit().putLong("resume_${item.resumeKey}",safe).apply()
        val list=loadContinue(profileId).filterNot{it.media.resumeKey==item.resumeKey}.toMutableList()
        if(!done && safe>=15_000) list.add(0,ContinueItem(item,safe,duration.coerceAtLeast(0),System.currentTimeMillis()))
        writeArray(collectionKey("continue", profileId),list.take(60).map(::continueJson))
    }

    fun loadContinue(profileId: String = ""): List<ContinueItem> {
        fun decode(key: String) = readArray(key).mapNotNull { o ->
            runCatching { ContinueItem(mediaFromJson(o.getJSONObject("media")),o.optLong("position"),o.optLong("duration"),o.optLong("updated")) }.getOrNull()
        }.sortedByDescending{it.updatedAt}
        val scoped = decode(collectionKey("continue", profileId))
        if (profileId.isBlank() || scoped.isNotEmpty()) return scoped
        return decode("continue").filter { it.media.sourceProfileId == profileId }
    }

    fun recordRecentlyWatched(item: MediaEntry) {
        if (item.kind == MediaKind.LIVE) return
        val profileId = item.sourceProfileId
        val list = loadRecentlyWatched(profileId).filterNot { it.resumeKey == item.resumeKey }.toMutableList()
        list.add(0, item)
        writeArray(collectionKey("recently_watched", profileId), list.take(80).map(::mediaJson))
    }

    fun loadRecentlyWatched(profileId: String = ""): List<MediaEntry> {
        fun decode(key: String) = readArray(key).mapNotNull { runCatching { mediaFromJson(it) }.getOrNull() }
        val scoped = decode(collectionKey("recently_watched", profileId))
        if (profileId.isBlank() || scoped.isNotEmpty()) return scoped
        return decode("recently_watched").filter { it.sourceProfileId == profileId }
    }

    fun toggleFavorite(item: MediaEntry): Boolean {
        val profileId = item.sourceProfileId
        val list=loadFavoriteEntries(profileId).toMutableList()
        val i=list.indexOfFirst{it.resumeKey==item.resumeKey}
        val added=i<0
        if(added) list.add(0,item) else list.removeAt(i)
        writeArray(collectionKey("favorites_items", profileId),list.take(200).map(::mediaJson))
        return added
    }
    fun isFavorite(item: MediaEntry)=loadFavoriteEntries(item.sourceProfileId).any{it.resumeKey==item.resumeKey}
    fun loadFavoriteEntries(profileId: String = ""): List<MediaEntry> {
        fun decode(key: String) = readArray(key).mapNotNull { runCatching{mediaFromJson(it)}.getOrNull() }
        val scoped = decode(collectionKey("favorites_items", profileId))
        if (profileId.isBlank() || scoped.isNotEmpty()) return scoped
        return decode("favorites_items").filter { it.sourceProfileId == profileId }
    }

    fun clearPlaylistCollections(profileId: String) {
        if (profileId.isBlank()) return
        val edit = p.edit()
        edit.remove(collectionKey("continue", profileId))
        edit.remove(collectionKey("recently_watched", profileId))
        edit.remove(collectionKey("favorites_items", profileId))
        p.all.keys.filter { it.startsWith("resume_${profileId}:") }.forEach { edit.remove(it) }
        edit.apply()
    }
'''
if old_save not in s:
    raise SystemExit("Prefs global collection block anchor missing")
s = s.replace(old_save, new_save, 1)
prefs.write_text(s)

# MainViewModel should ask PrefsRepository for the active playlist's own collections,
# rather than loading global arrays and filtering them in UI state.
vm = java / "MainViewModel.kt"
s = vm.read_text()
old_refresh = '''    private fun refreshCollections() {
        set {
            val activeId = it.active?.id.orEmpty()
            val allowLegacyUnbound = it.playlists.size <= 1
            it.copy(
                favorites = prefs.loadFavoriteEntries().filter { media ->
                    media.sourceProfileId == activeId || (media.sourceProfileId.isBlank() && allowLegacyUnbound)
                },
                continueWatching = prefs.loadContinue().filter { entry ->
                    entry.media.sourceProfileId == activeId || (entry.media.sourceProfileId.isBlank() && allowLegacyUnbound)
                },
                recentlyWatched = prefs.loadRecentlyWatched().filter { media ->
                    media.sourceProfileId == activeId || (media.sourceProfileId.isBlank() && allowLegacyUnbound)
                },
                preferredAudioLanguage = prefs.preferredAudioLanguage,
                preferredSubtitleLanguage = prefs.preferredSubtitleLanguage
            )
        }
    }
'''
new_refresh = '''    private fun refreshCollections() {
        set {
            val activeId = it.active?.id.orEmpty()
            it.copy(
                favorites = prefs.loadFavoriteEntries(activeId),
                continueWatching = prefs.loadContinue(activeId),
                recentlyWatched = prefs.loadRecentlyWatched(activeId),
                preferredAudioLanguage = prefs.preferredAudioLanguage,
                preferredSubtitleLanguage = prefs.preferredSubtitleLanguage
            )
        }
    }
'''
if old_refresh not in s:
    raise SystemExit("MainViewModel filtered collection block missing")
s = s.replace(old_refresh, new_refresh, 1)

old_remove = '''        prefs.activePlaylistId = list.firstOrNull()?.id.orEmpty()
        m3uCache.remove(id)
'''
new_remove = '''        prefs.activePlaylistId = list.firstOrNull()?.id.orEmpty()
        prefs.clearPlaylistCollections(id)
        m3uCache.remove(id)
        xtreamLibraryCache.keys.removeAll { it.startsWith("$id|") }
'''
if old_remove not in s:
    raise SystemExit("removePlaylist cleanup anchor missing")
s = s.replace(old_remove, new_remove, 1)

vm.write_text(s)

checks = [
    (build, 'versionName = "0.6.4.8"'),
    (build, 'versionCode = 611'),
    (models, 'sourceProfileId.ifBlank { "legacy" }'),
    (prefs, 'collectionKey("favorites_items", profileId)'),
    (prefs, 'collectionKey("continue", profileId)'),
    (prefs, 'collectionKey("recently_watched", profileId)'),
    (prefs, 'fun clearPlaylistCollections(profileId: String)'),
    (vm, 'favorites = prefs.loadFavoriteEntries(activeId)'),
    (vm, 'continueWatching = prefs.loadContinue(activeId)'),
    (vm, 'recentlyWatched = prefs.loadRecentlyWatched(activeId)'),
    (vm, 'prefs.clearPlaylistCollections(id)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix8 marker {marker} in {path}")

print("Android v0.6.4.8 strict per-playlist favorites/resume/history storage hotfix applied")
