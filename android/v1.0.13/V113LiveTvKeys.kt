package de.epimediahub.app.ui

/** List state belongs to the playlist/category, never to the focused channel. */
internal object V113LiveTvKeys {
    fun channels(playlistId: String, categoryId: String) = "livetv-channels:$playlistId:$categoryId"
    fun categories(playlistId: String) = "livetv-categories:$playlistId"
    fun focus(playlistId: String) = "livetv-focus:$playlistId"
}
