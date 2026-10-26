package de.epimediahub.app.data

import de.epimediahub.app.model.MediaEntry

/**
 * The provider's "added" metadata is authoritative when supplied.
 * A small number of Xtream providers omit timestamps for series or films;
 * then retain their native catalogue order rather than hiding the entire
 * "Zuletzt hinzugefügt" section.
 */
internal object V157RecentlyAdded {
    fun select(all: List<MediaEntry>, limit: Int = 36): List<MediaEntry> {
        if (limit <= 0) return emptyList()
        val dated = all.filter { it.addedAt > 0L }
        return if (dated.isNotEmpty()) dated.sortedByDescending { it.addedAt }.take(limit)
        else all.take(limit)
    }
}
