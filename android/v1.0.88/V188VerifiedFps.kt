package de.epimediahub.app.ui

import android.content.Context
import android.content.SharedPreferences
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

/**
 * Stores verified PTS cadence, not TV refresh rate nor video-format metadata.
 *
 * Keep category identity alongside profile and channel ID so a German/Italian
 * provider's different category versions are remembered independently.
 * v187's earlier fallback cache is deliberately NOT migrated: its "50 fps"
 * could come only from the stream's reported format without PTS verification.
 */
internal object V188VerifiedFps {
    @Volatile private var store: SharedPreferences? = null

    fun initialize(context: Context) {
        if (store == null) synchronized(this) {
            if (store == null) store = context.applicationContext
                .getSharedPreferences("epimediahub_pts_verified_fps_v188", Context.MODE_PRIVATE)
        }
    }

    private fun key(profile: String, category: String, id: String) =
        profile.length.toString() + ":" + profile + "|" +
        category.length + ":" + category + "|" + id

    fun rememberedRate(profile: String, category: String, id: String): Int {
        if (profile.isBlank() || id.isBlank()) return 0
        return store?.getInt(key(profile, category, id), 0) ?: 0
    }

    fun recordVerified(
        context: Context, item: MediaEntry, ptsRate: Int, activeProfileId: String = ""
    ) {
        val profile = item.sourceProfileId.ifBlank { activeProfileId }
        if (item.kind != MediaKind.LIVE || ptsRate !in listOf(25, 50) ||
            item.id.isBlank() || profile.isBlank()) return
        initialize(context)
        val lookup = key(profile, item.categoryId, item.id)
        if (store?.getInt(lookup, 0) != ptsRate)
            store?.edit()?.putInt(lookup, ptsRate)?.apply()
    }

    /** Only a PTS measurement proves 25/50 distinct temporal frames. */
    fun verifiedCandidate(ptsFps: Float, isPlaying: Boolean, rendered: Int): Int {
        if (!isPlaying || rendered < 90) return 0
        return V186SportPriority.classify(ptsFps)
    }

    /** Never substitute displayHz or reported metadata for a PTS-based rate. */
    fun diagnosticLabel(verified: Int, decoderReported: Int): String = when (verified) {
        50 -> "50 fps · Gemessen"
        25 -> "25 fps · Gemessen"
        else -> when (decoderReported) {
            50 -> "50 fps · Vom Stream gemeldet, noch nicht bestätigt"
            25 -> "25 fps · Vom Stream gemeldet, noch nicht bestätigt"
            else -> "Bildrate wird gemessen"
        }
    }
}
