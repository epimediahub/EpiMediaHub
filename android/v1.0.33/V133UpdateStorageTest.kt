package de.epimediahub.app.data

import android.content.Context
import android.os.Environment
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import java.io.File
import java.nio.file.Files

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V133UpdateStorageTest {
    @get:Rule val temp = TemporaryFolder()
    private val now = 1_800_000_000_000L
    private fun file(directory: File, name: String, bytes: Int = 17, age: Long = 0): File =
        File(directory, name).also { it.writeBytes(ByteArray(bytes)); assertTrue(it.setLastModified(now-age)) }

    @Test fun oldAndInstalledApksAreRemovedButFutureUpdatesAndOtherFilesRemain() {
        val dir = temp.newFolder(); val old = file(dir,"EpiMediaHub-1.0.9.apk",23)
        val current = file(dir,"EpiMediaHub-1.0.33.apk",31)
        val future = file(dir,"EpiMediaHub-1.0.34.apk")
        val other = file(dir,"my-playlist.apk"); val preferences = file(dir,"settings.json")
        val result = V133UpdateStorage.cleanupDirectory(dir,"1.0.33",now=now)
        assertEquals(V133CleanupResult(2,54),result)
        assertFalse(old.exists()); assertFalse(current.exists())
        assertTrue(future.exists()); assertTrue(other.exists()); assertTrue(preferences.exists())
    }

    @Test fun freshPartialDownloadsAreKeptAndOnlyStaleInstalledPartialsAreRemoved() {
        val dir = temp.newFolder(); val day = 24L*60*60*1000
        val fresh = file(dir,"EpiMediaHub-1.0.31.apk.part",age=day-1)
        val stale = file(dir,"EpiMediaHub-1.0.32.apk.part",age=day)
        val newer = file(dir,"EpiMediaHub-1.0.34.apk.part",age=day*2)
        val result = V133UpdateStorage.cleanupDirectory(dir,"1.0.33",now=now)
        assertEquals(1,result.files); assertTrue(fresh.exists()); assertFalse(stale.exists()); assertTrue(newer.exists())
    }

    @Test fun activeDownloadAndInstallerFilesCanBeExplicitlyProtected() {
        val dir = temp.newFolder(); val active = file(dir,"EpiMediaHub-1.0.32.apk")
        val partial = file(dir,"EpiMediaHub-1.0.32.apk.part",age=48L*60*60*1000)
        file(dir,"EpiMediaHub-1.0.31.apk")
        val result = V133UpdateStorage.cleanupDirectory(dir,"1.0.33",setOf(active.name,partial.name),now)
        assertEquals(1,result.files); assertTrue(active.exists()); assertTrue(partial.exists())
    }

    @Test fun versionOrderingIsNumericAndAcceptsHistoricalVPrefixes() {
        val dir = temp.newFolder(); val nine = file(dir,"EpiMediaHub-1.0.9.apk")
        val ten = file(dir,"EpiMediaHub-v1.0.10.apk")
        val next = file(dir,"EpiMediaHub-1.0.10.1.apk")
        assertEquals(2,V133UpdateStorage.cleanupDirectory(dir,"v1.0.10",now=now).files)
        assertFalse(nine.exists()); assertFalse(ten.exists()); assertTrue(next.exists())
    }

    @Test fun directoriesAndSymlinksAreNeverDeletedOrFollowed() {
        val dir = temp.newFolder(); val outside = file(temp.newFolder(),"outside.apk")
        val folder = File(dir,"EpiMediaHub-1.0.31.apk"); assertTrue(folder.mkdir())
        Files.createSymbolicLink(File(dir,"EpiMediaHub-1.0.32.apk").toPath(),outside.toPath())
        assertEquals(V133CleanupResult(),V133UpdateStorage.cleanupDirectory(dir,"1.0.33",now=now))
        assertTrue(folder.isDirectory); assertTrue(outside.exists())
        assertTrue(Files.isSymbolicLink(File(dir,"EpiMediaHub-1.0.32.apk").toPath()))
    }

    @Test fun unknownVersionsAndNamesAreLeftAloneAndCleanupIsIdempotent() {
        val dir = temp.newFolder(); val installed = file(dir,"EpiMediaHub-1.0.32.apk")
        val invalid = file(dir,"EpiMediaHub-999999999999999999999.0.0.apk")
        val other = file(dir,"EpiMediaHub-latest.apk")
        assertEquals(V133CleanupResult(),V133UpdateStorage.cleanupDirectory(dir,"invalid",now=now))
        assertTrue(installed.exists())
        assertEquals(1,V133UpdateStorage.cleanupDirectory(dir,"1.0.33",now=now).files)
        assertEquals(V133CleanupResult(),V133UpdateStorage.cleanupDirectory(dir,"1.0.33",now=now))
        assertTrue(invalid.exists()); assertTrue(other.exists())
        assertEquals(V133CleanupResult(),V133UpdateStorage.cleanupDirectory(null,"1.0.33"))
    }

    @Test fun startupCleanupTouchesOnlyUpdaterDownloadsAndPreservesCustomerState() {
        val app = RuntimeEnvironment.getApplication()
        val dir = app.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)!!; dir.mkdirs()
        val old = file(dir,"EpiMediaHub-1.0.32.apk",29)
        val internal = file(app.filesDir,"EpiMediaHub-1.0.32.apk")
        val prefs = app.getSharedPreferences("epimediahub",Context.MODE_PRIVATE)
        prefs.edit().putString("playlists","fixture-playlists").putString("favorites_items","fixture-favorites")
            .putString("theme","napoli__legends").commit()
        val license = app.getSharedPreferences("license-fixture",Context.MODE_PRIVATE)
        license.edit().putString("activation","active").commit()
        val result = V133UpdateStorage.cleanupInstalled(app)
        assertEquals(1,result.files); assertEquals(29L,result.bytes); assertFalse(old.exists()); assertTrue(internal.exists())
        assertEquals("fixture-playlists",prefs.getString("playlists",null))
        assertEquals("fixture-favorites",prefs.getString("favorites_items",null))
        assertEquals("napoli__legends",prefs.getString("theme",null))
        assertEquals("active",license.getString("activation",null))
    }
}
