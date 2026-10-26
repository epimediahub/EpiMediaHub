package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

/**
 * Cross-category SPORT candidate inventory from ALREADY CACHED catalogue rows.
 * No background stream scans or additional provider connections.
 * Never exposes another provider or another content type.
 */
internal object V188SportCatalog {
    fun samePlaylist(
        selected: MediaEntry,
        provided: List<MediaEntry>,
        rows: Map<String, List<MediaEntry>>,
        activeProfileId: String
    ): List<MediaEntry> {
        if (selected.kind != MediaKind.LIVE) return provided
        val profile = selected.sourceProfileId.ifBlank { activeProfileId }
        if (profile.isBlank()) return provided
        fun matches(item: MediaEntry): Boolean =
            item.kind == MediaKind.LIVE &&
                item.sourceProfileId.ifBlank { activeProfileId } == profile &&
                item.id.isNotBlank()
        // Exactly one entry per provider+stream ID. An __all__ category may
        // repeat the same item in every category; do not try it repeatedly.
        val full = (listOf(selected) + rows.values.flatten() + provided)
            .filter(::matches)
            .distinctBy { it.id }
        return full.ifEmpty { provided }
    }
}
