#!/usr/bin/env python3
"""EpiMediaHub 1.0.93: repair v191 async Sportmodus offer starvation.

Apply strictly AFTER v192. Never modify the working Live HDMI cadence, player
lifecycle, VPN, stream URLs, EpiScene, SmartTube or customer updater.

Verified 50-fps options remain PTS-measured; unverified sibling candidates can
only be TESTED after explicit consent, ONE AT A TIME, with v187 fallback.
"""
from pathlib import Path
import os
import shutil

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
app = root / "app"
ui = app / "src/main/java/de/epimediahub/app/ui"
vm = app / "src/main/java/de/epimediahub/app/MainViewModel.kt"
player = ui / "PlayerScreen.kt"
dialog = ui / "V187SportModeOffer.kt"
gradle = app / "build.gradle.kts"
tests = app / "src/test/java/de/epimediahub/app/ui"

def once(path: Path, old: str, new: str):
    original = path.read_text(encoding="utf-8")
    n = original.count(old)
    if n != 1:
        raise SystemExit(f"STOP_V193_SOURCE_DRIFT {path.name}: count={n}, anchor={old[:105]!r}")
    path.write_text(original.replace(old, new, 1), encoding="utf-8")

once(gradle, "versionCode = 1092", "versionCode = 1093")
once(gradle, 'versionName = "1.0.92"', 'versionName = "1.0.93"')
shutil.copy2(here / "V193SportOptions.kt", ui / "V193SportOptions.kt")
tests.mkdir(parents=True, exist_ok=True)
shutil.copy2(here / "V193SportOptionsTest.kt", tests / "V193SportOptionsTest.kt")

# v191 inadvertently threw away provided same-category alternatives and returned
# just the selected item until an asynchronous index became ready. Warm-cache
# entry could avoid index scheduling altogether. Use cached catalogue rows to
# schedule on demand, and always retain provided alternatives immediately.
once(vm,
'''        // Until the asynchronous lookup is ready, stay responsive and do NOT
        // recompute the whole cached catalogue on the UI/remote focus thread.
        if (v191SportIndexKey != catalogueKey(profile, MediaKind.LIVE))
            return listOf(item)
        return v191SportIndex?.groupFor(item) ?: listOf(item)''',
'''        // A warm-cache return may skip loadCategories(), so make the index
        // self-healing without flattening the catalogue on the UI thread.
        val key = catalogueKey(profile, MediaKind.LIVE)
        val current = _ui.value
        val rows = current.catalogRows.takeIf {
            current.contentFilterKind == MediaKind.LIVE &&
                it.isNotEmpty()
        } ?: libraryCatalogCache[key]?.rows
        if (rows != null &&
            (v191SportIndexKey != key || v191SportIndexRows !== rows))
            v191ScheduleSportIndex(profile.id, key, rows)
        val local = provided.filter {
            it.kind == MediaKind.LIVE && it.id.isNotBlank() &&
                it.sourceProfileId.ifBlank { profile.id } == profile.id
        }
        val indexed = if (v191SportIndexKey == key)
            v191SportIndex?.groupFor(item).orEmpty() else emptyList()
        // Local entries are available immediately; cross-category entries
        // arrive through v191SportsRevision once async indexing completes.
        return (listOf(item) + indexed + local).distinctBy { it.id }''')

# Keep the v187 explicit-consent state machine, but make it possible to
# offer an unmeasured SAME-station variant for sequential verification.
once(vm,
'''        de.epimediahub.app.ui.V188VerifiedFps.initialize(getApplication<Application>())
        val candidates = v188AllLiveCandidates(item, provided)
        return de.epimediahub.app.ui.V188SportMode.verifiedAlternatives(
            item, candidates, profile,
            de.epimediahub.app.ui.V188VerifiedFps::rememberedRate
        ).isNotEmpty()''',
'''        return v193SportOfferTier(item, provided) !=
            de.epimediahub.app.ui.V193SportOptions.Tier.NONE''')

once(vm,
'''    fun v187SportDecline(item: MediaEntry) {''',
'''    fun v193SportOfferTier(
        item: MediaEntry, provided: List<MediaEntry>
    ): de.epimediahub.app.ui.V193SportOptions.Tier {
        if (item.kind != MediaKind.LIVE) return de.epimediahub.app.ui.V193SportOptions.Tier.NONE
        val profile = item.sourceProfileId.ifBlank { _ui.value.active?.id.orEmpty() }
        de.epimediahub.app.ui.V188VerifiedFps.initialize(getApplication<Application>())
        return de.epimediahub.app.ui.V193SportOptions.tier(
            item, v188AllLiveCandidates(item, provided), profile,
            de.epimediahub.app.ui.V188VerifiedFps::rememberedRate
        )
    }

    fun v187SportDecline(item: MediaEntry) {''')

once(vm,
'''        val candidates = de.epimediahub.app.ui.V188SportMode.verifiedAlternatives(
            item, category, profile,
            de.epimediahub.app.ui.V188VerifiedFps::rememberedRate
        )''',
'''        val candidates = de.epimediahub.app.ui.V193SportOptions.candidates(
            item, category, profile,
            de.epimediahub.app.ui.V188VerifiedFps::rememberedRate
        )''')

