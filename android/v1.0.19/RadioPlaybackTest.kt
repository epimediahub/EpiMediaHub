package de.epimediahub.app.radio

import android.content.ComponentName
import android.content.Context
import android.content.pm.PackageManager
import androidx.media3.common.MimeTypes
import androidx.test.core.app.ApplicationProvider
import de.epimediahub.app.data.RadioStation
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [29])
class RadioPlaybackTest {
    @Test fun stationIdentitySurvivesLiveSongMetadataUpdates() {
        val station = RadioStation("station-1", "Radio Epi", "https://radio.example/live", countryCode = "IT")
        val item = station.mediaItem()
        val updated = item.buildUpon().setMediaMetadata(item.mediaMetadata.buildUpon().setTitle("Artist – Song").build()).build()
        assertEquals(station, radioStation(updated))
        assertEquals(station.uuid, updated.mediaId)
        assertEquals("Artist – Song", updated.mediaMetadata.title.toString())
    }
    @Test fun hlsStreamsGetTheirRequiredMediaType() {
        val station = RadioStation("station-1", "Radio Epi", "https://radio.example/live", hls = true)
        assertEquals(MimeTypes.APPLICATION_M3U8, station.mediaItem().localConfiguration!!.mimeType)
    }
    @Test fun backgroundPlaybackServiceAndRequiredPermissionsAreRegistered() {
        val context = ApplicationProvider.getApplicationContext<Context>()
        val service = context.packageManager.getServiceInfo(ComponentName(context, RadioPlaybackService::class.java), 0)
        assertEquals(android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK, service.foregroundServiceType)
        val permissions = context.packageManager.getPackageInfo(context.packageName, PackageManager.GET_PERMISSIONS).requestedPermissions.toList()
        assertTrue(permissions.contains("android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK"))
        assertTrue(permissions.contains("android.permission.WAKE_LOCK"))
    }
}
