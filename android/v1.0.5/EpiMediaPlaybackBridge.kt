package com.liskovsoft.youtubeapi.service.internal

import com.liskovsoft.mediaserviceinterfaces.data.MediaItemFormatInfo

/**
 * Small host bridge for EpiMediaHub.
 *
 * SmartTube itself can play SABR through its custom ExoPlayer extension.
 * EpiMediaHub uses Media3, so try SmartTube's legacy playback clients until
 * one returns DASH/HLS/progressive media that Media3 can consume.
 */
object EpiMediaPlaybackBridge {
    @JvmStatic
    fun getMedia3CompatibleFormatInfo(
        videoId: String,
        clickTrackingParams: String? = null
    ): MediaItemFormatInfo? {
        return FormatInfoWrapper.getMedia3CompatibleFormatInfo(videoId, clickTrackingParams)
    }
}
