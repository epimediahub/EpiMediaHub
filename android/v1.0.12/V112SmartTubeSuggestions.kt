package de.epimediahub.app.ui

internal object V112SmartTubeWatchRules {
    fun isWatched(live: Boolean, positionMs: Long, durationMs: Long, ended: Boolean): Boolean {
        if (live || positionMs <= 0L) return false
        return ended || (durationMs > 0L && positionMs.toDouble() / durationMs >= .90)
    }
}

internal object V112SmartTubeSuggestions {
    fun visible(rows: List<V100SmartTubeRow>, watched: Set<String>, hideWatched: Boolean): List<V100SmartTubeRow> =
        rows.mapNotNull { row ->
            val videos = row.videos.filterNot { hideWatched && !it.live && it.videoId in watched }
                .distinctBy { it.videoId }.take(30)
            if (videos.isEmpty()) null else row.copy(videos = videos)
        }

    fun next(rows: List<V100SmartTubeRow>, currentId: String, watched: Set<String>): V100SmartTubeVideo? {
        val queue = rows.flatMap { it.videos }.distinctBy { it.videoId }
        val currentIndex = queue.indexOfFirst { it.videoId == currentId }
        if (currentIndex < 0) return null
        return queue.drop(currentIndex + 1).firstOrNull { it.videoId !in watched || it.live }
    }
}
