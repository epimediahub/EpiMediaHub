#!/usr/bin/env python3
"""v1.0.87 QA: opt-in 50-fps sport mode + sequential failover.

Never force the user away from a manually selected channel.
Never open two simultaneous IPTV streams or probe the full live catalogue.
Existing playback, updater, intro, VOD, VPN and EpiScene remain unchanged.
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
        raise SystemExit(f"STOP_V187_ANCHOR {path.name} {n} {old[:96]!r}")
    path.write_text(s.replace(old, new, 1), encoding="utf-8")

once(gradle, "versionCode = 1086", "versionCode = 1087")
once(gradle, 'versionName = "1.0.86"', 'versionName = "1.0.87"')
for name in ("V187SportMode.kt", "V187SportModeOffer.kt"):
    shutil.copy2(here / name, ui / name)
tests = app / "src/test/java/de/epimediahub/app/ui"
tests.mkdir(parents=True, exist_ok=True)
shutil.copy2(here / "V187SportModeTest.kt", tests / "V187SportModeTest.kt")

# The full-category method from v186 stays. Removing auto-redirection from
# BOTH entry points is essential: a user selecting 4K MUST see 4K first.
once(vm,
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
''',
'''        // Manual choice always wins. Sport mode starts ONLY after "Ja".
        v187SportAttempt = null
        val v186Candidates = if (item.kind == MediaKind.LIVE)
            v186LiveCandidates(item, episodeList) else episodeList
        if (item.kind == MediaKind.LIVE)
            de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
''')
once(vm,
'''        val v186Candidates = v186LiveCandidates(item, channelList)
        de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
        val v186Preferred = de.epimediahub.app.ui.V186SportPriority.preferred(
            item, v186Candidates, _ui.value.active?.id.orEmpty())
        if (v186Preferred.id != item.id ||
            v186Preferred.sourceProfileId != item.sourceProfileId) {
            switchLiveChannel(v186Preferred, v186Candidates)
            return
        }
''',
'''        // A user channel change cancels any previous Sportmode search.
        if (v187SportAttempt != null && !v187SportIsCandidate(item))
            v187SportAttempt = null
        val v186Candidates = v186LiveCandidates(item, channelList)
        de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
''')

# Entire state machine lives in the retained ViewModel, not in a transient
# player view. It can advance when a candidate fails, returns 25 fps or hangs.
once(vm,
'''    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {
''',
'''    private data class V187SportAttempt(
        val original: MediaEntry,
        val channelList: List<MediaEntry>,
        val candidates: List<MediaEntry>,
        val index: Int,
        val confirmed50: Boolean = false
    )
    private var v187SportAttempt: V187SportAttempt? = null

    fun v187SportIsCandidate(item: MediaEntry): Boolean {
        val probe = v187SportAttempt ?: return false
        val target = probe.candidates.getOrNull(probe.index) ?: return false
        return target.id == item.id &&
            target.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() } ==
                item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() }
    }

    fun v187SportCandidatePending(item: MediaEntry): Boolean =
        v187SportIsCandidate(item) && v187SportAttempt?.confirmed50 != true

    fun v187SportOfferAvailable(item: MediaEntry, provided: List<MediaEntry>): Boolean {
        if (item.kind != MediaKind.LIVE || v187SportAttempt != null) return false
        val profile = item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() }
        if (de.epimediahub.app.ui.V187SportPromptMemory.wasDeclined(profile, item.id)) return false
        de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
        val candidates = v186LiveCandidates(item, provided)
        return de.epimediahub.app.ui.V187SportMode.alternatives(
            item, candidates, profile,
            de.epimediahub.app.ui.V186SportPriority::rememberedRate
        ).isNotEmpty()
    }

    fun v187SportDecline(item: MediaEntry) {
        val profile = item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() }
        de.epimediahub.app.ui.V187SportPromptMemory.decline(profile, item.id)
    }

    fun v187SportAccept(item: MediaEntry, provided: List<MediaEntry>) {
        val playing = _ui.value.screen as? Screen.Player ?: return
        if (playing.item.id != item.id || item.kind != MediaKind.LIVE) return
        v187SportDecline(item) // No repeated popup after accepting or declining.
        val category = v186LiveCandidates(item, provided)
        val profile = item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() }
        de.epimediahub.app.ui.V186SportPriority.initialize(getApplication<Application>())
        val candidates = de.epimediahub.app.ui.V187SportMode.alternatives(
            item, category, profile,
            de.epimediahub.app.ui.V186SportPriority::rememberedRate
        )
        if (candidates.isEmpty()) return
        v187SportAttempt = V187SportAttempt(item, category, candidates, 0)
        // Same channel list, same provider, only one candidate at a time.
        switchLiveChannel(candidates[0], category)
    }

    fun v187SportCandidateObserved(item: MediaEntry, fps: Int) {
        if (!v187SportIsCandidate(item)) return
        when (fps) {
            50 -> {
                // Retain the active route: if the currently working 50fps
                // stream fails later, continue with remaining alternatives.
                val active = v187SportAttempt ?: return
                if (!active.confirmed50) v187SportAttempt = active.copy(confirmed50 = true)
            }
            25 -> v187SportCandidateFailed(item) // Try another alternative.
        }
    }

    /**
     * Player calls this for a dead stream, unsupported decode, HTTP error or
     * 18-second no-FPS timeout. Returns true only for an active Sportmode trial.
     */
    fun v187SportCandidateFailed(item: MediaEntry, httpCode: Int? = null): Boolean {
        if (!v187SportIsCandidate(item)) return false
        val previous = v187SportAttempt ?: return false
        val next = if (de.epimediahub.app.ui.V161PlaybackRetryPolicy.providerBlocked(httpCode))
            null else de.epimediahub.app.ui.V187SportMode.nextIndex(
                previous.index, previous.candidates.size
            )
        if (next != null) {
            v187SportAttempt = previous.copy(index = next, confirmed50 = false)
            switchLiveChannel(previous.candidates[next], previous.channelList)
        } else {
            v187SportAttempt = null
            // Every alternative failed: restore the exact channel the viewer
            // chose before consenting (e.g., the working 4K25 stream).
            switchLiveChannel(previous.original, previous.channelList)
        }
        return true
    }

    fun play(item: MediaEntry, episodeList: List<MediaEntry> = emptyList()) {
''')

# If the viewer opens the live list or navigates out, cancel any pending
# candidate inspection rather than switching behind their back.
once(vm,
'''    fun openLiveChannels(item: MediaEntry, channelList: List<MediaEntry>) {
''',
'''    fun openLiveChannels(item: MediaEntry, channelList: List<MediaEntry>) {
        v187SportAttempt = null
''')

# Keep raw stream startup behaviour, player selection and standard fallback
# for every non-Sportmode user-initiated channel play.
once(player,
'''    var v185MeasuredFps by remember(item.resumeKey) { mutableIntStateOf(0) }
''',
'''    var v185MeasuredFps by remember(item.resumeKey) { mutableIntStateOf(0) }
    var v187SportOffer by remember(item.resumeKey) { mutableStateOf(false) }
    if (v187SportOffer) V187SportModeOffer(
        onYes = {
            v187SportOffer = false
            vm.v187SportAccept(item, episodeList)
        },
        onNo = {
            v187SportOffer = false
            vm.v187SportDecline(item)
        }
    )
''')
once(player,
'''                    V186SportPriority.recordMeasured(context, item, candidate, u.active?.id.orEmpty())
''',
'''                    V186SportPriority.recordMeasured(context, item, candidate, u.active?.id.orEmpty())
                    if (vm.v187SportIsCandidate(item)) {
                        vm.v187SportCandidateObserved(item, candidate)
                    } else if (candidate == 25 &&
                        vm.v187SportOfferAvailable(item, episodeList)) {
                        v187SportOffer = true
                    }
''')
# If format/PTS cannot be read, don't sit on a dead or unknown candidate
# indefinitely. This job is canceled when the player/item changes.
once(player,
'''    DisposableEffect(capture) { onDispose { capture?.close() } }
''',
'''    // Sport-mode candidate only; regular 25-fps playback is never timed out.
    LaunchedEffect(player, item.resumeKey) {
        if (item.kind == MediaKind.LIVE && vm.v187SportIsCandidate(item)) {
            delay(18_000L)
            if (vm.v187SportCandidatePending(item))
                vm.v187SportCandidateFailed(item)
        }
    }
    DisposableEffect(capture) { onDispose { capture?.close() } }
''')
# Player first-frame watchdog must advance candidates rather than force
# VLC or get stuck on a bad Full-HD stream.
once(player,
'''                        if (needsCompatibilityPlayer) {
                            val nextCandidate = activeUrl + 1
                            if (nextCandidate < playbackUrls.size && activeUrl < 2) {
                                openUrl(nextCandidate)
                            } else {
                                compatibilityUrl = playbackUrls.getOrNull(attempt).orEmpty()
                                playbackError = ""
                                useVlc = true
                            }
                        }
''',
'''                        if (needsCompatibilityPlayer) {
                            if (vm.v187SportIsCandidate(item)) {
                                vm.v187SportCandidateFailed(item)
                            } else {
                                val nextCandidate = activeUrl + 1
                                if (nextCandidate < playbackUrls.size && activeUrl < 2) {
                                    openUrl(nextCandidate)
                                } else {
                                    compatibilityUrl = playbackUrls.getOrNull(attempt).orEmpty()
                                    playbackError = ""
                                    useVlc = true
                                }
                            }
                        }
''')
once(player,
'''            override fun onPlayerError(error: PlaybackException) {
                cancelWatchdog()
''',
'''            override fun onPlayerError(error: PlaybackException) {
                cancelWatchdog()
                if (vm.v187SportIsCandidate(item)) {
                    var sportCause: Throwable? = error
                    var sportHttp: Int? = null
                    while (sportCause != null) {
                        if (sportCause is InvalidResponseCodeException) {
                            sportHttp = sportCause.responseCode
                            break
                        }
                        sportCause = sportCause.cause
                    }
                    vm.v187SportCandidateFailed(item, sportHttp)
                    return
                }
''')

# Replace the old direct one-step 50fps switch button by a fully optional,
# explicitly named Sportmode button. "Nein" never changes the stream.
once(player,
'''                    if (v185Alternative != null && v185MeasuredFps != 50) {
                        TextButton(
                            onClick = { vm.switchLiveChannel(v185Alternative, episodeList) },
                            modifier = Modifier.v114FocusRing()
                        ) { Text("50 FPS · Alternative", color = Color(0xFF72E8D3)) }
                    }
''',
'''                    if (item.kind == MediaKind.LIVE && v185MeasuredFps == 25 &&
                        vm.v187SportOfferAvailable(item, episodeList)) {
                        TextButton(
                            onClick = { v187SportOffer = true },
                            modifier = Modifier.v114FocusRing()
                        ) { Text("Sportmodus · Optional", color = Color(0xFF72E8D3)) }
                    }
''')

print("V187_OPT_IN_SPORTMODE_FULL_CATEGORY_SEQUENTIAL_FALLBACK_APPLIED")
print("V187_NO_FORCED_SWITCH_ALL_MANUAL_CHANNELS_AVAILABLE")
print("V187_NO_PARALLEL_IPTV_STREAMS_PUBLIC_UPDATER_UNCHANGED")
