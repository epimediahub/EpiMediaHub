package de.epimediahub.app.ui

import android.content.Context
import com.liskovsoft.mediaserviceinterfaces.ContentService
import com.liskovsoft.mediaserviceinterfaces.data.MediaGroup
import com.liskovsoft.mediaserviceinterfaces.data.MediaItem
import com.liskovsoft.sharedutils.prefs.GlobalPreferences
import com.liskovsoft.youtubeapi.service.YouTubeServiceManager
import com.liskovsoft.youtubeapi.service.internal.EpiMediaPlaybackBridge
import io.reactivex.Observable
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

internal enum class V108SmartTubeSection(
    val label: String,
    val shortMark: String,
    val requiresAuth: Boolean = false
) {
    HOME("Startseite", "ST"),
    SUBSCRIPTIONS("Abos", "AB", true),
    HISTORY("Verlauf", "VL", true),
    PLAYLISTS("Playlists", "PL", true),
    SHORTS("Shorts", "SH"),
    TRENDING("Trends", "TR"),
    MUSIC("Musik", "MU"),
    GAMING("Gaming", "GM"),
    NEWS("Nachrichten", "NW"),
    LIVE("Live", "LI")
}

internal data class V108SmartTubeAuthState(
    val signed: Boolean,
    val accountName: String
)

internal object V108SmartTubeCore {
    private data class CachedPlayback(
        val value: V100SmartTubePlayback,
        val expiresAtMs: Long
    )

    private val playbackCache = LinkedHashMap<String, CachedPlayback>()

    private fun cachedPlayback(videoId: String): V100SmartTubePlayback? = synchronized(playbackCache) {
        val now = System.currentTimeMillis()
        playbackCache.entries.removeAll { it.value.expiresAtMs <= now }
        playbackCache[videoId]?.value
    }

    private fun rememberPlayback(videoId: String, value: V100SmartTubePlayback) = synchronized(playbackCache) {
        playbackCache[videoId] = CachedPlayback(
            value = value,
            expiresAtMs = System.currentTimeMillis() + 5 * 60 * 1000L
        )
        while (playbackCache.size > 12) {
            val first = playbackCache.keys.firstOrNull() ?: break
            playbackCache.remove(first)
        }
    }

    private fun manager(context: Context) = run {
        GlobalPreferences.instance(context.applicationContext)
        YouTubeServiceManager.instance()
    }

    suspend fun authState(context: Context): V108SmartTubeAuthState =
        withContext(Dispatchers.IO) {
            val signIn = manager(context).signInService
            V108SmartTubeAuthState(
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

    suspend fun section(
        context: Context,
        section: V108SmartTubeSection
    ): Result<List<V100SmartTubeRow>> = withContext(Dispatchers.IO) {
        runCatching {
            val service = manager(context).contentService
            when (section) {
                V108SmartTubeSection.HOME -> homeRows(service)
                V108SmartTubeSection.SUBSCRIPTIONS ->
                    mapGroups(listOfNotNull(service.getSubscriptions()))
                V108SmartTubeSection.HISTORY ->
                    mapGroups(listOfNotNull(service.getHistory()))
                V108SmartTubeSection.PLAYLISTS ->
                    mapGroups(collectSingleGroups(service.getPlaylistsObserve()))
                V108SmartTubeSection.SHORTS ->
                    mapGroups(collectSingleGroups(service.getShortsObserve()))
                V108SmartTubeSection.TRENDING ->
                    mapGroups(collectGroups(service.getTrendingObserve()))
                V108SmartTubeSection.MUSIC ->
                    mapGroups(collectGroups(service.getMusicObserve()))
                V108SmartTubeSection.GAMING ->
                    mapGroups(collectGroups(service.getGamingObserve()))
                V108SmartTubeSection.NEWS ->
                    mapGroups(collectGroups(service.getNewsObserve()))
                V108SmartTubeSection.LIVE ->
                    mapGroups(collectGroups(service.getLiveObserve()))
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
        cachedPlayback(video.videoId)?.let {
            return@withContext Result.success(it)
        }

        runCatching {
            val info = EpiMediaPlaybackBridge.getMedia3CompatibleFormatInfo(video.videoId)
                ?: error("SmartTube konnte keine Wiedergabeinformationen laden.")
            if (info.isUnplayable) {
                error(info.playabilityReason?.takeIf { it.isNotBlank() } ?: "Video ist nicht abspielbar.")
            }

            val hls = info.hlsManifestUrl?.takeIf { info.containsHlsUrl() && it.startsWith("http") }
            val remoteDash = info.dashManifestUrl?.takeIf { info.containsDashUrl() && it.startsWith("http") }

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
        }.onSuccess { rememberPlayback(video.videoId, it) }
    }

    private fun collectGroups(source: Observable<List<MediaGroup>>): List<MediaGroup> =
        source.toList().blockingGet().flatten()

    private fun collectSingleGroups(source: Observable<MediaGroup>): List<MediaGroup> =
        source.toList().blockingGet()

    private fun homeRows(service: ContentService): List<V100SmartTubeRow> {
        val primary = mapGroups(service.getHome())
        return if (primary.isNotEmpty()) primary else fallbackRows(service)
    }

    private fun fallbackRows(service: ContentService): List<V100SmartTubeRow> {
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
        }.take(24)

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
