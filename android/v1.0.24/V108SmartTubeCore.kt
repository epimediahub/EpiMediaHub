package de.epimediahub.app.ui

import android.content.Context
import com.liskovsoft.mediaserviceinterfaces.ContentService
import com.liskovsoft.mediaserviceinterfaces.data.MediaGroup
import com.liskovsoft.mediaserviceinterfaces.data.MediaItem
import com.liskovsoft.sharedutils.prefs.GlobalPreferences
import com.liskovsoft.youtubeapi.service.YouTubeServiceManager
import com.liskovsoft.youtubeapi.service.internal.EpiMediaPlaybackBridge
import io.reactivex.Observable
import io.reactivex.schedulers.Schedulers
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import com.liskovsoft.youtubeapi.service.internal.MediaServiceData
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
    TRENDING("Trends", "TR"),
    MUSIC("Musik", "MU"),
    GAMING("Gaming", "GM"),
    NEWS("Nachrichten", "NW"),
    LIVE("Live", "LI")
}

internal data class V108SmartTubeAuthState(
    val signed: Boolean,
    val accountName: String,
    val accountKey: String = "guest"
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
        // Avoid the reel-details endpoint, including Shorts shelves embedded in Home.
        val data = MediaServiceData.instance()
        if (!data.isContentHidden(MediaServiceData.CONTENT_SHORTS_ALL)) {
            data.setContentHidden(MediaServiceData.CONTENT_SHORTS_ALL, true)
        }
        YouTubeServiceManager.instance()
    }

    suspend fun authState(context: Context): V108SmartTubeAuthState =
        withContext(Dispatchers.IO) {
            val signIn = manager(context).signInService
            V108SmartTubeAuthState(
                signed = signIn.isSigned,
                accountName = signIn.selectedAccount?.name?.trim().orEmpty(),
                accountKey = V112SmartTubeWatchHistory.accountKey(signIn.selectedAccount)
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
        try {
            val manager = manager(context)
            val service = manager.contentService
            val scope = V112SmartTubeWatchHistory.accountKey(manager.signInService.selectedAccount)
            val groups = when (section) {
                V108SmartTubeSection.HOME -> collectGroups(Observable.fromCallable { service.getHome().orEmpty() })
                V108SmartTubeSection.SUBSCRIPTIONS -> collectSingleGroups(service.getSubscriptionsObserve())
                V108SmartTubeSection.HISTORY -> collectSingleGroups(service.getHistoryObserve())
                V108SmartTubeSection.PLAYLISTS -> collectSingleGroups(service.getPlaylistsObserve())
                V108SmartTubeSection.TRENDING -> emptyList()
                V108SmartTubeSection.MUSIC -> collectGroups(service.getMusicObserve())
                V108SmartTubeSection.GAMING -> collectGroups(service.getGamingObserve())
                V108SmartTubeSection.NEWS -> collectGroups(service.getNewsObserve())
                V108SmartTubeSection.LIVE -> collectGroups(service.getLiveObserve())
            }
            val feed = section != V108SmartTubeSection.HISTORY && section != V108SmartTubeSection.PLAYLISTS
            checkAccount(manager, scope)
            val mapped = if (feed) feedRows(context, scope, service, groups) else mapGroups(groups)
            checkAccount(manager, scope)
            Result.success(mapped)
        } catch (cancelled: CancellationException) {
            throw cancelled
        } catch (failure: Exception) {
            Result.failure(failure)
        }
    }

    suspend fun search(context: Context, query: String): Result<List<V100SmartTubeRow>> =
        withContext(Dispatchers.IO) {
            try {
                val needle = query.trim()
                Result.success(if (needle.isBlank()) emptyList()
                    else mapGroups(collectGroups(manager(context).contentService.getSearchObserve(needle))))
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (failure: Exception) {
                Result.failure(failure)
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

    private suspend fun <T : Any> collect(source: Observable<T>, timeoutSeconds: Long = 20L): List<T> =
        suspendCancellableCoroutine { continuation ->
            val disposable = source.subscribeOn(Schedulers.io()).take(24).toList()
                .timeout(timeoutSeconds, TimeUnit.SECONDS)
                .subscribe(
                    { if (continuation.isActive) continuation.resume(it) },
                    { if (continuation.isActive) continuation.resumeWithException(it) }
                )
            continuation.invokeOnCancellation { disposable.dispose() }
        }

    private suspend fun collectGroups(source: Observable<List<MediaGroup>>): List<MediaGroup> =
        collect(source).flatten().take(24)

    private suspend fun collectSingleGroups(source: Observable<MediaGroup>): List<MediaGroup> = collect(source)

    private fun checkAccount(manager: com.liskovsoft.mediaserviceinterfaces.ServiceManager, expected: String) {
        if (V112SmartTubeWatchHistory.accountKey(manager.signInService.selectedAccount) != expected)
            throw CancellationException("YouTube account changed")
    }

    suspend fun related(context: Context, videoId: String, accountKey: String): Result<List<V100SmartTubeRow>> =
        withContext(Dispatchers.IO) {
            try {
                val manager = manager(context)
                checkAccount(manager, accountKey)
                val metadata = collect(manager.mediaItemService.getMetadataObserve(videoId).take(1), 12L)
                    .firstOrNull() ?: error("YouTube hat keine passenden Videos geliefert.")
                checkAccount(manager, accountKey)
                val rows = feedRows(context, accountKey, manager.contentService,
                    metadata.suggestions, setOf(videoId))
                checkAccount(manager, accountKey)
                Result.success(rows)
            } catch (cancelled: CancellationException) { throw cancelled }
            catch (failure: Exception) { Result.failure(failure) }
        }

    private suspend fun feedRows(
        context: Context, scope: String, service: ContentService, groups: List<MediaGroup>?,
        excluded: Set<String> = emptySet()
    ): List<V100SmartTubeRow> = V124SmartTubeFeed.rows(
        groups.orEmpty(), V112SmartTubeWatchHistory.watched(context, scope), excluded,
        continueGroup = { group -> collect(service.continueGroupObserve(group).take(1), 4L).firstOrNull() },
        rememberWatched = { V112SmartTubeWatchHistory.mergeWatched(context, scope, it) })

    private fun mapGroups(groups: List<MediaGroup>?): List<V100SmartTubeRow> =
        groups.orEmpty().take(24).filterNot { it.type == MediaGroup.TYPE_SHORTS }.mapNotNull { group ->
            val videos = group.mediaItems.orEmpty().mapNotNull(::mapItem).distinctBy { it.videoId }.take(60)
            if (videos.isEmpty()) null
            else V100SmartTubeRow(group.title?.takeIf { it.isNotBlank() } ?: "YouTube", videos)
        }

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
