package de.epimediahub.app.ui

import android.content.Context
import com.liskovsoft.mediaserviceinterfaces.data.MediaGroup
import com.liskovsoft.mediaserviceinterfaces.data.MediaItem
import com.liskovsoft.sharedutils.prefs.GlobalPreferences
import com.liskovsoft.youtubeapi.service.YouTubeServiceManager
import com.liskovsoft.youtubeapi.service.internal.EpiMediaPlaybackBridge
import io.reactivex.Observable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

internal object V105SmartTubeCore {
    private fun manager(context: Context) = run {
        GlobalPreferences.instance(context.applicationContext)
        YouTubeServiceManager.instance()
    }

    suspend fun authState(context: Context): V104SmartTubeAuthState =
        withContext(Dispatchers.IO) {
            val signIn = manager(context).signInService
            V104SmartTubeAuthState(
                signed = signIn.isSigned,
                accountName = signIn.selectedAccount?.name?.trim().orEmpty()
            )
        }

    fun signInObserve(context: Context): Observable<String> =
        manager(context).signInService.signInObserve()

    suspend fun signOut(context: Context) = withContext(Dispatchers.IO) {
        val signIn = manager(context).signInService
        signIn.selectedAccount?.let { signIn.removeAccount(it) }
    }

    suspend fun home(context: Context): Result<List<V100SmartTubeRow>> =
        withContext(Dispatchers.IO) {
            runCatching {
                val service = manager(context).contentService
                val primary = mapGroups(service.home)
                if (primary.isNotEmpty()) {
                    primary
                } else {
                    // Anonymous YouTube TV home can legitimately be empty.
                    // Build a useful TV start page from working SmartTube searches
                    // until the user signs in; signed-in home remains preferred.
                    fallbackRows(service)
                }
            }
        }

    suspend fun search(context: Context, query: String): Result<List<V100SmartTubeRow>> =
        withContext(Dispatchers.IO) {
            runCatching {
                val needle = query.trim()
                if (needle.isBlank()) return@runCatching emptyList()
                mapGroups(manager(context).contentService.getSearch(needle))
            }
        }

    suspend fun resolvePlayback(
        context: Context,
        video: V100SmartTubeVideo
    ): Result<V100SmartTubePlayback> = withContext(Dispatchers.IO) {
        runCatching {
            val info = EpiMediaPlaybackBridge.getMedia3CompatibleFormatInfo(video.videoId)
                ?: error("SmartTube konnte keine Wiedergabeinformationen laden.")
            if (info.isUnplayable) {
                error(info.playabilityReason?.takeIf { it.isNotBlank() } ?: "Video ist nicht abspielbar.")
            }

            val hls = info.hlsManifestUrl?.takeIf { info.containsHlsUrl() && it.startsWith("http") }
            val remoteDash = info.dashManifestUrl?.takeIf { info.containsDashUrl() && it.startsWith("http") }

            // Match SmartTube's playback priority more closely. For ordinary
            // videos SmartTube prefers adaptive DASH over the legacy URL list.
            // EpiMediaHub uses Media3, so materialize SmartTube's generated MPD
            // into our private cache and hand that manifest to our own player.
            if (!info.isLive && info.containsDashFormats()) {
                val mpd = info.createMpdStream()
                if (mpd != null) {
                    val file = File(context.cacheDir, "smarttube-${video.videoId}.mpd")
                    mpd.use { input ->
                        file.outputStream().use { output -> input.copyTo(output) }
                    }
                    if (file.length() > 0L) {
                        return@runCatching V100SmartTubePlayback(file.toURI().toString(), "mpd")
                    }
                }
            }

            if (info.isLive && remoteDash != null) {
                return@runCatching V100SmartTubePlayback(remoteDash, "mpd")
            }
            if (info.isLive && hls != null) {
                return@runCatching V100SmartTubePlayback(hls, "m3u8")
            }

            val progressive = if (info.containsUrlFormats()) {
                info.createUrlList()?.firstOrNull { it.startsWith("http") }
            } else null
            if (progressive != null) {
                return@runCatching V100SmartTubePlayback(progressive, extensionFor(progressive))
            }

            if (remoteDash != null) {
                return@runCatching V100SmartTubePlayback(remoteDash, "mpd")
            }
            if (hls != null) {
                return@runCatching V100SmartTubePlayback(hls, "m3u8")
            }

            val mode = buildList {
                if (info.containsDashFormats()) add("DASH")
                if (info.containsSabrFormats()) add("SABR")
                if (info.containsUrlFormats()) add("URL")
                if (info.containsHlsUrl()) add("HLS")
            }.joinToString("+").ifBlank { "keine Formate" }

            error(
                (info.playabilityReason?.takeIf { it.isNotBlank() }?.plus(" · ") ?: "") +
                    "SmartTube-Wiedergabe: $mode konnte nicht an Media3 übergeben werden."
            )
        }
    }

    private fun fallbackRows(
        service: com.liskovsoft.mediaserviceinterfaces.ContentService
    ): List<V100SmartTubeRow> {
        val sections = listOf(
            "Für dich" to "Beliebt auf YouTube",
            "Musik" to "Musik",
            "Nachrichten" to "Nachrichten",
            "Gaming" to "Gaming"
        )
        return sections.mapNotNull { (title, needle) ->
            val videos = service.getSearch(needle)
                .orEmpty()
                .flatMap { it.mediaItems.orEmpty() }
                .mapNotNull(::mapItem)
                .distinctBy { it.videoId }
                .take(24)
            if (videos.isEmpty()) null else V100SmartTubeRow(title, videos)
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
