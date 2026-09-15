#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")

# Version metadata.
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
require_once(s, 'versionCode = 51', 'v0.4.11 versionCode')
require_once(s, 'versionName = "0.4.11"', 'v0.4.11 versionName')
s = s.replace('versionCode = 51', 'versionCode = 52', 1)
s = s.replace('versionName = "0.4.11"', 'versionName = "0.4.12"', 1)
gradle.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.4.11", "0.4.12"))

# Replace the old single-endpoint updater with a resilient implementation.
manager = java / "data/UpdateManager.kt"
manager.write_text(r'''package de.epimediahub.app.data

import android.content.Context
import android.content.Intent
import android.os.Environment
import androidx.core.content.FileProvider
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.NetworkType
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import de.epimediahub.app.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import java.util.concurrent.TimeUnit


data class AppUpdateInfo(
    val version: String,
    val versionCode: Int,
    val url: String,
    val sha256: String = "",
    val notes: String = ""
)

object AppUpdateManager {
    private const val MANIFEST_RAW_URL = "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/android/update.json"
    private const val MANIFEST_API_URL = "https://api.github.com/repos/epimediahub/EpiMediaHub/contents/android/update.json?ref=main"
    private const val RELEASE_API_URL = "https://api.github.com/repos/epimediahub/EpiMediaHub/releases/tags/android-latest"
    private const val STABLE_APK_URL = "https://github.com/epimediahub/EpiMediaHub/releases/download/android-latest/EpiMediaHub-Android.apk"
    private const val PREFS = "epimediahub_updater"
    private const val KEY_LAST_CHECK = "last_check_ms"
    private const val KEY_PENDING = "pending_update"
    private const val WORK_NAME = "epimediahub-update-check"
    private const val CHECK_INTERVAL_MS = 24L * 60L * 60L * 1000L

    fun schedule(context: Context) {
        val constraints = Constraints.Builder()
            .setRequiredNetworkType(NetworkType.CONNECTED)
            .build()
        val request = PeriodicWorkRequestBuilder<UpdateCheckWorker>(24, TimeUnit.HOURS)
            .setConstraints(constraints)
            .build()
        WorkManager.getInstance(context.applicationContext).enqueueUniquePeriodicWork(
            WORK_NAME,
            ExistingPeriodicWorkPolicy.KEEP,
            request
        )
    }

    fun pending(context: Context): AppUpdateInfo? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw = prefs.getString(KEY_PENDING, null) ?: return null
        return runCatching { parseManifest(JSONObject(raw)) }.getOrNull()?.also {
            if (it.versionCode <= BuildConfig.VERSION_CODE) clearPending(context)
        }?.takeIf { it.versionCode > BuildConfig.VERSION_CODE }
    }

    suspend fun checkIfDue(context: Context, force: Boolean = false): AppUpdateInfo? {
        pending(context)?.let { return it }
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val now = System.currentTimeMillis()
        val last = prefs.getLong(KEY_LAST_CHECK, 0L)
        if (!force && now - last < CHECK_INTERVAL_MS) return null
        return checkNow(context)
    }

    suspend fun checkNow(context: Context): AppUpdateInfo? = withContext(Dispatchers.IO) {
        val info = fetchLatestInfo()
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putLong(KEY_LAST_CHECK, System.currentTimeMillis())
            .apply()
        if (info.versionCode > BuildConfig.VERSION_CODE) {
            savePending(context, info)
            info
        } else {
            clearPending(context)
            null
        }
    }

    /**
     * Three independent metadata paths are used deliberately. Several Android
     * TV DNS/filter setups block raw.githubusercontent.com while github.com or
     * api.github.com still work. One failed endpoint must never break updates.
     */
    private fun fetchLatestInfo(): AppUpdateInfo {
        val errors = mutableListOf<String>()

        runCatching {
            parseManifest(JSONObject(fetchJson(MANIFEST_RAW_URL)))
        }.onSuccess { return it }
            .onFailure { errors += "raw: ${shortError(it)}" }

        runCatching {
            val raw = fetchJson(MANIFEST_API_URL, "application/vnd.github.raw+json")
            parseManifest(JSONObject(raw))
        }.onSuccess { return it }
            .onFailure { errors += "api-manifest: ${shortError(it)}" }

        runCatching {
            parseRelease(JSONObject(fetchJson(RELEASE_API_URL, "application/vnd.github+json")))
        }.onSuccess { return it }
            .onFailure { errors += "release: ${shortError(it)}" }

        error("Update-Metadaten konnten nicht geladen werden. ${errors.joinToString(" | ")}")
    }

    suspend fun downloadApk(context: Context, info: AppUpdateInfo): File = withContext(Dispatchers.IO) {
        val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: error("Download-Verzeichnis ist nicht verfügbar.")
        if (!dir.exists() && !dir.mkdirs()) error("Download-Verzeichnis konnte nicht erstellt werden.")
        val safeVersion = info.version.ifBlank { "latest" }.replace(Regex("[^A-Za-z0-9._-]"), "_")
        val file = File(dir, "EpiMediaHub-$safeVersion.apk")
        if (file.exists()) file.delete()

        val primary = info.url.ifBlank { STABLE_APK_URL }
        val conn = openGet(primary, accept = "application/vnd.android.package-archive", readTimeoutMs = 120000)
        try {
            val code = conn.responseCode
            if (code !in 200..299) error("Update-Download fehlgeschlagen (HTTP $code).")
            val digest = MessageDigest.getInstance("SHA-256")
            conn.inputStream.use { input ->
                file.outputStream().use { output ->
                    val buffer = ByteArray(128 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read <= 0) break
                        output.write(buffer, 0, read)
                        digest.update(buffer, 0, read)
                    }
                }
            }
            if (file.length() < 1024 * 1024) {
                file.delete()
                error("Update-Download ist unvollständig (${file.length()} Bytes).")
            }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            if (info.sha256.isNotBlank() && !actual.equals(info.sha256, ignoreCase = true)) {
                file.delete()
                error("Sicherheitsprüfung fehlgeschlagen: SHA-256 stimmt nicht.")
            }
            file
        } finally {
            conn.disconnect()
        }
    }

    fun installApk(context: Context, apk: File) {
        val uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            apk
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        context.startActivity(intent)
    }

    fun clearPending(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().remove(KEY_PENDING).apply()
    }

    private fun savePending(context: Context, info: AppUpdateInfo) {
        val json = JSONObject()
            .put("version", info.version)
            .put("versionCode", info.versionCode)
            .put("url", info.url)
            .put("sha256", info.sha256)
            .put("notes", info.notes)
            .toString()
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY_PENDING, json).apply()
    }

    private fun parseManifest(json: JSONObject) = AppUpdateInfo(
        version = json.optString("version"),
        versionCode = json.optInt("versionCode"),
        url = json.optString("url").ifBlank { STABLE_APK_URL },
        sha256 = json.optString("sha256").removePrefix("sha256:"),
        notes = json.optString("notes")
    ).also {
        require(it.version.isNotBlank()) { "Update-Version fehlt." }
        require(it.versionCode > 0) { "Update-VersionCode fehlt." }
        require(it.url.startsWith("https://")) { "Ungültige Update-URL." }
    }

    private fun parseRelease(json: JSONObject): AppUpdateInfo {
        val title = json.optString("name")
        val version = Regex("v(\\d+\\.\\d+\\.\\d+)").find(title)?.groupValues?.get(1)
            ?: error("Release-Version fehlt.")
        val assets = json.optJSONArray("assets") ?: error("Release enthält keine Assets.")
        var url = ""
        var digest = ""
        for (i in 0 until assets.length()) {
            val asset = assets.optJSONObject(i) ?: continue
            if (asset.optString("name") == "EpiMediaHub-Android.apk") {
                url = asset.optString("browser_download_url")
                digest = asset.optString("digest").removePrefix("sha256:")
                break
            }
        }
        require(url.startsWith("https://")) { "APK-Asset fehlt im android-latest-Release." }
        return AppUpdateInfo(
            version = version,
            versionCode = versionCodeFrom(version),
            url = url,
            sha256 = digest,
            notes = json.optString("body")
        )
    }

    private fun versionCodeFrom(version: String): Int {
        val parts = version.split('.').mapNotNull { it.toIntOrNull() }
        require(parts.size == 3) { "Ungültige Release-Version: $version" }
        // Existing EpiMediaHub versionCode scheme: 0.3.6 -> 36, 0.4.12 -> 52.
        return if (parts[0] == 0) parts[1] * 10 + parts[2]
        else parts[0] * 10000 + parts[1] * 100 + parts[2]
    }

    private fun fetchJson(url: String, accept: String = "application/json"): String {
        val conn = openGet(url, accept = accept, readTimeoutMs = 15000)
        try {
            val code = conn.responseCode
            if (code !in 200..299) {
                val detail = runCatching { conn.errorStream?.bufferedReader()?.use { it.readText() } }.getOrNull().orEmpty()
                error("HTTP $code${if (detail.isBlank()) "" else ": ${detail.take(120)}"}")
            }
            return conn.inputStream.bufferedReader().use { it.readText() }
        } finally {
            conn.disconnect()
        }
    }

    private fun openGet(url: String, accept: String, readTimeoutMs: Int): HttpURLConnection {
        var current = url
        repeat(8) {
            require(current.startsWith("https://")) { "Unsichere Weiterleitung blockiert." }
            val conn = (URL(current).openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                connectTimeout = 15000
                readTimeout = readTimeoutMs
                requestMethod = "GET"
                setRequestProperty("User-Agent", "EpiMediaHub/${BuildConfig.VERSION_NAME} Android")
                setRequestProperty("Accept", accept)
                setRequestProperty("Cache-Control", "no-cache")
                setRequestProperty("Pragma", "no-cache")
            }
            when (conn.responseCode) {
                HttpURLConnection.HTTP_MOVED_PERM,
                HttpURLConnection.HTTP_MOVED_TEMP,
                HttpURLConnection.HTTP_SEE_OTHER,
                307, 308 -> {
                    val location = conn.getHeaderField("Location")
                        ?: run { conn.disconnect(); error("GitHub-Weiterleitung ohne Ziel.") }
                    val next = URL(URL(current), location).toString()
                    conn.disconnect()
                    current = next
                }
                else -> return conn
            }
        }
        error("Zu viele Weiterleitungen beim Update-Download.")
    }

    private fun shortError(error: Throwable): String =
        (error.message ?: error.javaClass.simpleName).replace('\n', ' ').take(140)
}

class UpdateCheckWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result {
        return runCatching {
            AppUpdateManager.checkNow(applicationContext)
            Result.success()
        }.getOrElse { Result.retry() }
    }
}
''')

# Update screen: always refresh when opened, so stale/empty pending metadata does
# not make a manual user think there is no update information.
update_screen = java / "ui/UpdateScreen.kt"
s = update_screen.read_text()
old = '''    LaunchedEffect(Unit) {\n        AppUpdateManager.schedule(context.applicationContext)\n        update = AppUpdateManager.pending(context.applicationContext)\n    }'''
require_once(s, old, 'UpdateScreen initial metadata load')
new = '''    LaunchedEffect(Unit) {\n        AppUpdateManager.schedule(context.applicationContext)\n        checking = true\n        update = AppUpdateManager.pending(context.applicationContext)\n        runCatching { AppUpdateManager.checkNow(context.applicationContext) }\n            .onSuccess { found ->\n                update = found\n                message = if (found == null) "Du nutzt bereits die aktuelle Version." else "Neue Version ${found.version} gefunden."\n            }\n            .onFailure { message = it.message ?: "Update-Metadaten konnten nicht geladen werden." }\n        checking = false\n    }'''
s = s.replace(old, new, 1)
update_screen.write_text(s)

print("Android v0.4.12 resilient updater patch applied")
