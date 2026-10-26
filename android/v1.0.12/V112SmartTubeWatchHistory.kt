package de.epimediahub.app.ui

import android.content.Context
import com.liskovsoft.mediaserviceinterfaces.oauth.Account
import com.liskovsoft.sharedutils.prefs.GlobalPreferences
import com.liskovsoft.youtubeapi.service.YouTubeServiceManager
import io.reactivex.schedulers.Schedulers
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import org.json.JSONArray
import java.security.MessageDigest
import java.util.concurrent.TimeUnit

/** Local viewed IDs work without login; signed-in playback also updates YouTube's history. */
internal object V112SmartTubeWatchHistory {
    private const val MAX_IDS = 5_000
    private val seenByAccount = HashMap<String, LinkedHashSet<String>>()
    private data class Update(val context: Context, val accountKey: String, val videoId: String, val positionSec: Float)
    private val updates = Channel<Update>(Channel.CONFLATED)
    private val worker = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    init {
        worker.launch {
            for (update in updates) {
                try {
                    GlobalPreferences.instance(update.context)
                    val service = YouTubeServiceManager.instance()
                    if (!service.signInService.isSigned || accountKey(service.signInService.selectedAccount) != update.accountKey) continue
                    service.mediaItemService.updateHistoryPositionObserve(update.videoId, update.positionSec)
                        .subscribeOn(Schedulers.io()).timeout(12L, TimeUnit.SECONDS).ignoreElements().blockingAwait()
                } catch (_: Exception) {
                    // Offline/disabled YouTube history must never interrupt local playback or the viewed filter.
                }
            }
        }
    }

    fun accountKey(account: Account?): String {
        if (account == null) return "guest"
        val identity = "${account.id}|${account.email.orEmpty()}|${account.name.orEmpty()}"
        return MessageDigest.getInstance("SHA-256").digest(identity.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it.toInt() and 255) }
    }

    @Synchronized
    fun watched(context: Context, accountKey: String): Set<String> = ids(context, accountKey).toSet()

    private fun ids(context: Context, accountKey: String): LinkedHashSet<String> =
        seenByAccount.getOrPut(accountKey) {
            val raw = context.applicationContext.getSharedPreferences("smarttube_watched_v112", Context.MODE_PRIVATE)
                .getString(accountKey, "[]").orEmpty()
            val array = runCatching { JSONArray(raw) }.getOrElse { JSONArray() }
            LinkedHashSet<String>().apply {
                for (i in (array.length() - MAX_IDS).coerceAtLeast(0) until array.length()) {
                    array.optString(i).takeIf { it.isNotBlank() }?.let(::add)
                }
            }
        }

    @Synchronized
    fun mark(context: Context, accountKey: String, videoId: String): Boolean {
        if (videoId.isBlank()) return false
        val ids = ids(context, accountKey)
        if (!ids.add(videoId)) return false
        while (ids.size > MAX_IDS) ids.remove(ids.first())
        context.applicationContext.getSharedPreferences("smarttube_watched_v112", Context.MODE_PRIVATE)
            .edit().putString(accountKey, JSONArray(ids.toList()).toString()).apply()
        return true
    }

    fun sync(context: Context, accountKey: String, videoId: String, positionMs: Long) {
        if (accountKey == "guest" || positionMs <= 0L) return
        updates.trySend(Update(context.applicationContext, accountKey, videoId, positionMs / 1_000f))
    }
}
