package de.epimediahub.app.data

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
    private const val MANIFEST_URL = "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/android/update.json"
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
            ExistingPeriodicWorkPolicy.UPDATE,
            request
        )
    }

    fun pending(context: Context): AppUpdateInfo? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw = prefs.getString(KEY_PENDING, null) ?: return null
        return runCatching { parse(JSONObject(raw)) }.getOrNull()?.also {
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
        val json = fetchJson(MANIFEST_URL)
        val info = parse(JSONObject(json))
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

    suspend fun downloadApk(context: Context, info: AppUpdateInfo): File = withContext(Dispatchers.IO) {
        val dir = context.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS)
            ?: error("Download-Verzeichnis ist nicht verfügbar.")
        if (!dir.exists()) dir.mkdirs()
        val file = File(dir, "EpiMediaHub-${info.version}.apk")
        if (file.exists()) file.delete()

        val conn = (URL(info.url).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 15000
            readTimeout = 30000
            requestMethod = "GET"
            setRequestProperty("User-Agent", "EpiMediaHub/${BuildConfig.VERSION_NAME}")
        }
        try {
            val code = conn.responseCode
            if (code !in 200..299) error("Update-Download fehlgeschlagen (HTTP $code).")
            val digest = MessageDigest.getInstance("SHA-256")
            conn.inputStream.use { input ->
                file.outputStream().use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read <= 0) break
                        output.write(buffer, 0, read)
                        digest.update(buffer, 0, read)
                    }
                }
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

    private fun parse(json: JSONObject) = AppUpdateInfo(
        version = json.optString("version"),
        versionCode = json.optInt("versionCode"),
        url = json.optString("url"),
        sha256 = json.optString("sha256"),
        notes = json.optString("notes")
    ).also {
        require(it.version.isNotBlank()) { "Update-Version fehlt." }
        require(it.versionCode > 0) { "Update-VersionCode fehlt." }
        require(it.url.startsWith("https://")) { "Ungültige Update-URL." }
    }

    private fun fetchJson(url: String): String {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = true
            connectTimeout = 10000
            readTimeout = 10000
            requestMethod = "GET"
            setRequestProperty("User-Agent", "EpiMediaHub/${BuildConfig.VERSION_NAME}")
            setRequestProperty("Cache-Control", "no-cache")
        }
        try {
            val code = conn.responseCode
            if (code !in 200..299) error("Update-Prüfung fehlgeschlagen (HTTP $code).")
            return conn.inputStream.bufferedReader().use { it.readText() }
        } finally {
            conn.disconnect()
        }
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
