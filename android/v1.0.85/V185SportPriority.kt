package de.epimediahub.app.ui

import android.content.Context
import android.content.SharedPreferences
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import java.util.Locale

/**
 * Never opens or probes an IPTV stream. Prefer only an unambiguous 50-fps
 * variant of the same named channel inside the SAME provider profile.
 * Facts measured during normal playback override labels. A user can still
 * explicitly select any version from the live channel list.
 */
internal object V185SportPriority {
    internal data class Variant(
        val id: String,
        val name: String,
        val profile: String,
        val measuredFps: Int = 0
    )

    private val fpsToken = Regex("""(?i)(?<!\w)(?:25|50|60)\s*(?:FPS)(?!\w)""")
    private val qualityToken = Regex("""(?i)(?<!\w)(?:4K|UHD|FHD|FULL\s*HD|HD|SD|1080P|720P|2160P)(?!\w)""")
    private val whitespace = Regex("""\s+""")
    private val nonWord = Regex("""[^\p{L}\p{N}]+""")
    private val labelRate = Regex("""(?i)(?<!\d)(25|50|60)\s*FPS(?!\w)""")

    @Volatile private var store: SharedPreferences? = null

    fun initialize(context: Context) {
        if (store == null) synchronized(this) {
            if (store == null) store = context.applicationContext
                .getSharedPreferences("epimediahub_live_fps_v185", Context.MODE_PRIVATE)
        }
    }

    private fun key(profile: String, id: String): String =
        "rate_" + profile.length + "_" + profile + "_" + id

    fun rememberedRate(profile: String, id: String): Int =
        if (profile.isBlank() || id.isBlank()) 0 else
            store?.getInt(key(profile, id), 0) ?: 0

    fun recordMeasured(context: Context, item: MediaEntry, fps: Int) {
        if (item.kind != MediaKind.LIVE || fps !in listOf(25, 50) ||
            item.sourceProfileId.isBlank() || item.id.isBlank()) return
        initialize(context)
        val storageKey = key(item.sourceProfileId, item.id)
        if (store?.getInt(storageKey, 0) != fps) store?.edit()?.putInt(storageKey, fps)?.apply()
    }

    fun classify(fps: Float): Int = when {
        fps in 24.8f..25.2f -> 25
        fps in 49.7f..50.3f -> 50
        else -> 0
    }

    internal fun advertisedFps(name: String): Int =
        labelRate.find(name)?.groupValues?.get(1)?.toIntOrNull() ?: 0

    internal fun canonical(name: String): String =
        whitespace.replace(
            nonWord.replace(
                qualityToken.replace(fpsToken.replace(name.uppercase(Locale.ROOT), " "), " "), " "
            ).trim(), " "
        ).trim()

    /**
     * Highest observed FPS wins. If no measurement exists, a literal "50 FPS"
     * label is usable but remains unverified. Never redirect across providers.
     * Never resolve ambiguous ties to an arbitrary alternate channel.
     */
    internal fun bestIndex(selected: Int, variants: List<Variant>): Int {
        if (selected !in variants.indices) return selected
        val current = variants[selected]
        if (current.profile.isBlank() || current.id.isBlank()) return selected
        val channel = canonical(current.name)
        if (channel.length < 3) return selected
        fun rate(variant: Variant): Int =
            variant.measuredFps.takeIf { it == 25 || it == 50 }
                ?: advertisedFps(variant.name)

        val originalRate = rate(current)
        val alternatives = variants.withIndex().filter { (_, other) ->
            other.id.isNotBlank() && other.profile == current.profile &&
                canonical(other.name) == channel && other.id != current.id &&
                rate(other) == 50
        }
        if (originalRate >= 50 || alternatives.size != 1) return selected
        return alternatives.single().index
    }

    fun preferred(current: MediaEntry, channelList: List<MediaEntry>): MediaEntry {
        if (current.kind != MediaKind.LIVE || channelList.size < 2) return current
        val variants = channelList.map {
            Variant(it.id, it.name, it.sourceProfileId,
                rememberedRate(it.sourceProfileId, it.id))
        }
        val originalIndex = channelList.indexOfFirst {
            it.id == current.id && it.sourceProfileId == current.sourceProfileId
        }
        val chosen = bestIndex(originalIndex, variants)
        return channelList.getOrNull(chosen) ?: current
    }

    fun recommendedAlternative(current: MediaEntry, list: List<MediaEntry>): MediaEntry? =
        preferred(current, list).takeUnless { it.id == current.id &&
            it.sourceProfileId == current.sourceProfileId }
}
