package de.epimediahub.app.ui

import android.content.Context
import android.content.SharedPreferences
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import java.util.Locale

/**
 * Choose a verified 50-fps variant of the SAME channel in the SAME provider.
 *
 * Uses metadata already present in the live category; never opens a second
 * IPTV connection or probes another stream. Playback measurements are saved
 * only for channels the viewer actually watches. Names containing different
 * station numbers, languages and regions must never be conflated.
 */
internal object V186SportPriority {
    internal data class Variant(
        val id: String,
        val name: String,
        val profile: String,
        val measuredFps: Int = 0
    )

    private val fpsToken = Regex("""(?i)(?<!\w)(?:25|50|60)\s*FPS(?!\w)""")
    private val qualityToken = Regex("""(?i)(?<!\w)(?:4K|UHD|FHD|FULL\s*HD|HD|SD|1080P|720P|2160P)(?!\w)""")
    private val deliveryToken = Regex("""(?i)(?<!\w)(?:WEB|HEVC|H\.?265|H\.?264|AVC|BAHEVC|BHAEVC)(?!\w)""")
    private val whitespace = Regex("""\s+""")
    private val nonWord = Regex("""[^\p{L}\p{N}]+""")
    private val labelRate = Regex("""(?i)(?<!\d)(25|50|60)\s*FPS(?!\w)""")
    private val uhd = Regex("""(?i)(?<!\w)(?:4K|UHD|2160P)(?!\w)""")
    private val fhd = Regex("""(?i)(?<!\w)(?:FHD|FULL\s*HD|1080P)(?!\w)""")
    private val hdPlus = Regex("""(?i)(?<!\w)HD\s*\+(?!\w)""")
    private val hd = Regex("""(?i)(?<!\w)(?:HD|720P)(?!\w)""")
    private val sd = Regex("""(?i)(?<!\w)SD(?!\w)""")

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
        if (profile.isBlank() || id.isBlank()) 0
        else store?.getInt(key(profile, id), 0) ?: 0

    fun recordMeasured(context: Context, item: MediaEntry, fps: Int, activeProfileId: String = "") {
        val profile = item.sourceProfileId.ifBlank { activeProfileId }
        if (item.kind != MediaKind.LIVE || fps !in listOf(25, 50) ||
            profile.isBlank() || item.id.isBlank()) return
        initialize(context)
        val storageKey = key(profile, item.id)
        if (store?.getInt(storageKey, 0) != fps)
            store?.edit()?.putInt(storageKey, fps)?.apply()
    }

    fun classify(fps: Float): Int = when {
        fps in 24.8f..25.2f -> 25
        fps in 49.7f..50.3f -> 50
        else -> 0
    }

    /**
     * PTS cadence is strongest evidence. If PTS is unavailable (often
     * interlaced broadcasts), fallback to the player's stable format rate.
     * Three consecutive 2-second samples and at least 90 decoded frames are
     * required by the caller before the result is persisted.
     */
    internal fun observedRate(measured: Float, format: Float, decoderFormat: Float): Int {
        val pts = classify(measured)
        if (pts != 0) return pts
        val reported = classify(format)
        if (reported != 0) return reported
        return classify(decoderFormat)
    }

    internal fun advertisedFps(name: String): Int =
        labelRate.find(name)?.groupValues?.get(1)?.toIntOrNull() ?: 0

    internal fun canonical(name: String): String =
        whitespace.replace(
            nonWord.replace(
                deliveryToken.replace(
                    qualityToken.replace(fpsToken.replace(name.uppercase(Locale.ROOT), " "), " "), " "
                ), " "
            ).trim(), " "
        ).trim()

    private fun quality(name: String): Int = when {
        uhd.containsMatchIn(name) -> 6
        fhd.containsMatchIn(name) -> 5
        hdPlus.containsMatchIn(name) -> 4
        hd.containsMatchIn(name) -> 3
        sd.containsMatchIn(name) -> 1
        else -> 2
    }

    /**
     * Previous version refused to switch when there were TWO or more 50-fps
     * siblings. Pick deterministically: first observed > name-only 50 fps,
     * then 4K > Full HD > HD+, HD etc, then stable category ordering.
     */
    internal fun bestIndex(selected: Int, variants: List<Variant>): Int {
        if (selected !in variants.indices) return selected
        val current = variants[selected]
        if (current.profile.isBlank() || current.id.isBlank()) return selected
        val channel = canonical(current.name)
        if (channel.length < 3) return selected
        fun rate(v: Variant): Int =
            v.measuredFps.takeIf { it == 25 || it == 50 } ?: advertisedFps(v.name)

        if (rate(current) == 50) return selected

        val valid = variants.withIndex().filter { (_, v) ->
            v.id.isNotBlank() && v.id != current.id &&
                v.profile == current.profile &&
                canonical(v.name) == channel && rate(v) == 50
        }
        if (valid.isEmpty()) return selected

        // Explicit comparator keeps the first existing channel on exact ties.
        val chosen = valid.maxWithOrNull(compareBy<IndexedValue<Variant>>(
            { if (it.value.measuredFps == 50) 1 else 0 },
            { quality(it.value.name) },
            { -it.index }
        )) ?: return selected
        return chosen.index
    }

    fun preferred(current: MediaEntry, channelList: List<MediaEntry>, activeProfileId: String = ""): MediaEntry {
        if (current.kind != MediaKind.LIVE || channelList.size < 2) return current
        fun profile(item: MediaEntry): String =
            item.sourceProfileId.ifBlank { activeProfileId }
        initializeIfAlreadyUsed()
        val variants = channelList.map {
            val resolved = profile(it)
            Variant(it.id, it.name, resolved, rememberedRate(resolved, it.id))
        }
        val original = channelList.indexOfFirst {
            it.id == current.id && profile(it) == profile(current)
        }
        val chosen = bestIndex(original, variants)
        return channelList.getOrNull(chosen) ?: current
    }

    // initialize() runs at player startup; no Context reference is held here.
    private fun initializeIfAlreadyUsed() = Unit

    fun recommendedAlternative(current: MediaEntry, list: List<MediaEntry>, activeProfileId: String = ""): MediaEntry? =
        preferred(current, list, activeProfileId).takeUnless {
            it.id == current.id &&
                it.sourceProfileId.ifBlank { activeProfileId } ==
                current.sourceProfileId.ifBlank { activeProfileId }
        }
}