# A 25-fps observation can arrive before the async index: re-check its offer
# when v191SportsRevision changes. It never opens a second stream and neither
# guesses current PTS nor forces a background channel switch.
once(player,
'''    if (v187SportOffer) V187SportModeOffer(
        onYes = {''',
'''    LaunchedEffect(item.resumeKey, v185MeasuredFps, u.v191SportsRevision) {
        if (item.kind == MediaKind.LIVE && v185MeasuredFps == 25 &&
            !v187SportOffer && vm.v187SportOfferAvailable(item, episodeList)) {
            val currentEpg = de.epimediahub.app.data.V163Epg.current(
                u.epg[item.id].orEmpty(), System.currentTimeMillis() / 1000L)
            val categoryName = u.categories.firstOrNull {
                it.id == item.categoryId
            }?.name.orEmpty()
            if (V193SportOptions.automaticOfferAllowed(
                    item.name, categoryName, currentEpg?.title.orEmpty(),
                    currentEpg?.description.orEmpty(), v185MeasuredFps,
                    vm.v193SportOfferTier(item, episodeList)
                )) v187SportOffer = true
        }
    }
    if (v187SportOffer) V187SportModeOffer(
        verified = vm.v193SportOfferTier(item, episodeList) ==
            V193SportOptions.Tier.VERIFIED_50,
        onYes = {''')

# The existing fast-path offer while observing PTS uses the same explicit
# candidate tier check as the catalogue-ready effect above.
once(player,
'''                        if (V188SportContext.automaticOfferAllowed(
                                item.name, categoryName,
                                currentEpg?.title.orEmpty(),
                                currentEpg?.description.orEmpty(),
                                candidate, true
                            )) {''',
'''                        if (V193SportOptions.automaticOfferAllowed(
                                item.name, categoryName,
                                currentEpg?.title.orEmpty(),
                                currentEpg?.description.orEmpty(),
                                candidate, vm.v193SportOfferTier(item, episodeList)
                            )) {''')

# The existing dark dialog must not claim "50 fps available" on an unverified
# candidate. It explains opt-in sequential checking and safe restoration.
once(dialog,
'''internal fun V187SportModeOffer(onYes: () -> Unit, onNo: () -> Unit) {''',
'''internal fun V187SportModeOffer(
    onYes: () -> Unit, onNo: () -> Unit, verified: Boolean = true
) {''')
once(dialog,
'''                    "50 fps verfügbar",''',
'''                    if (verified) "50 fps verfügbar"
                    else "Sportvariante gefunden",''')
once(dialog,
'''                    "Dieser Sender wird mit 25 fps wiedergegeben. " +
                        "Eine flüssigere 50-fps-Variante wurde bereits erkannt – " +
                        "auch über andere Kategorien hinweg. Möchtest du wechseln?",''',
'''                    if (verified)
                        "Dieser Sender wird mit 25 fps wiedergegeben. " +
                        "Eine flüssigere 50-fps-Variante wurde bereits erkannt – " +
                        "auch über andere Kategorien hinweg. Möchtest du wechseln?"
                    else
                        "Dieser Sender läuft gemessen mit 25 fps. Eine passende " +
                        "Sender-Alternative ist vorhanden, ihre Bildrate aber noch " +
                        "nicht bestätigt. Soll die App sie einzeln testen? " +
                        "Bei 25 fps, Fehlern oder Zeitüberschreitung kehrt sie " +
                        "zum ursprünglichen Sender zurück.",''')
once(dialog,
'''                        Text("Ja · 50 fps nutzen")''',
'''                        Text(if (verified) "Ja · 50 fps nutzen"
                             else "Ja · Varianten testen")''')

# IPTV providers sometimes call Bundesliga "DB LIGA". Keep EPG-driven
# documentary/news suppression, but recognize this specific sports-station
# alias even without EPG metadata.
sports_context = ui / "V188SportContext.kt"
once(sports_context, r'dazn|eurosport|sportitalia|sport1|',
    r'dazn|db\s*liga|eurosport|sportitalia|sport1|')

# Do not touch the tested v192 HDMI code. Fail closed if the bridge vanished.
assert 'V192LiveModeHold.request(view.context.activity(), view, fps)' in (
    ui / "V121VodSurface.kt").read_text(encoding="utf-8")
assert 'V193SportOptions.candidates(' in vm.read_text(encoding="utf-8")
assert 'v191SportsRevision' in player.read_text(encoding="utf-8")
assert 'v187SportCandidateFailed(item)' in player.read_text(encoding="utf-8")
assert 'V188VerifiedFps.verifiedCandidate(' in player.read_text(encoding="utf-8")
assert 'V193SportOptions.automaticOfferAllowed(' in player.read_text(encoding="utf-8")
print("V193_SPORT_INDEX_CACHE_READY_RECHECK_AND_LOCAL_CANDIDATES_APPLIED")
print("V193_VERIFIED_VS_UNKNOWN_SEQUENTIAL_OPT_IN_TEST_WITH_RESTORE_APPLIED")
print("V193_V192_LIVE_HDMI_UNCHANGED_NO_PARALLEL_IPTV_NO_UPDATER_CHANGES")
