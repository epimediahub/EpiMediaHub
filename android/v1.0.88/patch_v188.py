#!/usr/bin/env python3
"""EpiMediaHub 1.0.88: cross-category opt-in Sportmodus, verified FPS catalogue.

Apply after v187. Do not probe or open streams in the background. Learn the
real PTS frame rate only while a viewer watches the channel normally, and keep
that fact per provider, category and stream ID in persistent preferences.

Never silently redirect user-selected channels or offer Sportmodus unless
there is at least one confirmed 50fps alternate in the same provider.
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
tests = app / "src/test/java/de/epimediahub/app/ui"

def once(path: Path, old: str, new: str):
    original = path.read_text(encoding="utf-8")
    count = original.count(old)
    if count != 1:
        raise SystemExit(f"STOP_V188_ANCHOR {path.name} {count} {old[:95]!r}")
    path.write_text(original.replace(old, new, 1), encoding="utf-8")

once(gradle, "versionCode = 1087", "versionCode = 1088")
once(gradle, 'versionName = "1.0.87"', 'versionName = "1.0.88"')
for name in ("V188SportCatalog.kt", "V188VerifiedFps.kt", "V188SportMode.kt"):
    shutil.copy2(here / name, ui / name)
# Replace only the older, generic AlertDialog; retain the same composable
# name so existing player uses it without modifying all the call sites.
shutil.copy2(here / "V188SportModeOffer.kt", ui / "V187SportModeOffer.kt")
tests.mkdir(parents=True, exist_ok=True)
for name in ("V188SportCatalogTest.kt", "V188VerifiedFpsTest.kt"):
    shutil.copy2(here / name, tests / name)

# Authenticate the snapshot against the ACTUAL active player. In v187 the
# global weak reference could momentarily refer to the retained old surface
# while changing channels, and its PTS rate could then label the new stream.
surface = ui / "V121VodSurface.kt"
once(surface,
'''    fun playbackSnapshot(): V122PlaybackSnapshot? = frameRate?.snapshot()
''',
'''    fun isCurrentPlayer(candidate: Player): Boolean = boundPlayer === candidate
    fun playbackSnapshot(): V122PlaybackSnapshot? = frameRate?.snapshot()
''')
playbackInfo = ui / "V122PlaybackInfo.kt"
once(playbackInfo,
'''    fun snapshot(): V122PlaybackSnapshot? = active.get()?.playbackSnapshot()
''',
'''    fun snapshot(): V122PlaybackSnapshot? = active.get()?.playbackSnapshot()
    fun snapshotFor(player: androidx.media3.common.Player): V122PlaybackSnapshot? =
        active.get()?.takeIf { it.isCurrentPlayer(player) }?.playbackSnapshot()
''')

# The retained ViewModel owns the candidate list across channel changes. Read
# the full category cache (plus already loaded rows) for the CURRENT provider.
# As with v187, it never opens any extra IPTV connection for inventory.
once(vm,
'''    fun v187SportOfferAvailable(item: MediaEntry, provided: List<MediaEntry>): Boolean {
''',
'''    private fun v188AllLiveCandidates(
        item: MediaEntry, provided: List<MediaEntry>
    ): List<MediaEntry> {
        val state = _ui.value
        val profileId = item.sourceProfileId.ifBlank { state.active?.id.orEmpty() }
        val profile = state.playlists.firstOrNull { it.id == profileId }
            ?: state.active?.takeIf { it.id == profileId }
        val cached = profile?.let {
            libraryCatalogCache[catalogueKey(it, MediaKind.LIVE)]?.rows
        }.orEmpty()
        val current = state.catalogRows.takeIf {
            state.active?.id == profileId && state.contentFilterKind == MediaKind.LIVE
        }.orEmpty()
        // Keep all provider categories, including copies of variants that
        // appear in different category groups. V188SportCatalog de-duplicates.
        val allRows = cached + current
        return de.epimediahub.app.ui.V188SportCatalog.samePlaylist(
            item, provided, allRows, profileId)
    }

    fun v187SportOfferAvailable(item: MediaEntry, provided: List<MediaEntry>): Boolean {
''')

once(vm,
'''        de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
        val candidates = v186LiveCandidates(item, provided)
        return de.epimediahub.app.ui.V187SportMode.alternatives(
            item, candidates, profile,
            de.epimediahub.app.ui.V186SportPriority::rememberedRate
        ).isNotEmpty()
''',
'''        de.epimediahub.app.ui.V188VerifiedFps.initialize(getApplication<Application>())
        val candidates = v188AllLiveCandidates(item, provided)
        return de.epimediahub.app.ui.V188SportMode.verifiedAlternatives(
            item, candidates, profile,
            de.epimediahub.app.ui.V188VerifiedFps::rememberedRate
        ).isNotEmpty()
''')

once(vm,
'''        val category = v186LiveCandidates(item, provided)
        val profile = item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() }
        de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
        val candidates = de.epimediahub.app.ui.V187SportMode.alternatives(
            item, category, profile,
            de.epimediahub.app.ui.V186SportPriority::rememberedRate
        )
''',
'''        val category = v188AllLiveCandidates(item, provided)
        val profile = item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() }
        de.epimediahub.app.ui.V188VerifiedFps.initialize(getApplication<Application>())
        val candidates = de.epimediahub.app.ui.V188SportMode.verifiedAlternatives(
            item, category, profile,
            de.epimediahub.app.ui.V188VerifiedFps::rememberedRate
        )
''')

# Drop v186's decoder-reported FPS fallback; it caused unverified 50-fps
# badges and polluted the old in-memory cache. Only stable PTS cadence may
# update a 25/50 measurement or persist a channel's actual FPS.
once(player,
'''            V186SportPriority.initialize(context)
''',
'''            V188VerifiedFps.initialize(context)
''')
once(player,
'''                val snapshot = V122ActiveVideo.snapshot()
                val decoded = snapshot?.rendered
                    ?: player.videoDecoderCounters?.renderedOutputBufferCount ?: 0
                val candidate = if (player.isPlaying && decoded >= 90)
                    V186SportPriority.observedRate(
                        snapshot?.measuredFps ?: 0f,
                        snapshot?.metadataFps ?: 0f,
                        player.videoFormat?.frameRate ?: 0f)
                    else 0
''',
'''                val snapshot = V122ActiveVideo.snapshotFor(player)
                val candidate = V188VerifiedFps.verifiedCandidate(
                    snapshot?.measuredFps ?: 0f,
                    player.isPlaying,
                    snapshot?.rendered ?: 0
                )
''')
once(player,
'''                    V186SportPriority.recordMeasured(context, item, candidate, u.active?.id.orEmpty())
''',
'''                    V188VerifiedFps.recordVerified(context, item, candidate, u.active?.id.orEmpty())
''')
once(player,
'''                                else -> "Bildrate wird gemessen"
''',
'''                                else -> V188VerifiedFps.diagnosticLabel(
                                    0, V186SportPriority.classify(player.videoFormat?.frameRate ?: 0f))
''')

# Old compatibility-name match is unused in v187; make sure the on-screen
# offer button continues to consult the v188 confirmed-only ViewModel check.
assert "vm.v187SportOfferAvailable(item, episodeList)" in player.read_text()
assert "vm.v187SportCandidateObserved(item, candidate)" in player.read_text()
assert "v187SportCandidateFailed(item, sportHttp)" in player.read_text()
assert "V188SportMode.verifiedAlternatives(" in vm.read_text()
print("V188_CROSS_CATEGORY_SPORT_MODE_CONFIRMED_50_ONLY")
print("V188_PTS_VERIFIED_RATE_PERSISTED_PER_PLAYLIST_CATEGORY_CHANNEL")
print("V188_NO_BACKGROUND_STREAM_PROBES_NO_AUTO_REDIRECT")
print("V188_MATCHING_EPIMEDIAHUB_DIALOG_NO_PUBLIC_UPDATER_CHANGES")
