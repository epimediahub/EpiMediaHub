#!/usr/bin/env python3
"""v1.0.86 QA: correct 50 FPS variant selection in the full live category.

Applies after v1.0.85; never probes IPTV streams, never touches the customer
updater, VPN, EpiScene, film cadence or the 17.5-second intro.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
app = root / "app"
ui = app / "src/main/java/de/epimediahub/app/ui"
vm = app / "src/main/java/de/epimediahub/app/MainViewModel.kt"
player = ui / "PlayerScreen.kt"
gradle = app / "build.gradle.kts"

def once(path: Path, old: str, new: str):
    s = path.read_text(encoding="utf-8")
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"STOP_V186_ANCHOR {path.name} {n} {old[:90]!r}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")

once(gradle, "versionCode = 1085", "versionCode = 1086")
once(gradle, 'versionName = "1.0.85"', 'versionName = "1.0.86"')
shutil.copy2(here / "V186SportPriority.kt", ui / "V186SportPriority.kt")
tests = app / "src/test/java/de/epimediahub/app/ui"
tests.mkdir(parents=True, exist_ok=True)
shutil.copy2(here / "V186SportPriorityTest.kt", tests / "V186SportPriorityTest.kt")

# The EpiMediaHub Live-TV screen ordinarily supplies the entire category list,
# but favorite/recent/search flows can supply one or only a subset. Consult only
# the already-loaded catalogue, prefer the selected category's complete list,
# and NEVER fetch or open a stream to discover alternatives.
once(vm,
'''    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {
''',
'''    private fun v186LiveCandidates(item: MediaEntry, provided: List<MediaEntry>): List<MediaEntry> {
        val state = _ui.value
        val profileId = item.sourceProfileId.ifBlank { state.active?.id.orEmpty() }
        val profile = state.playlists.firstOrNull { it.id == profileId } ?: state.active
        val category = item.categoryId
        val cachedRows = profile?.let {
            libraryCatalogCache[catalogueKey(it, MediaKind.LIVE)]?.rows
        }
        val categoryItems = if (category.isNotBlank()) {
            cachedRows?.get(category)
                ?: state.catalogRows.takeIf {
                    state.active?.id == profileId &&
                        state.contentFilterKind == MediaKind.LIVE
                }?.get(category)
        } else null
        return categoryItems?.takeIf { rows ->
            rows.size > 1 && rows.any { it.id == item.id }
        } ?: provided
    }

    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {
''')

once(vm,
'''        if (item.kind == MediaKind.LIVE) {
            val preferred = de.epimediahub.app.ui.V185SportPriority.preferred(item, episodeList, _ui.value.active?.id.orEmpty())
            if (preferred.id != item.id || preferred.sourceProfileId != item.sourceProfileId) {
                play(preferred, episodeList)
                return
            }
        }
''',
'''        val v186Candidates = if (item.kind == MediaKind.LIVE)
            v186LiveCandidates(item, episodeList) else episodeList
        if (item.kind == MediaKind.LIVE) {
            de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
            val preferred = de.epimediahub.app.ui.V186SportPriority.preferred(
                item, v186Candidates, _ui.value.active?.id.orEmpty())
            if (preferred.id != item.id || preferred.sourceProfileId != item.sourceProfileId) {
                play(preferred, v186Candidates)
                return
            }
        }
''')
once(vm,
'''navigate(Screen.Player(prepared.copy(sourceProfileId = profile.id), episodeList))''',
'''navigate(Screen.Player(prepared.copy(sourceProfileId = profile.id), v186Candidates))''')
once(vm,
'''            navigate(Screen.Player(item, episodeList))
''',
'''            navigate(Screen.Player(item, v186Candidates))
''')

once(vm,
'''        val v185Preferred = de.epimediahub.app.ui.V185SportPriority.preferred(
            item, channelList, _ui.value.active?.id.orEmpty())
        if (v185Preferred.id != item.id ||
            v185Preferred.sourceProfileId != item.sourceProfileId) {
            switchLiveChannel(v185Preferred, channelList)
            return
        }
''',
'''        val v186Candidates = v186LiveCandidates(item, channelList)
        de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
        val v186Preferred = de.epimediahub.app.ui.V186SportPriority.preferred(
            item, v186Candidates, _ui.value.active?.id.orEmpty())
        if (v186Preferred.id != item.id ||
            v186Preferred.sourceProfileId != item.sourceProfileId) {
            switchLiveChannel(v186Preferred, v186Candidates)
            return
        }
''')
once(vm, "Screen.Player(prepared.copy(sourceProfileId = profile.id), channelList)",
    "Screen.Player(prepared.copy(sourceProfileId = profile.id), v186Candidates)")
once(vm, "Screen.Player(item.copy(sourceProfileId = profile.id), channelList)",
    "Screen.Player(item.copy(sourceProfileId = profile.id), v186Candidates)")

# Measure actual PTS cadence; when unavailable, use a stable decoder/format
# FPS only after three observations and 90 decoded frames. No second playback.
once(player,
'''                val snapshot = V122ActiveVideo.snapshot()
                val candidate = if (player.isPlaying && (snapshot?.rendered ?: 0) >= 90)
                    V185SportPriority.classify(snapshot?.measuredFps ?: 0f) else 0
''',
'''                val snapshot = V122ActiveVideo.snapshot()
                val decoded = snapshot?.rendered
                    ?: player.videoDecoderCounters?.renderedOutputBufferCount ?: 0
                val candidate = if (player.isPlaying && decoded >= 90)
                    V186SportPriority.observedRate(
                        snapshot?.measuredFps ?: 0f,
                        snapshot?.metadataFps ?: 0f,
                        player.videoFormat?.frameRate ?: 0f)
                    else 0
''')
once(player, "V185SportPriority.recordMeasured(context, item, candidate, u.active?.id.orEmpty())",
    "V186SportPriority.recordMeasured(context, item, candidate, u.active?.id.orEmpty())")
once(player, "V185SportPriority.initialize(context)", "V186SportPriority.initialize(context)")
once(player,
    "V185SportPriority.recommendedAlternative(item, episodeList, u.active?.id.orEmpty())",
    "V186SportPriority.recommendedAlternative(item, episodeList, u.active?.id.orEmpty())")

# Diagnostic logs reveal neither channel names nor provider credentials.
# A dedicated on-screen indicator already displays confirmed 25 / 50fps.
print("V186_SPORT_PRIORITY_APPLIED_NO_EXTRA_STREAM_CONNECTIONS")
print("V186_BUILD_1086_INTRO_AND_CUSTOMER_UPDATER_UNCHANGED")
