package de.epimediahub.app.ui

import android.content.Context

/** Account-separated, device-local progress for SmartTube, including guest viewing. */
internal object V184SmartTubeResume {
    private const val NAME = "smarttube_resume_v184"
    private fun key(account: String, videoId: String) = "position:$account:$videoId"
    fun read(context: Context, account: String, videoId: String): Long {
        if (videoId.isBlank() || videoId.length > 128) return 0L
        return context.applicationContext.getSharedPreferences(NAME, Context.MODE_PRIVATE)
            .getLong(key(account, videoId), 0L).coerceAtLeast(0L)
    }
    fun save(context: Context, account: String, videoId: String, position: Long, duration: Long) {
        if (videoId.isBlank() || videoId.length > 128 || position < 2_000L) return
        // Near the credits/end, begin at 0 on the next visit rather than resuming the credits.
        if (duration > 0L && position >= (duration - 20_000L).coerceAtLeast(0L)) {
            clear(context, account, videoId)
            return
        }
        context.applicationContext.getSharedPreferences(NAME, Context.MODE_PRIVATE)
            .edit().putLong(key(account, videoId), position).apply()
    }
    fun clear(context: Context, account: String, videoId: String) {
        if (videoId.isBlank() || videoId.length > 128) return
        context.applicationContext.getSharedPreferences(NAME, Context.MODE_PRIVATE)
            .edit().remove(key(account, videoId)).apply()
    }
}
