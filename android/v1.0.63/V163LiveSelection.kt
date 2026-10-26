package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

internal data class V163LiveSelection(val categoryId: String, val index: Int) {
    companion object {
        fun resolve(item: MediaEntry, preferred: String, rows: Map<String, List<MediaEntry>>,
                    fallback: List<MediaEntry>): V163LiveSelection {
            fun position(channels: List<MediaEntry>) = channels.indexOfFirst {
                it.kind == MediaKind.LIVE && it.id == item.id &&
                    (it.sourceProfileId.isBlank() || item.sourceProfileId.isBlank() ||
                        it.sourceProfileId == item.sourceProfileId)
            }
            val preferredIndex = position(rows[preferred].orEmpty())
            if (preferred.isNotBlank() && preferredIndex >= 0) return V163LiveSelection(preferred, preferredIndex)
            val actualIndex = position(rows[item.categoryId].orEmpty())
            return V163LiveSelection(item.categoryId,
                if (actualIndex >= 0) actualIndex else position(fallback).coerceAtLeast(0))
        }
    }
}
