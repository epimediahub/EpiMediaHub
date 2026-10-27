package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

/**
 * Build on Dispatchers.Default when the full Live catalogue is loaded.
 * Browsing and Compose rendering only perform hash-map lookups. No IPTV
 * streams or network requests are opened to inspect frame rates.
 */
internal class V191SportIndex private constructor(
    private val profileId: String,
    private val groups: Map<String, List<MediaEntry>>
) {
    fun groupFor(item: MediaEntry): List<MediaEntry> {
        if (item.kind != MediaKind.LIVE ||
            item.sourceProfileId.isNotBlank() && item.sourceProfileId != profileId)
            return listOf(item)
        val identity = V188WorldwideSportChannels.canonicalSportIdentity(item.name)
        return groups[identity]?.takeIf { candidates ->
            candidates.any { it.id == item.id }
        } ?: listOf(item)
    }

    companion object {
        fun build(profileId: String, rows: Map<String, List<MediaEntry>>): V191SportIndex {
            val unique = HashSet<String>()
            val grouped = HashMap<String, MutableList<MediaEntry>>()
            for (channels in rows.values) for (channel in channels) {
                if (channel.kind != MediaKind.LIVE || channel.id.isBlank() ||
                    channel.sourceProfileId.isNotBlank() &&
                    channel.sourceProfileId != profileId ||
                    !unique.add(channel.id) ||
                    V191LiveHeaders.isNonPlayableName(channel.name)) continue
                val identity = V188WorldwideSportChannels.canonicalSportIdentity(channel.name)
                if (identity.length < 3) continue
                grouped.getOrPut(identity) { ArrayList(2) }.add(channel)
            }
            return V191SportIndex(profileId, grouped)
        }
    }
}
