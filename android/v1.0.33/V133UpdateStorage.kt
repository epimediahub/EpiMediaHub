package de.epimediahub.app.data

import android.content.Context
import android.os.Environment
import android.util.Log
import de.epimediahub.app.BuildConfig
import java.io.File

internal data class V133CleanupResult(val files: Int = 0, val bytes: Long = 0, val failures: Int = 0)

/** Only updater-owned files in the private Downloads folder are eligible. */
internal object V133UpdateStorage {
    private const val STALE_PART_MS = 24L * 60L * 60L * 1000L
    private val ownedName = Regex("EpiMediaHub-v?([0-9]+(?:\\.[0-9]+){2,3})\\.apk(\\.part)?")

    private fun version(value: String): List<Int>? {
        val clean = value.removePrefix("v")
        if (!Regex("[0-9]+(?:\\.[0-9]+){2,3}").matches(clean)) return null
        return clean.split('.').map { it.toIntOrNull() ?: return null }
    }

    private fun compare(a: List<Int>, b: List<Int>): Int {
        for (index in 0 until maxOf(a.size, b.size)) {
            val comparison = a.getOrElse(index) { 0 }.compareTo(b.getOrElse(index) { 0 })
            if (comparison != 0) return comparison
        }
        return 0
    }

    @Synchronized
    fun cleanupDirectory(directory: File?, installedVersion: String,
        protectedNames: Set<String> = emptySet(), now: Long = System.currentTimeMillis()): V133CleanupResult {
        val installed = version(installedVersion) ?: return V133CleanupResult()
        if (directory == null || !directory.isDirectory) return V133CleanupResult()
        var files = 0; var bytes = 0L; var failures = 0
        try {
            val root = directory.canonicalFile
            val entries = root.listFiles() ?: return V133CleanupResult(failures = 1)
            for (file in entries) {
                try {
                    val match = ownedName.matchEntire(file.name) ?: continue
                    if (file.name in protectedNames) continue
                    val candidate = version(match.groupValues[1]) ?: continue
                    // A newer APK may still be needed by an open installer.
                    if (compare(candidate, installed) > 0) continue
                    if (match.groupValues[2].isNotEmpty() && now - file.lastModified() < STALE_PART_MS) continue
                    // Never follow links out of Downloads or descend into directories.
                    if (!file.isFile || file.canonicalFile != File(root, file.name)) continue
                    val length = file.length().coerceAtLeast(0L)
                    if (file.delete()) { files++; bytes += length } else failures++
                } catch (_: Exception) { failures++ }
            }
        } catch (_: Exception) { failures++ }
        return V133CleanupResult(files, bytes, failures)
    }

    fun cleanupInstalled(context: Context): V133CleanupResult = runCatching {
        cleanupDirectory(context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS), BuildConfig.VERSION_NAME)
    }.getOrElse { V133CleanupResult(failures = 1) }.also {
        if (it.files > 0) Log.i("EpiMediaHub", "Update cleanup: ${it.files} files, ${it.bytes} bytes released")
    }
}
