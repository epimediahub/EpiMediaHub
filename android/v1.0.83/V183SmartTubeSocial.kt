package de.epimediahub.app.ui

import android.content.Context
import com.liskovsoft.youtubeapi.service.YouTubeServiceManager
import com.liskovsoft.sharedutils.prefs.GlobalPreferences
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/** Actual creator information and per-video comments from the pinned SmartTube backend.
 * Never fabricate a subscriber count, a channel ID or comments when YouTube hides them.
 * IO is bounded and never runs on the Android/Compose main thread.
 */
internal data class V183CreatorDetails(
    val channelId: String,
    val channelName: String,
    val avatar: String,
    val subscribers: String,
    val commentsKey: String
)
internal data class V183Comment(
    val id: String,
    val author: String,
    val avatar: String,
    val message: String,
    val date: String,
    val likes: String,
    val replies: String
)
internal data class V183CommentsPage(
    val items: List<V183Comment>,
    val nextKey: String
)

internal object V183SmartTubeSocial {
    suspend fun creator(context: Context, videoId: String): Result<V183CreatorDetails> =
        withContext(Dispatchers.IO) {
            try {
                require(videoId.isNotBlank() && videoId.length <= 128)
                GlobalPreferences.instance(context.applicationContext)
                val data = YouTubeServiceManager.instance().mediaItemService
                    .getMetadataObserve(videoId)
                    .firstOrError()
                    .timeout(14, TimeUnit.SECONDS)
                    .blockingGet()
                Result.success(
                    V183CreatorDetails(
                        channelId = data.channelId.orEmpty().trim()
                            .takeIf(V179SmartTubeChannel::validId).orEmpty(),
                        channelName = data.author.orEmpty().trim().take(120),
                        avatar = data.authorImageUrl.orEmpty().trim()
                            .takeIf { it.startsWith("https://") }.orEmpty(),
                        subscribers = data.subscriberCount.orEmpty().trim().take(64),
                        commentsKey = data.commentsKey.orEmpty().trim().take(1024)
                    )
                )
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (err: Exception) {
                Result.failure(err)
            }
        }

    suspend fun comments(context: Context, key: String): Result<V183CommentsPage> =
        withContext(Dispatchers.IO) {
            try {
                require(key.isNotBlank() && key.length <= 1024)
                GlobalPreferences.instance(context.applicationContext)
                val group = YouTubeServiceManager.instance().commentsService
                    .getCommentsObserve(key)
                    .firstOrError()
                    .timeout(14, TimeUnit.SECONDS)
                    .blockingGet()
                val items = group.comments.orEmpty().take(30).mapIndexed { index, item ->
                    V183Comment(
                        id = item.id.orEmpty().ifBlank { "comment-$index" },
                        author = item.authorName.orEmpty().take(90),
                        avatar = item.authorPhoto.orEmpty()
                            .takeIf { it.startsWith("https://") }.orEmpty(),
                        message = item.message.orEmpty().take(1800),
                        date = item.publishedDate.orEmpty().take(80),
                        likes = item.likeCount.orEmpty().take(32),
                        replies = item.replyCount.orEmpty().take(32)
                    )
                }.filter { it.message.isNotBlank() }
                Result.success(V183CommentsPage(items, group.nextCommentsKey.orEmpty().trim().take(1024)))
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (err: Exception) {
                Result.failure(err)
            }
        }
}
