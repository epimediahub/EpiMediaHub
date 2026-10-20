#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


# ---------------------------------------------------------------------------
# Version metadata.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
require_once(s, 'versionCode = 615', 'v0.6.4.12 versionCode')
require_once(s, 'versionName = "0.6.4.12"', 'v0.6.4.12 versionName')
s = s.replace('versionCode = 615', 'versionCode = 616', 1)
s = s.replace('versionName = "0.6.4.12"', 'versionName = "0.6.4.13"', 1)
gradle.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.6.4.12", "0.6.4.13"))


# ---------------------------------------------------------------------------
# Dashboard 0.7 provisioning / sync.
#
# The dashboard currently exposes:
#   POST /v1/setup/redeem
#   POST /v1/setup/redeem-token
#   GET  /v1/device/config?version=<known>
#   POST /v1/device/sync-result
#
# Keep the public API used by the existing Compose screens, but make applying a
# remote playlist transactional and self-healing. The managed dashboard profile
# is replaced in-place while locally created playlists are preserved.
# ---------------------------------------------------------------------------
(java / "data/SetupCodeProvisioning.kt").write_text(r'''package de.epimediahub.app.data

import android.content.Context
import android.provider.Settings
import de.epimediahub.app.model.PlaylistProfile
import de.epimediahub.app.model.PlaylistType
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.Locale
import java.util.UUID

sealed class SetupCodeResult {
    data class Success(val payload: JSONObject) : SetupCodeResult()
    data class Error(val message: String) : SetupCodeResult()
}

sealed class DeviceSyncResult {
    data class Success(
        val changed: Boolean,
        val configVersion: Int,
        val playlistUrl: String?
    ) : DeviceSyncResult()
    data class Error(val message: String, val retryable: Boolean = true) : DeviceSyncResult()
}

object SetupCodeProvisioning {
    const val PRODUCTION_BASE_URL = "https://setup.epimediahub.com"

    private const val PREFS = "epimediahub_provisioning"
    private const val KEY_PAYLOAD = "provisioning_payload"
    private const val KEY_DEVICE_ID = "stable_device_id"
    private const val KEY_BASE_URL = "provisioning_base_url"
    private const val MANAGED_PROFILE_ID = "managed-dashboard"

    fun rawCode(raw: String): String = raw
        .uppercase(Locale.ROOT)
        .replace(Regex("[^A-Z0-9]"), "")
        .take(12)

    fun normalize(raw: String): String = rawCode(raw).chunked(4).joinToString("-")
    fun isValid(code: String): Boolean = rawCode(code).length == 12

    fun deviceId(context: Context): String {
        val androidId = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID
        )?.trim().orEmpty()
        if (androidId.isNotBlank() && androidId.lowercase(Locale.ROOT) != "9774d56d682e549c") {
            return "android-$androidId"
        }
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY_DEVICE_ID, null)?.takeIf { it.isNotBlank() }?.let { return it }
        val generated = "android-" + UUID.randomUUID().toString()
        prefs.edit().putString(KEY_DEVICE_ID, generated).commit()
        return generated
    }

    private fun cleanBase(baseUrl: String): String? {
        val base = baseUrl.trim().trimEnd('/')
        if (base.startsWith("https://")) return base
        // Explicit development escape hatch used by the existing Tailscale setup.
        if (base.startsWith("http://100.")) return base
        return null
    }

    private fun connection(
        url: String,
        method: String,
        sessionToken: String? = null
    ): HttpURLConnection = (URL(url).openConnection() as HttpURLConnection).apply {
        requestMethod = method
        connectTimeout = 10_000
        readTimeout = 15_000
        useCaches = false
        setRequestProperty("Accept", "application/json")
        setRequestProperty("Cache-Control", "no-cache")
        if (method == "POST") {
            doOutput = true
            setRequestProperty("Content-Type", "application/json; charset=utf-8")
        }
        if (!sessionToken.isNullOrBlank()) {
            setRequestProperty("Authorization", "Bearer $sessionToken")
        }
    }

    private fun read(conn: HttpURLConnection, status: Int): String =
        (if (status in 200..299) conn.inputStream else conn.errorStream)
            ?.bufferedReader()
            ?.use { it.readText() }
            .orEmpty()

    private fun postActivation(
        context: Context,
        baseUrl: String,
        path: String,
        key: String,
        value: String
    ): SetupCodeResult {
        val base = cleanBase(baseUrl)
            ?: return SetupCodeResult.Error("Provisionierungsserver nicht sicher konfiguriert")
        var conn: HttpURLConnection? = null
        return try {
            conn = connection(base + path, "POST")
            val body = JSONObject()
                .put(key, value)
                .put("device_id", deviceId(context))
                .put("platform", "android")
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            val status = conn.responseCode
            val text = read(conn, status)
            when (status) {
                in 200..299 -> {
                    val payload = JSONObject(text)
                    val config = payload.optJSONObject("config") ?: JSONObject()
                    val applyError = applyConfigToApp(context, config)
                    if (applyError != null) {
                        SetupCodeResult.Error(applyError)
                    } else {
                        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                            .edit()
                            .putString(KEY_PAYLOAD, payload.toString())
                            .putString(KEY_BASE_URL, base)
                            .commit()
                        DashboardSyncWorker.schedule(context.applicationContext)
                        SetupCodeResult.Success(payload)
                    }
                }
                404 -> SetupCodeResult.Error("Einrichtungscode ungültig")
                409 -> SetupCodeResult.Error("Einrichtung wurde bereits verwendet")
                410 -> SetupCodeResult.Error("Einrichtungscode ist abgelaufen")
                else -> SetupCodeResult.Error("Serverfehler ($status)")
            }
        } catch (_: Exception) {
            SetupCodeResult.Error("Provisionierungsserver nicht erreichbar")
        } finally {
            conn?.disconnect()
        }
    }

    fun redeem(context: Context, baseUrl: String, rawCode: String): SetupCodeResult {
        val code = normalize(rawCode)
        if (!isValid(code)) return SetupCodeResult.Error("Einrichtungscode ungültig")
        return postActivation(context, baseUrl, "/v1/setup/redeem", "code", code)
    }

    fun redeemToken(context: Context, baseUrl: String, token: String): SetupCodeResult {
        if (token.isBlank()) return SetupCodeResult.Error("Aktivierungslink ungültig")
        return postActivation(context, baseUrl, "/v1/setup/redeem-token", "token", token)
    }

    fun savedPayload(context: Context): JSONObject? =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_PAYLOAD, null)
            ?.let { runCatching { JSONObject(it) }.getOrNull() }

    fun playlistUrl(context: Context): String? =
        savedPayload(context)?.optJSONObject("config")?.optString("playlist_url")?.takeIf { it.isNotBlank() }

    fun sessionToken(context: Context): String? =
        savedPayload(context)?.optString("session_token")?.takeIf { it.isNotBlank() }

    fun provisioningBaseUrl(context: Context): String =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_BASE_URL, null)
            ?.takeIf { cleanBase(it) != null }
            ?: PRODUCTION_BASE_URL

    fun configVersion(context: Context): Int = savedPayload(context)?.optInt("config_version", 0) ?: 0

    fun sync(context: Context): DeviceSyncResult {
        val token = sessionToken(context)
            ?: return DeviceSyncResult.Error("Gerät ist noch nicht eingerichtet", retryable = false)
        val base = provisioningBaseUrl(context)
        val knownVersion = configVersion(context)
        val versionQuery = URLEncoder.encode(knownVersion.toString(), "UTF-8")
        var conn: HttpURLConnection? = null
        return try {
            conn = connection("$base/v1/device/config?version=$versionQuery", "GET", token)
            val status = conn.responseCode
            val text = read(conn, status)
            if (status !in 200..299) {
                return DeviceSyncResult.Error(
                    if (status == 401) "Gerät ist nicht mehr freigegeben" else "Sync-Serverfehler ($status)",
                    retryable = status != 401 && status !in 400..499
                )
            }

            val remote = JSONObject(text)
            val version = remote.optInt("config_version", knownVersion)
            val config = remote.optJSONObject("config") ?: JSONObject()
            val serverChanged = remote.optBoolean("changed", version != knownVersion)
            val localManagedMissing = PrefsRepository(context)
                .loadPlaylists()
                .none { it.id == MANAGED_PROFILE_ID }
            val shouldApply = serverChanged || version != knownVersion || localManagedMissing

            if (shouldApply) {
                val applyError = applyConfigToApp(context, config)
                if (applyError != null) {
                    reportSync(base, token, version, "error", "Konfiguration konnte nicht angewendet werden")
                    return DeviceSyncResult.Error(applyError, retryable = false)
                }
            }

            val old = savedPayload(context) ?: JSONObject()
            val merged = JSONObject(old.toString())
                .put("config_version", version)
                .put("config", config)
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
                .edit()
                .putString(KEY_PAYLOAD, merged.toString())
                .putString(KEY_BASE_URL, base)
                .commit()
            reportSync(base, token, version, "ok", "")

            DeviceSyncResult.Success(
                changed = shouldApply,
                configVersion = version,
                playlistUrl = config.optString("playlist_url").takeIf { it.isNotBlank() }
            )
        } catch (_: Exception) {
            DeviceSyncResult.Error("Synchronisierung fehlgeschlagen", retryable = true)
        } finally {
            conn?.disconnect()
        }
    }

    private fun isHttpUrl(value: String): Boolean = runCatching {
        val url = URL(value)
        url.protocol.equals("http", true) || url.protocol.equals("https", true)
    }.getOrDefault(false)

    /** Returns null on success and a user-safe error message on validation failure. */
    private fun applyConfigToApp(context: Context, config: JSONObject): String? {
        val type = config.optString("playlist_type", "").uppercase(Locale.ROOT)
        val name = config.optString("playlist_name", "EpiMediaHub Dashboard")
            .ifBlank { "EpiMediaHub Dashboard" }
        val url = config.optString("playlist_url", "").trim()
        val server = config.optString("xtream_server", "").trim().trimEnd('/')
        val username = config.optString("xtream_username", "").trim()
        val password = config.optString("xtream_password", "")
        val output = config.optString("xtream_output", "ts").ifBlank { "ts" }

        val profile = when (type) {
            "XTREAM" -> {
                if (!isHttpUrl(server) || username.isBlank() || password.isBlank()) {
                    return "Dashboard-Xtream-Konfiguration ist unvollständig"
                }
                PlaylistProfile(
                    MANAGED_PROFILE_ID,
                    name,
                    "",
                    PlaylistType.XTREAM,
                    server,
                    username,
                    password,
                    output
                )
            }
            "M3U" -> {
                if (!isHttpUrl(url)) return "Dashboard-M3U-Konfiguration ist ungültig"
                PlaylistProfile(MANAGED_PROFILE_ID, name, url, PlaylistType.M3U)
            }
            else -> return "Dashboard-Konfiguration enthält keinen unterstützten Playlist-Typ"
        }

        return try {
            val repo = PrefsRepository(context)
            val local = repo.loadPlaylists().filterNot { it.id == MANAGED_PROFILE_ID }
            repo.savePlaylists(listOf(profile) + local)
            repo.activePlaylistId = MANAGED_PROFILE_ID
            null
        } catch (_: Exception) {
            "Dashboard-Konfiguration konnte nicht gespeichert werden"
        }
    }

    private fun reportSync(
        base: String,
        token: String,
        version: Int,
        statusValue: String,
        error: String
    ) {
        var conn: HttpURLConnection? = null
        try {
            conn = connection(base.trimEnd('/') + "/v1/device/sync-result", "POST", token)
            val body = JSONObject()
                .put("config_version", version)
                .put("status", statusValue)
                .put("error", error.take(240))
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            conn.responseCode
        } catch (_: Exception) {
            // Reporting must never make an otherwise successful config sync fail.
        } finally {
            conn?.disconnect()
        }
    }
}
''')


