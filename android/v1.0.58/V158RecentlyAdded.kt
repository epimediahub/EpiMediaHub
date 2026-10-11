package de.epimediahub.app.data

import de.epimediahub.app.model.MediaEntry

/**
 * Only provider timestamps justify the label "Zuletzt hinzugefügt".
 * The provider's native list order is not guaranteed to be chronological.
 * Do not populate this category with arbitrary old entries on missing dates.
 */
internal object V158RecentlyAdded {
    fun select(all: List<MediaEntry>, limit: Int = 36): List<MediaEntry> {
        if (limit <= 0) return emptyList()
        return all.asSequence()
            .filter { it.addedAt > 0L }
            .distinctBy { it.resumeKey }
            .sortedByDescending { it.addedAt }
            .take(limit)
            .toList()
    }
}
