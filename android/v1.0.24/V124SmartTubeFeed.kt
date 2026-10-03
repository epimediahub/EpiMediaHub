package de.epimediahub.app.ui

import com.liskovsoft.mediaserviceinterfaces.data.MediaGroup
import com.liskovsoft.mediaserviceinterfaces.data.MediaItem
import kotlinx.coroutines.CancellationException

/** Keep YouTube's ranking, replace filtered items and bound work on older Fire TVs. */
internal object V124SmartTubeFeed {
    suspend fun rows(
        groups: List<MediaGroup>, watched: Set<String>, excluded: Set<String> = emptySet(),
        continueGroup: suspend (MediaGroup) -> MediaGroup?,
        rememberWatched: (Set<String>) -> Unit = {}
    ): List<V100SmartTubeRow> {
        val blocked = watched.toMutableSet()
        val serverWatched = LinkedHashSet<String>()
        fun record(items: List<MediaItem>?) {
            items.orEmpty().filter { !it.isLive && it.percentWatched >= 90 }
                .mapNotNull { it.videoId?.trim()?.takeIf(String::isNotEmpty) }
                .forEach { blocked.add(it); serverWatched.add(it) }
        }
        val shelves = groups.take(24).filterNot { it.type == MediaGroup.TYPE_SHORTS }
        shelves.forEach { record(it.mediaItems) }
        val emitted = HashSet<String>()
        var requestsLeft = 4
        val rows = shelves.mapNotNull { group ->
            val videos = ArrayList<V100SmartTubeVideo>()
            fun append(items: List<MediaItem>?) {
                record(items)
                for (item in items.orEmpty()) {
                    val id = item.videoId?.trim().orEmpty()
                    if (id.isBlank() || id in excluded || item.isShorts || item.isUpcoming ||
                        (!item.isLive && id in blocked) || id in emitted) continue
                    if (videos.size >= 30) break
                    emitted.add(id)
                    videos.add(V100SmartTubeVideo(id, item.title?.trim().orEmpty().ifBlank { "YouTube" },
                        item.author?.trim().orEmpty(), item.cardImageUrl?.trim().orEmpty(),
                        item.backgroundImageUrl?.trim().orEmpty(), item.durationMs.coerceAtLeast(0L), item.isLive))
                }
            }
            append(group.mediaItems)
            var cursor = group
            val visited = HashSet<String>()
            var pages = 0
            while (videos.size < 24 && requestsLeft > 0 && pages < 2) {
                val token = cursor.nextPageKey?.takeIf { it.isNotBlank() } ?: break
                if (!visited.add(token)) break
                requestsLeft--; pages++
                val next = try { continueGroup(cursor) }
                    catch (cancelled: CancellationException) { throw cancelled }
                    catch (_: Exception) { null } ?: break
                append(next.mediaItems)
                cursor = next
            }
            if (videos.isEmpty()) null else V100SmartTubeRow(
                group.title?.trim()?.takeIf { it.isNotEmpty() } ?: "Weitere Videos", videos)
        }
        if (serverWatched.isNotEmpty()) rememberWatched(serverWatched)
        // Later pages can reveal that an item from an earlier shelf was already watched.
        return V112SmartTubeSuggestions.visible(rows, blocked, true)
    }
}
