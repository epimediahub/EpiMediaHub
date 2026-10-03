package de.epimediahub.app.data

import android.content.Context
import android.provider.Settings
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.MessageDigest

enum class V120LicenseKind { CHECKING, TRIAL_ACTIVE, TRIAL_EXPIRED, LIFETIME_ACTIVE, ERROR }

data class V120LicenseState(
    val kind: V120LicenseKind,
    val remainingSeconds: Long? = null,
    val trialExpiresAt: String = "",
    val message: String = ""
) {
    val allowsUse: Boolean get() = kind == V120LicenseKind.TRIAL_ACTIVE || kind == V120LicenseKind.LIFETIME_ACTIVE
    val remainingDays: Long?
        get() = remainingSeconds?.let { if (it <= 0) 0 else (it + 86_399L) / 86_400L }
}

object V120LicenseManager {
    private const val API_URL = "https://api.epimediahub.com/v1/license/status"
    private const val PREFS = "v120_license"
    private const val KEY_PAYLOAD = "payload"
    private const val KEY_CHECKED_AT = "checked_at"
    private const val TRIAL_CACHE_GRACE_MS = 30L * 60L * 1000L

    private fun sha256(value: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    fun trialKey(context: Context): String {
        val secureId = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
            ?.trim().orEmpty()
        val basis = if (secureId.isNotBlank()) "android-secure:$secureId"
        else "install:${SetupCodeProvisioning.deviceId(context)}"
        return sha256("epimediahub-trial-v1|$basis")
    }

    fun deviceId(context: Context): String = SetupCodeProvisioning.deviceId(context)

    fun check(context: Context): V120LicenseState {
        var conn: HttpURLConnection? = null
        return try {
            conn = (URL(API_URL).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 8_000
                readTimeout = 8_000
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                setRequestProperty("Accept", "application/json")
                setRequestProperty("User-Agent", "EpiMediaHub-Android/1.0.20")
            }
            val requestBody = JSONObject()
                .put("device_id", deviceId(context))
                .put("trial_key", trialKey(context))
                .put("platform", "android")
                .toString()
            conn.outputStream.use { it.write(requestBody.toByteArray(Charsets.UTF_8)) }
            val status = conn.responseCode
            val stream = if (status in 200..299) conn.inputStream else conn.errorStream
            val raw = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (status !in 200..299) return cachedOrError(context, "Lizenzserverfehler ($status)")
            val parsed = decode(JSONObject(raw))
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                .putString(KEY_PAYLOAD, raw)
                .putLong(KEY_CHECKED_AT, System.currentTimeMillis())
                .apply()
            parsed
        } catch (_: Exception) {
            cachedOrError(context, "Lizenzserver nicht erreichbar")
        } finally {
            conn?.disconnect()
        }
    }

    fun cached(context: Context): V120LicenseState? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val raw = prefs.getString(KEY_PAYLOAD, null) ?: return null
        return runCatching { decode(JSONObject(raw)) }.getOrNull()
    }

    private fun cachedOrError(context: Context, message: String): V120LicenseState {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val cached = cached(context) ?: return V120LicenseState(V120LicenseKind.ERROR, message = message)
        if (cached.kind == V120LicenseKind.LIFETIME_ACTIVE || cached.kind == V120LicenseKind.TRIAL_EXPIRED) return cached
        if (cached.kind != V120LicenseKind.TRIAL_ACTIVE) return V120LicenseState(V120LicenseKind.ERROR, message = message)
        val checkedAt = prefs.getLong(KEY_CHECKED_AT, 0L)
        val age = System.currentTimeMillis() - checkedAt
        if (checkedAt <= 0L || age < 0L || age > TRIAL_CACHE_GRACE_MS) {
            return V120LicenseState(V120LicenseKind.ERROR, message = message)
        }
        val remaining = (cached.remainingSeconds ?: 0L) - age / 1000L
        return if (remaining > 0L) cached.copy(remainingSeconds = remaining)
        else cached.copy(kind = V120LicenseKind.TRIAL_EXPIRED, remainingSeconds = 0L)
    }

    private fun decode(json: JSONObject): V120LicenseState {
        val remaining = if (json.isNull("remaining_seconds")) null else json.optLong("remaining_seconds")
        val expires = json.optString("trial_expires_at")
        return when (json.optString("status")) {
            "LIFETIME_ACTIVE" -> V120LicenseState(V120LicenseKind.LIFETIME_ACTIVE, null, expires)
            "TRIAL_ACTIVE" -> V120LicenseState(V120LicenseKind.TRIAL_ACTIVE, remaining, expires)
            "TRIAL_EXPIRED" -> V120LicenseState(V120LicenseKind.TRIAL_EXPIRED, 0L, expires)
            else -> V120LicenseState(V120LicenseKind.ERROR, message = "Unbekannter Lizenzstatus")
        }
    }
}
