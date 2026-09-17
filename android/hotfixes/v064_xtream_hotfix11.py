#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Version.
# ---------------------------------------------------------------------------
build = root / "app/build.gradle.kts"
replace_once(build, 'versionCode = 613', 'versionCode = 614', 'hotfix11 versionCode')
replace_once(build, 'versionName = "0.6.4.10"', 'versionName = "0.6.4.11"', 'hotfix11 versionName')

home = java / "ui/V044Home.kt"
replace_once(home, "0.6.4.10", "0.6.4.11", "hotfix11 visible version")


# ---------------------------------------------------------------------------
# Android package-install permission. FileProvider itself was added in v0.4.13,
# but Android 8+/Fire OS also needs REQUEST_INSTALL_PACKAGES for a sideloading
# app to be allowed as an installation source.
# ---------------------------------------------------------------------------
manifest = root / "app/src/main/AndroidManifest.xml"
ms = manifest.read_text()
perm = '    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />\n'
if 'android.permission.REQUEST_INSTALL_PACKAGES' not in ms:
    internet = '    <uses-permission android:name="android.permission.INTERNET" />\n'
    if internet not in ms:
        raise SystemExit("AndroidManifest INTERNET permission anchor missing")
    ms = ms.replace(internet, internet + perm, 1)
manifest.write_text(ms)


