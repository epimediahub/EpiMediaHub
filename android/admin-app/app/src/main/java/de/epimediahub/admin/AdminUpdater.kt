package de.epimediahub.admin

import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import androidx.core.content.FileProvider
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest
import kotlin.concurrent.thread

/** HTTPS-only authenticated private release updater; Android always asks before installing. */
object AdminUpdater {
    data class Release(val versionCode: Long, val name: String, val bytes: Long, val sha256: String)
    private const val BASE = "https://admin.epimediahub.com"
    private const val MAX_BYTES = 100L * 1024 * 1024
    private val main = Handler(Looper.getMainLooper())

    private fun connection(path: String, cookie: String): HttpURLConnection {
        require(path == "/admin/mobile/update/status" || path == "/admin/mobile/update/apk")
        require(cookie.isNotBlank())
        return (URL(BASE + path).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = false
            connectTimeout = 8000
            readTimeout = 15000
            setRequestProperty("Cookie", cookie)
            setRequestProperty("Accept", if (path.endsWith("/apk"))
                "application/vnd.android.package-archive" else "application/json")
            setRequestProperty("Cache-Control", "no-store")
        }
    }

    private fun result(onResult: (Release?, String) -> Unit, release: Release?, message: String) {
        main.post { onResult(release, message) }
    }

    fun check(cookie: String, currentVersion: Long, onResult: (Release?, String) -> Unit) {
        if (cookie.isBlank()) {
            result(onResult, null, "Bitte zuerst im Dashboard anmelden.")
            return
        }
        thread(name = "epimediahub-admin-update-check") {
            var con: HttpURLConnection? = null
            try {
                con = connection("/admin/mobile/update/status", cookie)
                if (con.responseCode != 200) {
                    result(onResult, null, "Der private Update-Server ist noch nicht eingerichtet.")
                    return@thread
                }
                val raw = con.inputStream.bufferedReader().use { it.readText().take(4096) }
                val data = JSONObject(raw)
                if (!data.optBoolean("available", false)) {
                    result(onResult, null, "Noch keine signierte Admin-Version veröffentlicht.")
                    return@thread
                }
                val version = data.getLong("version_code")
                val name = data.getString("version_name")
                val size = data.getLong("size_bytes")
                val hash = data.getString("sha256")
                if (data.getString("package") != "de.epimediahub.admin" ||
                    version <= 0 || size !in 1024..MAX_BYTES ||
                    !hash.matches(Regex("[0-9a-f]{64}")) ||
                    !name.matches(Regex("[A-Za-z0-9._-]{1,48}"))) {
                    result(onResult, null, "Update-Metadaten wurden aus Sicherheitsgründen abgelehnt.")
                    return@thread
                }
                if (version <= currentVersion) {
                    result(onResult, null, "Die Admin-App ist auf dem aktuellen Stand.")
                    return@thread
                }
                result(onResult, Release(version, name, size, hash),
                    "Admin-Update $name verfügbar.")
            } catch (_: Exception) {
                result(onResult, null, "Update-Server momentan nicht erreichbar.")
            } finally {
                con?.disconnect()
            }
        }
    }

    private fun signaturesMatch(context: Context, apk: File, version: Long): Boolean {
        val manager = context.packageManager
        @Suppress("DEPRECATION")
        val flags = if (Build.VERSION.SDK_INT >= 28)
            PackageManager.GET_SIGNING_CERTIFICATES else PackageManager.GET_SIGNATURES
        @Suppress("DEPRECATION")
        val installed = manager.getPackageInfo(context.packageName, flags)
        @Suppress("DEPRECATION")
        val candidate = manager.getPackageArchiveInfo(apk.absolutePath, flags) ?: return false
        if (candidate.packageName != context.packageName) return false
        @Suppress("DEPRECATION")
        val code = if (Build.VERSION.SDK_INT >= 28) candidate.longVersionCode
                   else candidate.versionCode.toLong()
        if (code != version) return false
        @Suppress("DEPRECATION")
        val a = if (Build.VERSION.SDK_INT >= 28)
            installed.signingInfo?.apkContentsSigners else installed.signatures
        @Suppress("DEPRECATION")
        val b = if (Build.VERSION.SDK_INT >= 28)
            candidate.signingInfo?.apkContentsSigners else candidate.signatures
        if (a.isNullOrEmpty() || b.isNullOrEmpty() || a.size != b.size) return false
        return a.map { it.toCharsString() }.toSet() == b.map { it.toCharsString() }.toSet()
    }

    fun downloadAndInstall(
        context: Context, cookie: String, release: Release, onResult: (String) -> Unit
    ) {
        val app = context.applicationContext
        if (cookie.isBlank()) {
            main.post { onResult("Bitte zuerst im Dashboard anmelden.") }
            return
        }
        if (Build.VERSION.SDK_INT >= 26 && !app.packageManager.canRequestPackageInstalls()) {
            main.post {
                onResult("Einmalig die Installation von Updates für diese Admin-App erlauben.")
                val settings = Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                    Uri.parse("package:" + app.packageName)).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }
                try { app.startActivity(settings) }
                catch (_: Exception) { onResult("Installationsberechtigung konnte nicht geöffnet werden.") }
            }
            return
        }
        thread(name = "epimediahub-admin-update-download") {
            var con: HttpURLConnection? = null
            var file: File? = null
            try {
                val dir = File(app.cacheDir, "admin-updates")
                if (!dir.isDirectory && !dir.mkdirs()) throw IllegalStateException("No private cache")
                val targetFile = File(dir, "epimediahub-admin-next.apk")
                file = targetFile
                con = connection("/admin/mobile/update/apk", cookie)
                if (con.responseCode != 200 ||
                    con.contentType?.substringBefore(";") != "application/vnd.android.package-archive") {
                    throw IllegalStateException("Invalid private update response")
                }
                val digest = MessageDigest.getInstance("SHA-256")
                var total = 0L
                con.inputStream.use { source ->
                    targetFile.outputStream().use { target ->
                        val buffer = ByteArray(64 * 1024)
                        while (true) {
                            val len = source.read(buffer)
                            if (len == -1) break
                            total += len
                            if (total > MAX_BYTES || total > release.bytes) {
                                throw IllegalStateException("Update exceeds approved size")
                            }
                            digest.update(buffer, 0, len)
                            target.write(buffer, 0, len)
                        }
                    }
                }
                val actual = digest.digest().joinToString("") { "%02x".format(it) }
                if (total != release.bytes || actual != release.sha256 ||
                    !signaturesMatch(app, targetFile, release.versionCode)) {
                    throw SecurityException("Update identity failed")
                }
                val uri = FileProvider.getUriForFile(
                    app, app.packageName + ".adminupdates", targetFile
                )
                val installer = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION)
                }
                main.post {
                    onResult("Android fragt jetzt nach deiner Bestätigung für das Update.")
                    app.startActivity(installer)
                }
            } catch (_: Exception) {
                file?.delete()
                main.post { onResult("Update konnte nicht sicher geprüft oder installiert werden.") }
            } finally {
                con?.disconnect()
            }
        }
    }
}
