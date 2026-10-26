package de.epimediahub.app.ui

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

/**
 * Sportmodus is strictly opt-in. Keep the selected stream playing unchanged
 * until a measured 25 fps and the user's explicit confirmation.
 *
 * Candidate discovery reads ONLY cached category entries and FPS facts from
 * normal playback. A failed candidate is abandoned before opening the next.
 */
internal object V187SportMode {
    data class Candidate(
        val id: String,
        val name: String,
        val profile: String,
        val measuredFps: Int = 0
    )

    private val uhd = Regex("""(?i)(?<!\w)(?:4K|UHD|2160P)(?!\w)""")
    private val fullHd = Regex("""(?i)(?<!\w)(?:FHD|FULL[\s-]*HD|1080P)(?!\w)""")
    private val hdPlus = Regex("""(?i)(?<!\w)HD\s*\+(?!\w)""")
    private val hd = Regex("""(?i)(?<!\w)(?:HD|720P)(?!\w)""")
    private val sd = Regex("""(?i)(?<!\w)SD(?!\w)""")

    private fun quality(name: String): Int = when {
        uhd.containsMatchIn(name) -> 6
        fullHd.containsMatchIn(name) -> 5
        hdPlus.containsMatchIn(name) -> 4
        hd.containsMatchIn(name) -> 3
        sd.containsMatchIn(name) -> 1
        else -> 2
    }

    private fun fps(v: Candidate) =
        v.measuredFps.takeIf { it == 25 || it == 50 } ?: V186SportPriority.advertisedFps(v.name)

    /** Known 50 first, then unknown variants to inspect sequentially; skip measured 25. */
    fun rankedIndices(selected: Int, variants: List<Candidate>): List<Int> {
        if (selected !in variants.indices) return emptyList()
        val current = variants[selected]
        if (current.id.isBlank() || current.profile.isBlank()) return emptyList()
        val station = V188WorldwideSportChannels.canonicalSportIdentity(current.name)
        if (station.length < 3) return emptyList()
        return variants.withIndex()
            .filter { (index, v) ->
                index != selected && v.id.isNotBlank() &&
                    v.profile == current.profile &&
                    V188WorldwideSportChannels.canonicalSportIdentity(v.name) == station &&
                    fps(v) != 25
            }
            .sortedWith(
                compareByDescending<IndexedValue<Candidate>> {
                    when {
                        it.value.measuredFps == 50 -> 3
                        fps(it.value) == 50 -> 2
                        else -> 1
                    }
                }.thenByDescending { quality(it.value.name) }
                    .thenBy { it.index }
            )
            .map { it.index }
    }

    fun alternatives(
        current: MediaEntry, all: List<MediaEntry>,
        activeProfileId: String, rememberedRate: (String, String) -> Int
    ): List<MediaEntry> {
        if (current.kind != MediaKind.LIVE || all.size < 2) return emptyList()
        fun profile(entry: MediaEntry) = entry.sourceProfileId.ifBlank { activeProfileId }
        val currentIndex = all.indexOfFirst {
            it.id == current.id && profile(it) == profile(current)
        }
        if (currentIndex < 0) return emptyList()
        val variants = all.map { media ->
            val resolved = profile(media)
            Candidate(media.id, media.name, resolved, rememberedRate(resolved, media.id))
        }
        return rankedIndices(currentIndex, variants).mapNotNull(all::getOrNull)
    }

    /** Never automatically retry indefinitely or jump between unrelated streams. */
    fun nextIndex(failedAt: Int, count: Int): Int? =
        (failedAt + 1).takeIf { it in 0 until count }
}

/** Suppresses a declined offer for the remainder of the app process. */
internal object V187SportPromptMemory {
    private val declined = mutableSetOf<String>()
    private fun key(profile: String, id: String) =
        profile.length.toString() + ":" + profile + "|" + id
    fun decline(profile: String, id: String) {
        if (profile.isNotBlank() && id.isNotBlank()) declined.add(key(profile, id))
    }
    fun wasDeclined(profile: String, id: String): Boolean =
        profile.isNotBlank() && id.isNotBlank() && key(profile, id) in declined
}