# ---------------------------------------------------------------------------
# Replace the updater completely. The old updater still queried android-latest,
# expected EpiMediaHub-Android.apk and parsed only three version components.
# Current releases use v0.6.4-test, EpiMediaHub_Android_v0.6.4-test.apk and
# hotfix-style names such as 0.6.4.10. Therefore it could never reliably detect
# the builds we are currently publishing.
# ---------------------------------------------------------------------------
manager = java / "data/UpdateManager.kt"
manager.write_text(r'''package de.epimediahub.app.data

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.Settings
import android.widget.Toast
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
    // This is the same moving test-release that the Android CI pipeline updates.
    private const val RELEASE_API_URL = "https://api.github.com/repos/epimediahub/EpiMediaHub/releases/tags/v0.6.4-test"
    private const val STABLE_APK_NAME = "EpiMediaHub_Android_v0.6.4-test.apk"
    private const val STABLE_APK_URL = "https://github.com/epimediahub/EpiMediaHub/releases/download/v0.6.4-test/EpiMediaHub_Android_v0.6.4-test.apk"
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
        val info = runCatching { parseStored(JSONObject(raw)) }.getOrNull()
            ?: run { clearPending(context); return null }
        return if (isNewer(info.version, BuildConfig.VERSION_NAME)) info
        else {
            clearPending(context)
            null
        }
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
        if (isNewer(info.version, BuildConfig.VERSION_NAME)) {
            savePending(context, info)
            info
        } else {
            clearPending(context)
            null
        }
    }

    private fun fetchLatestInfo(): AppUpdateInfo {
        val raw = fetchJson(RELEASE_API_URL, "application/vnd.github+json")
        return parseRelease(JSONObject(raw))
    }

    suspend fun downloadApk(context: Context, info: AppUpdateInfo): File = withContext(Dispatchers.IO) {
        val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: error("Download-Verzeichnis ist nicht verfügbar.")
        if (!dir.exists() && !dir.mkdirs()) error("Download-Verzeichnis konnte nicht erstellt werden.")

        val safeVersion = info.version.ifBlank { "latest" }.replace(Regex("[^A-Za-z0-9._-]"), "_")
        val target = File(dir, "EpiMediaHub-$safeVersion.apk")
        val partial = File(dir, "EpiMediaHub-$safeVersion.apk.part")

        // Reuse a previously completed and verified APK. This is important when
        // Android first has to send the user to "Unbekannte Apps installieren";
        // the second tap must not download ~170 MB again.
        if (target.isFile && target.length() >= 1024 * 1024) {
            if (info.sha256.isBlank() || sha256(target).equals(info.sha256, ignoreCase = true)) {
                return@withContext target
            }
            target.delete()
        }
        partial.delete()

        val primary = info.url.ifBlank { STABLE_APK_URL }
        val conn = openGet(primary, accept = "application/vnd.android.package-archive", readTimeoutMs = 180000)
        try {
            val code = conn.responseCode
            if (code !in 200..299) error("Update-Download fehlgeschlagen (HTTP $code).")
            val digest = MessageDigest.getInstance("SHA-256")
            conn.inputStream.use { input ->
                partial.outputStream().buffered(256 * 1024).use { output ->
                    val buffer = ByteArray(256 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read <= 0) break
                        output.write(buffer, 0, read)
                        digest.update(buffer, 0, read)
                    }
                    output.flush()
                }
            }
            if (partial.length() < 1024 * 1024) {
                val length = partial.length()
                partial.delete()
                error("Update-Download ist unvollständig ($length Bytes).")
            }
            val actual = digest.digest().joinToString("") { "%02x".format(it) }
            if (info.sha256.isNotBlank() && !actual.equals(info.sha256, ignoreCase = true)) {
                partial.delete()
                error("Sicherheitsprüfung fehlgeschlagen: SHA-256 stimmt nicht.")
            }
            if (target.exists()) target.delete()
            if (!partial.renameTo(target)) {
                partial.copyTo(target, overwrite = true)
                partial.delete()
            }
            if (!target.isFile || target.length() < 1024 * 1024) {
                target.delete()
                error("Update-Datei konnte nicht gespeichert werden.")
            }
            target
        } finally {
            conn.disconnect()
        }
    }

    /**
     * Starts the Android package installer. On Android 8+/Fire OS the app may
     * first need to be authorised as an installation source. In that case we
     * open the correct system page and keep the verified APK cached; after the
     * user returns, pressing Installieren again launches immediately.
     */
    fun installApk(context: Context, apk: File) {
        require(apk.isFile && apk.length() >= 1024 * 1024) { "Update-APK fehlt oder ist unvollständig." }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && !context.packageManager.canRequestPackageInstalls()) {
            Toast.makeText(
                context,
                "Bitte EpiMediaHub das Installieren unbekannter Apps erlauben und danach zurückkehren.",
                Toast.LENGTH_LONG
            ).show()
            val appSource = Intent(
                Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:${context.packageName}")
            ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            val launched = runCatching { context.startActivity(appSource); true }.getOrDefault(false)
            if (!launched) {
                val security = Intent(Settings.ACTION_SECURITY_SETTINGS)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                runCatching { context.startActivity(security) }
                    .getOrElse { error("Installation aus unbekannten Quellen konnte nicht geöffnet werden.") }
            }
            return
        }

        val uri = FileProvider.getUriForFile(
            context,
            "${context.packageName}.fileprovider",
            apk
        )
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(uri, "application/vnd.android.package-archive")
            clipData = android.content.ClipData.newRawUri("EpiMediaHub Update", uri)
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        if (intent.resolveActivity(context.packageManager) == null) {
            error("Auf diesem Gerät wurde kein Android-Paketinstaller gefunden.")
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

    private fun parseStored(json: JSONObject) = AppUpdateInfo(
        version = json.optString("version"),
        versionCode = json.optInt("versionCode", 0),
        url = json.optString("url").ifBlank { STABLE_APK_URL },
        sha256 = json.optString("sha256").removePrefix("sha256:"),
        notes = json.optString("notes")
    ).also {
        require(normalizeVersion(it.version).isNotEmpty()) { "Update-Version fehlt." }
        require(it.url.startsWith("https://")) { "Ungültige Update-URL." }
    }

    private fun parseRelease(json: JSONObject): AppUpdateInfo {
        val candidates = listOf(json.optString("name"), json.optString("tag_name"))
        val version = candidates.asSequence()
            .mapNotNull { Regex("(?:^|[^0-9])(\\d+(?:\\.\\d+){2,3})(?:[^0-9]|$)").find(it)?.groupValues?.get(1) }
            .firstOrNull()
            ?: error("Release-Version fehlt.")

        val assets = json.optJSONArray("assets") ?: error("Release enthält keine Assets.")
        var url = ""
        var digest = ""
        for (i in 0 until assets.length()) {
            val asset = assets.optJSONObject(i) ?: continue
            val name = asset.optString("name")
            val isApk = name == STABLE_APK_NAME || name.endsWith(".apk", ignoreCase = true)
            if (!isApk) continue
            val candidateUrl = asset.optString("browser_download_url")
            if (!candidateUrl.startsWith("https://")) continue
            url = candidateUrl
            digest = asset.optString("digest").removePrefix("sha256:")
            if (name == STABLE_APK_NAME) break
        }
        if (url.isBlank()) url = STABLE_APK_URL

        return AppUpdateInfo(
            version = version,
            versionCode = semanticVersionCode(version),
            url = url,
            sha256 = digest,
            notes = json.optString("body")
        )
    }

    private fun isNewer(remote: String, local: String): Boolean {
        val r = normalizeVersion(remote)
        val l = normalizeVersion(local)
        if (r.isEmpty()) return false
        val size = maxOf(r.size, l.size)
        for (i in 0 until size) {
            val rv = r.getOrElse(i) { 0 }
            val lv = l.getOrElse(i) { 0 }
            if (rv != lv) return rv > lv
        }
        return false
    }

    private fun normalizeVersion(version: String): List<Int> =
        version.trim().removePrefix("v").split('.').mapNotNull { it.toIntOrNull() }

    private fun semanticVersionCode(version: String): Int {
        val p = normalizeVersion(version)
        val major = p.getOrElse(0) { 0 }.coerceIn(0, 99)
        val minor = p.getOrElse(1) { 0 }.coerceIn(0, 99)
        val patch = p.getOrElse(2) { 0 }.coerceIn(0, 99)
        val hotfix = p.getOrElse(3) { 0 }.coerceIn(0, 99)
        return major * 1_000_000 + minor * 10_000 + patch * 100 + hotfix
    }

    private fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered(256 * 1024).use { input ->
            val buffer = ByteArray(256 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    private fun fetchJson(url: String, accept: String = "application/json"): String {
        val conn = openGet(url, accept = accept, readTimeoutMs = 20000)
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
        repeat(10) {
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


checks = [
    (build, 'versionName = "0.6.4.11"'),
    (build, 'versionCode = 614'),
    (manifest, 'android.permission.REQUEST_INSTALL_PACKAGES'),
    (manager, 'releases/tags/v0.6.4-test'),
    (manager, 'EpiMediaHub_Android_v0.6.4-test.apk'),
    (manager, 'private fun isNewer(remote: String, local: String): Boolean'),
    (manager, 'Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES'),
    (manager, 'context.packageManager.canRequestPackageInstalls()'),
    (manager, 'FileProvider.getUriForFile'),
    (manager, 'info.sha256.isBlank() || sha256(target).equals(info.sha256, ignoreCase = true)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing hotfix11 updater marker {marker} in {path}")

print("Android v0.6.4.11 current-release updater, cached verified APK and Fire TV install-source handling applied")
