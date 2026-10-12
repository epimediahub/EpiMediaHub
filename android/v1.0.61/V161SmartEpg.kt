package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import java.util.Locale

/** Reuses EPG information within one playlist, without extra HTTP requests. */
internal object V161SmartEpg {
    private val pictureTags = setOf(
        "SD", "HD", "FHD", "UHD", "4K", "8K", "HEVC", "H264", "H265",
        "AVC", "1080P", "720P", "2160P", "50FPS", "60FPS"
    )

    fun stationKey(name: String): String = Regex("[\\p{L}\\p{N}]+")
        .findAll(name.uppercase(Locale.ROOT))
        .map { it.value }
        .filterNot { it in pictureTags }
        .joinToString(" ")
        .trim()

    fun enrich(
        channels: List<MediaEntry>,
        guides: Map<String, List<EpgItem>>
    ): Map<String, List<EpgItem>> {
        if (guides.isEmpty()) return guides
        val result = guides.toMutableMap()
        val grouped = channels.asSequence().filter { it.kind == MediaKind.LIVE }
            .distinctBy { it.id }.groupBy { stationKey(it.name) }
        grouped.forEach { (key, members) ->
            if (key.isBlank() || members.size < 2) return@forEach
            val explicitIds = members.map { it.epgId.trim().lowercase(Locale.ROOT) }
                .filter { it.isNotBlank() }.toSet()
            if (explicitIds.size > 1) return@forEach
            val sources = members.mapNotNull { member ->
                guides[member.id]?.takeIf { it.isNotEmpty() }
            }
            if (sources.isEmpty()) return@forEach
            val fingerprints = sources.map { epg ->
                epg.take(2).map { event ->
                    event.start.toString() + ":" + event.end + ":" +
                        event.title.trim().lowercase(Locale.ROOT)
                }
            }.distinct()
            if (fingerprints.size != 1) return@forEach
            val guide = sources.first()
            members.forEach { member ->
                if (result[member.id].isNullOrEmpty()) result[member.id] = guide
            }
        }
        return result
    }
}