# ---------------------------------------------------------------------------
# Automatic Dashboard sync: an immediate job on app start and a network-bound
# periodic job. WorkManager's minimum periodic interval is 15 minutes.
# ---------------------------------------------------------------------------
(java / "data/DashboardSyncWorker.kt").write_text(r'''package de.epimediahub.app.data

import android.content.Context
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

class DashboardSyncWorker(
    appContext: Context,
    params: WorkerParameters
) : CoroutineWorker(appContext, params) {
    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        if (SetupCodeProvisioning.sessionToken(applicationContext).isNullOrBlank()) {
            return@withContext Result.success()
        }
        when (val result = SetupCodeProvisioning.sync(applicationContext)) {
            is DeviceSyncResult.Success -> Result.success()
            is DeviceSyncResult.Error -> if (result.retryable) Result.retry() else Result.success()
        }
    }

    companion object {
        private const val PERIODIC_NAME = "dashboard-config-sync"
        private const val IMMEDIATE_NAME = "dashboard-config-sync-now"

        fun schedule(context: Context) {
            val app = context.applicationContext
            if (SetupCodeProvisioning.sessionToken(app).isNullOrBlank()) return
            val constraints = Constraints.Builder()
                .setRequiredNetworkType(NetworkType.CONNECTED)
                .build()

            val periodic = PeriodicWorkRequestBuilder<DashboardSyncWorker>(15, TimeUnit.MINUTES)
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(app).enqueueUniquePeriodicWork(
                PERIODIC_NAME,
                ExistingPeriodicWorkPolicy.KEEP,
                periodic
            )

            val immediate = OneTimeWorkRequestBuilder<DashboardSyncWorker>()
                .setConstraints(constraints)
                .build()
            WorkManager.getInstance(app).enqueueUniqueWork(
                IMMEDIATE_NAME,
                ExistingWorkPolicy.REPLACE,
                immediate
            )
        }
    }
}
''')


# Schedule a self-healing sync whenever the app starts. Existing dashboard-linked
# installations therefore begin using Dashboard 0.7 without reconnecting.
main = java / "MainActivity.kt"
ms = main.read_text()
import_anchor = 'import androidx.activity.result.contract.ActivityResultContracts\n'
if 'import de.epimediahub.app.data.DashboardSyncWorker\n' not in ms:
    require_once(ms, import_anchor, 'MainActivity import anchor')
    ms = ms.replace(import_anchor, import_anchor + 'import de.epimediahub.app.data.DashboardSyncWorker\n', 1)
start_anchor = '        super.onCreate(savedInstanceState)\n'
if 'DashboardSyncWorker.schedule(applicationContext)' not in ms:
    require_once(ms, start_anchor, 'MainActivity onCreate anchor')
    ms = ms.replace(
        start_anchor,
        start_anchor + '        DashboardSyncWorker.schedule(applicationContext)\n',
        1,
    )
main.write_text(ms)

print("Android v0.6.4.13 Dashboard 0.7 sync installed")
