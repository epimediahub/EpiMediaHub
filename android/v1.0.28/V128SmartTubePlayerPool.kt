package de.epimediahub.app.ui

import android.content.Context
import androidx.annotation.OptIn
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.DefaultLoadControl
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory

/** One idle player is prepared on entry; no MediaItem means no media request or playback. */
@OptIn(UnstableApi::class)
internal class V128SmartTubePlayerPool(context: Context) {
    val result: Result<ExoPlayer> = runCatching {
        val http = DefaultHttpDataSource.Factory().setUserAgent("EpiMediaHub/1.0.28")
            .setAllowCrossProtocolRedirects(true)
        val factory = DefaultMediaSourceFactory(context)
            .setDataSourceFactory(DefaultDataSource.Factory(context, http))
        ExoPlayer.Builder(context).setMediaSourceFactory(factory)
            .setLoadControl(DefaultLoadControl.Builder().setBufferDurationsMs(5_000, 30_000, 750, 1_250).build()).build()
    }
    fun close() { result.getOrNull()?.release() }
}
