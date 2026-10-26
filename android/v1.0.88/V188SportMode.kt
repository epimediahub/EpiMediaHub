package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

/**
 * The opt-in sport offer is allowed ONLY when at least one trusted PTS-verified
 * 50 fps alternate exists, even if it lives in another cached category.
 *
 * Reuses v187's ranker for quality/identity but never includes filename-only
 * 50 FPS labels or unknown streams. Old rates from v185-v187 are ignored.
 */
internal object V188SportMode {
    fun verifiedAlternatives(
        selected: MediaEntry, all: List<MediaEntry>, activeProfileId: String,
        measured: (profile: String, category: String, streamId: String) -> Int
    ): List<MediaEntry> {
        if (selected.kind != MediaKind.LIVE || all.size < 2) return emptyList()
        fun profile(item: MediaEntry): String =
            item.sourceProfileId.ifBlank { activeProfileId }
        val idx = all.indexOfFirst {
            it.id == selected.id && profile(it) == profile(selected)
        }
        if (idx < 0) return emptyList()
        val variants = all.map { item ->
            val provider = profile(item)
            V187SportMode.Candidate(item.id, item.name, provider,
                measured(provider, item.categoryId, item.id))
        }
        return V187SportMode.rankedIndices(idx, variants)
            .filter { variants[it].measuredFps == 50 }
            .mapNotNull(all::getOrNull)
    }
}
