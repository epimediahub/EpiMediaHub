package de.epimediahub.app.model

enum class PlaylistType { XTREAM, M3U }
enum class MediaKind { LIVE, MOVIE, SERIES, EPISODE }

data class PlaylistProfile(
    val id: String,
    val name: String,
    val originalUrl: String,
    val type: PlaylistType,
    val server: String = "",
    val username: String = "",
    val password: String = "",
    val output: String = "ts"
)

data class ThemeInfo(val id: String, val label: String, val group: String, val accent: String)
data class ThemeGroup(val id: String, val label: String, val themes: List<String>)
data class ThemeCatalog(val groups: List<ThemeGroup>, val themes: Map<String, ThemeInfo>)
data class MediaCategory(val id: String, val name: String)

data class MediaEntry(
    val id: String,
    val name: String,
    val kind: MediaKind,
    val categoryId: String = "",
    val image: String = "",
    val rating: String = "",
    val plot: String = "",
    val streamUrl: String = "",
    val extension: String = "ts",
    val seriesId: String = "",
    val season: Int = 0,
    val episode: Int = 0,
    val epgId: String = "",
    val year: String = "",
    val duration: String = "",
    val cast: String = "",
    val director: String = "",
    val genre: String = "",
    val releaseDate: String = ""
) {
    val resumeKey: String get() = "${kind.name}:$id"
}

data class EpgItem(val title: String, val description: String, val start: Long, val end: Long)

data class ContinueItem(
    val media: MediaEntry,
    val positionMs: Long,
    val durationMs: Long,
    val updatedAt: Long
) {
    val progress: Float get() = if (durationMs <= 0L) 0f else (positionMs.toFloat() / durationMs).coerceIn(0f, 1f)
}
