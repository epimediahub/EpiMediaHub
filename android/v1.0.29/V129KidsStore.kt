package de.epimediahub.app.ui

import android.content.Context

/** Persist the Kids session across Back, backgrounding and process restarts. */
internal class V129KidsStore(context: Context) {
    val prefs = context.applicationContext.getSharedPreferences("epi_smarttube_kids_v129", Context.MODE_PRIVATE)
    fun active() = prefs.getBoolean("active", false)
    fun enter() { check(prefs.edit().putBoolean("active", true).commit()) }
    fun leave() { check(prefs.edit().putBoolean("active", false).commit()) }
}

/** Only items received from the separate Kids catalogue can be played or suggested. */
internal class V129KidsCatalogue(rows: List<V100SmartTubeRow>) {
    private val idPattern = Regex("[A-Za-z0-9_-]{11}")
    val rows = rows.mapNotNull { row ->
        val videos = row.videos.filter { !it.live && idPattern.matches(it.videoId) }
            .distinctBy { it.videoId }.take(60)
        if (videos.isEmpty()) null else row.copy(videos = videos)
    }.take(12)
    val videos = this.rows.flatMap { it.videos }.distinctBy { it.videoId }
    private val ids = videos.map { it.videoId }.toSet()
    fun allows(video: V100SmartTubeVideo) = !video.live && video.videoId in ids
}
