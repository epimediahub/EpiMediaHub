package de.epimediahub.app.ui

import android.content.Context
import com.liskovsoft.mediaserviceinterfaces.data.MediaGroup
import com.liskovsoft.mediaserviceinterfaces.data.MediaItem
import com.liskovsoft.sharedutils.prefs.GlobalPreferences
import com.liskovsoft.youtubeapi.service.YouTubeServiceManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

internal data class V100SmartTubeVideo(
    val videoId: String,
    val title: String,
    val author: String,
    val image: String,
    val background: String,
    val durationMs: Long,
    val live: Boolean
)

internal data class V100SmartTubeRow(
    val title: String,
    val videos: List<V100SmartTubeVideo>
)

internal data class V100SmartTubePlayback(
    val url: String,
    val extension: String
)

/**
 * Thin EpiMediaHub adapter around the pinned SmartTube MediaServiceCore.
 *
 * Keeping this bridge small is intentional: EpiMediaHub owns the Compose UI
 * and player chrome while SmartTube's service layer owns YouTube discovery
 * and stream resolution.
 */
internal object V100SmartTubeCore {
    private fun service(context: Context) = run {
        GlobalPreferences.instance(context.applicationContext)
        YouTubeServiceManager.instance()
    }

    suspend fun home(context: Context): Result<List<V100SmartTubeRow>> =
        withContext(Dispatchers.IO) {
            runCatching {
                val groups = service(context).contentService.home
                mapGroups(groups)
            }
        }

    suspend fun search(context: Context, query: String): Result<List<V100SmartTubeRow>> =
        withContext(Dispatchers.IO) {
            runCatching {
                val needle = query.trim()
                if (needle.isBlank()) return@runCatching emptyList()
                mapGroups(service(context).contentService.getSearch(needle))
            }
        }

    suspend fun resolvePlayback(
        context: Context,
        video: V100SmartTubeVideo
    ): Result<V100SmartTubePlayback> = withContext(Dispatchers.IO) {
        runCatching {
            val info = service(context).mediaItemService.getFormatInfo(video.videoId)
            if (info.isUnplayable) {
                error(info.playabilityReason?.takeIf { it.isNotBlank() } ?: "Video ist nicht abspielbar.")
            }

            val progressive = if (info.containsUrlFormats()) {
                info.createUrlList()?.firstOrNull { it.startsWith("http") }
            } else null
            val hls = info.hlsManifestUrl?.takeIf { info.containsHlsUrl() && it.startsWith("http") }
            val dash = info.dashManifestUrl?.takeIf { info.containsDashUrl() && it.startsWith("http") }

            val url = when {
                info.isLive && hls != null -> hls
                progressive != null -> progressive
                hls != null -> hls
                dash != null -> dash
                else -> error(
                    info.playabilityReason?.takeIf { it.isNotBlank() }
                        ?: "SmartTube konnte für dieses Video noch keine kompatible Wiedergabe-URL auflösen."
                )
            }
            V100SmartTubePlayback(url, extensionFor(url))
        }
    }

    private fun mapGroups(groups: List<MediaGroup>?): List<V100SmartTubeRow> =
        groups.orEmpty().mapNotNull { group ->
            val videos = group.mediaItems.orEmpty()
                .mapNotNull(::mapItem)
                .distinctBy { it.videoId }
                .take(30)
            if (videos.isEmpty()) null
            else V100SmartTubeRow(group.title?.takeIf { it.isNotBlank() } ?: "YouTube", videos)
        }.take(20)

    private fun mapItem(item: MediaItem): V100SmartTubeVideo? {
        val id = item.videoId?.trim().orEmpty()
        if (id.isBlank()) return null
        return V100SmartTubeVideo(
            videoId = id,
            title = item.title?.trim().orEmpty().ifBlank { "YouTube" },
            author = item.author?.trim().orEmpty(),
            image = item.cardImageUrl?.trim().orEmpty(),
            background = item.backgroundImageUrl?.trim().orEmpty(),
            durationMs = item.durationMs.coerceAtLeast(0L),
            live = item.isLive
        )
    }

    private fun extensionFor(url: String): String {
        val clean = url.substringBefore('?').lowercase()
        return when {
            clean.endsWith(".m3u8") -> "m3u8"
            clean.endsWith(".mpd") -> "mpd"
            clean.endsWith(".webm") -> "webm"
            else -> "mp4"
        }
    }
}
