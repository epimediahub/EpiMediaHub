package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

/**
 * A possible 50-fps variant is not a verified 50-fps stream.
 *
 * Inventory is strictly the currently cached catalogue plus the active
 * category, never remote probes. A user may explicitly test unknown siblings
 * ONE AT A TIME; the retained v187 state machine verifies observed PTS,
 * advances on 25-fps/error/timeout and restores the original on exhaustion.
 */
object V193SportOptions {
    enum class Tier { NONE, UNVERIFIED, VERIFIED_50 }

    private data class Rated(val item: MediaEntry, val rate: Int)

    private fun ranked(
        current: MediaEntry,
        all: List<MediaEntry>,
        activeProfileId: String,
        measured: (profile: String, category: String, streamId: String) -> Int
    ): List<Rated> {
        if (current.kind != MediaKind.LIVE || all.size < 2) return emptyList()
        fun profile(entry: MediaEntry) = entry.sourceProfileId.ifBlank { activeProfileId }
        val selectedProfile = profile(current)
        if (selectedProfile.isBlank()) return emptyList()
        // The index may contain catalogue rows for multiple categories;
        // nothing may spill into another playlist or media kind.
        val candidates = (listOf(current) + all)
            .filter {
                it.kind == MediaKind.LIVE && it.id.isNotBlank() &&
                    profile(it) == selectedProfile
            }
            .distinctBy { it.id }
        val selectedIndex = candidates.indexOfFirst { it.id == current.id }
        if (selectedIndex < 0 || candidates.size < 2) return emptyList()
        val rated = candidates.map { item ->
            Rated(item, measured(profile(item), item.categoryId, item.id))
        }
        val pool = rated.map { ratedItem ->
            V187SportMode.Candidate(
                ratedItem.item.id, ratedItem.item.name,
                profile(ratedItem.item), ratedItem.rate
            )
        }
        // Canonical sport identity and provider checks live in this ranker.
        return V187SportMode.rankedIndices(selectedIndex, pool)
            .mapNotNull(rated::getOrNull)
            .filter { it.rate == 50 || it.rate == 0 }
    }

    fun candidates(
        current: MediaEntry,
        all: List<MediaEntry>,
        activeProfileId: String,
        measured: (profile: String, category: String, streamId: String) -> Int
    ): List<MediaEntry> =
        ranked(current, all, activeProfileId, measured).map { it.item }

    fun tier(
        current: MediaEntry,
        all: List<MediaEntry>,
        activeProfileId: String,
        measured: (profile: String, category: String, streamId: String) -> Int
    ): Tier {
        val candidates = ranked(current, all, activeProfileId, measured)
        return when {
            candidates.any { it.rate == 50 } -> Tier.VERIFIED_50
            candidates.isNotEmpty() -> Tier.UNVERIFIED
            else -> Tier.NONE
        }
    }

    /** The automatic prompt still requires an actual PTS-verified 25 fps. */
    fun automaticOfferAllowed(
        name: String, category: String, epgTitle: String, epgDescription: String,
        confirmedCurrentFps: Int, tier: Tier
    ): Boolean = confirmedCurrentFps == 25 && tier != Tier.NONE &&
        V188SportContext.confidence(name, category, epgTitle, epgDescription) !=
            V188SportContext.Confidence.NONE
}
