package de.epimediahub.app.radio

import android.content.ComponentName
import android.content.Context
import android.net.Uri
import android.os.Bundle
import androidx.core.content.ContextCompat
import androidx.media3.common.*
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.extractor.metadata.icy.IcyInfo
import androidx.media3.session.MediaController
import androidx.media3.session.MediaSession
import androidx.media3.session.MediaSessionService
import androidx.media3.session.SessionToken
import com.google.common.util.concurrent.ListenableFuture
import de.epimediahub.app.MainActivity
import de.epimediahub.app.data.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

internal fun RadioStation.mediaItem(): MediaItem {
    val metadata = MediaMetadata.Builder().setTitle(name).setArtist(country)
        .setExtras(Bundle().apply { putString("radio-station", radioJson.encodeToString(RadioStation.serializer(), this@mediaItem)) })
    if (logo.isNotBlank()) metadata.setArtworkUri(Uri.parse(logo))
    val item = MediaItem.Builder().setMediaId(uuid).setUri(streamUrl).setMediaMetadata(metadata.build())
    if (hls) item.setMimeType(MimeTypes.APPLICATION_M3U8)
    return item.build()
}

internal fun radioStation(item: MediaItem?): RadioStation? = runCatching {
    val text = item?.mediaMetadata?.extras?.getString("radio-station") ?: return@runCatching null
    radioJson.decodeFromString(RadioStation.serializer(), text)
}.getOrNull()

/** Owns the player so Android can keep radio playing with the screen locked. */
@OptIn(UnstableApi::class)
class RadioPlaybackService : MediaSessionService() {
    private var session: MediaSession? = null

    override fun onCreate() {
        super.onCreate()
        val http = DefaultHttpDataSource.Factory().setUserAgent("EpiMediaHub/1.0.19 Radio")
            .setConnectTimeoutMs(8_000).setReadTimeoutMs(12_000).setAllowCrossProtocolRedirects(true)
            .setDefaultRequestProperties(mapOf("Icy-MetaData" to "1"))
        val source = DefaultMediaSourceFactory(DefaultDataSource.Factory(this, http))
        val player = ExoPlayer.Builder(this).setMediaSourceFactory(source)
            .setLoadControl(DefaultLoadControl.Builder().setBufferDurationsMs(5_000, 20_000, 750, 1_250).build())
            .setAudioAttributes(AudioAttributes.Builder().setUsage(C.USAGE_MEDIA).setContentType(C.AUDIO_CONTENT_TYPE_MUSIC).build(), true)
            .setHandleAudioBecomingNoisy(true).setWakeMode(C.WAKE_MODE_NETWORK).build()
        val prefs = RadioPreferences(this)
        var lastStation = ""
        player.addListener(object : Player.Listener {
            override fun onMediaItemTransition(mediaItem: MediaItem?, reason: Int) {
                radioStation(mediaItem)?.let {
                    if (it.uuid != lastStation) { lastStation = it.uuid; prefs.rememberStation(it) }
                }
            }
            override fun onMetadata(metadata: Metadata) {
                for (index in 0 until metadata.length()) {
                    val song = (metadata[index] as? IcyInfo)?.title?.trim()?.takeIf { it.isNotBlank() } ?: continue
                    val current = player.currentMediaItem ?: continue
                    val station = radioStation(current) ?: continue
                    if (current.mediaMetadata.title?.toString() == song) continue
                    val updated = current.buildUpon().setMediaMetadata(current.mediaMetadata.buildUpon()
                        .setTitle(song).setArtist(station.name).build()).build()
                    // A metadata-only replacement keeps the live stream and connection running.
                    player.replaceMediaItem(player.currentMediaItemIndex, updated)
                }
            }
        })
        val intent = android.content.Intent(this, MainActivity::class.java)
            .addFlags(android.content.Intent.FLAG_ACTIVITY_SINGLE_TOP or android.content.Intent.FLAG_ACTIVITY_CLEAR_TOP)
        val pendingIntent = android.app.PendingIntent.getActivity(this, 119, intent,
            android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_IMMUTABLE)
        session = MediaSession.Builder(this, player).setSessionActivity(pendingIntent).build()
        active = this
    }

    override fun onGetSession(controllerInfo: MediaSession.ControllerInfo): MediaSession? = session

    override fun onTaskRemoved(rootIntent: android.content.Intent?) {
        if (session?.player?.playWhenReady != true) stopSelf()
    }

    override fun onDestroy() {
        if (active === this) active = null
        session?.let { it.player.release(); it.release() }
        session = null
        super.onDestroy()
    }

    companion object {
        @Volatile private var active: RadioPlaybackService? = null
        /** Prevent simultaneous sound when Live TV, a film or SmartTube starts. */
        fun pauseForVideo() { active?.session?.player?.pause() }
    }
}

internal data class RadioPlaybackState(
    val station: RadioStation? = null,
    val song: String = "",
    val playing: Boolean = false,
    val buffering: Boolean = false,
    val ready: Boolean = false,
    val previous: Boolean = false,
    val next: Boolean = false,
    val error: String = ""
)

internal class RadioController(context: Context) : AutoCloseable {
    private val mutable = MutableStateFlow(RadioPlaybackState())
    val state: StateFlow<RadioPlaybackState> = mutable
    private var controller: MediaController? = null
    private var pending: ((MediaController) -> Unit)? = null
    private var closed = false
    private val future: ListenableFuture<MediaController> = MediaController.Builder(context.applicationContext,
        SessionToken(context, ComponentName(context, RadioPlaybackService::class.java))).buildAsync()
    private val listener = object : Player.Listener {
        override fun onEvents(player: Player, events: Player.Events) { update(player) }
    }

    init {
        future.addListener({
            if (!closed) {
                runCatching {
                    val player = future.get(); controller = player; player.addListener(listener)
                    pending?.invoke(player); pending = null; update(player)
                }.onFailure { mutable.value = mutable.value.copy(error = "Radio konnte nicht gestartet werden. Bitte erneut öffnen.") }
            }
        }, ContextCompat.getMainExecutor(context))
    }

    private fun update(player: Player) {
        val station = radioStation(player.currentMediaItem)
        val title = player.mediaMetadata.title?.toString().orEmpty()
        mutable.value = RadioPlaybackState(station, title.takeUnless { it == station?.name }.orEmpty(), player.isPlaying,
            player.playbackState == Player.STATE_BUFFERING, true,
            player.hasPreviousMediaItem(), player.hasNextMediaItem(),
            if (player.playerError != null) "Sender gerade nicht erreichbar. Erneut versuchen oder einen anderen Sender wählen." else "")
    }

    private fun command(action: (MediaController) -> Unit) {
        if (closed) return
        controller?.let(action) ?: run { pending = action }
    }

    fun play(station: RadioStation, stations: List<RadioStation>) = command { player ->
        val queue = radioPlaybackQueue(stations, station)
        player.setMediaItems(queue.map { it.mediaItem() }, queue.indexOfFirst { it.uuid == station.uuid }, 0L)
        player.prepare(); player.play()
    }
    fun toggle() = command { if (it.playWhenReady && it.playerError == null) it.pause() else { it.prepare(); it.play() } }
    fun previous() = command { if (it.hasPreviousMediaItem()) { it.seekToPreviousMediaItem(); it.prepare(); it.play() } }
    fun next() = command { if (it.hasNextMediaItem()) { it.seekToNextMediaItem(); it.prepare(); it.play() } }
    fun stop() = command { it.stop(); it.clearMediaItems() }
    override fun close() {
        closed = true; pending = null
        controller?.removeListener(listener)
        MediaController.releaseFuture(future)
        controller = null
    }
}
