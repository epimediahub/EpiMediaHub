package de.epimediahub.app.data

import android.content.Context
import de.epimediahub.app.model.PlaylistProfile
import de.epimediahub.app.model.PlaylistType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.security.MessageDigest
import java.text.ParsePosition
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.TimeZone

internal data class V132PlaylistExpiry(val untilMs: Long? = null, val unlimited: Boolean = false) {
    fun label(locale: Locale, nowMs: Long): String {
        val words = when (locale.language) {
            "it" -> listOf("Scade il", "Scaduta il", "Senza scadenza", "Scadenza non disponibile")
            "tr" -> listOf("Son tarih", "Süresi doldu", "Süresiz", "Bitiş tarihi mevcut değil")
            "fr" -> listOf("Valable jusqu’au", "Expirée le", "Sans expiration", "Expiration indisponible")
            "es" -> listOf("Válida hasta", "Caducó el", "Sin caducidad", "Caducidad no disponible")
            "en" -> listOf("Expires", "Expired", "No expiry date", "Expiry unavailable")
            else -> listOf("Gültig bis", "Abgelaufen am", "Ohne Ablaufdatum", "Ablaufdatum nicht verfügbar")
        }
        val end = untilMs
        return when {
            end != null -> "${words[if (end <= nowMs) 1 else 0]} ${SimpleDateFormat("dd.MM.yyyy", locale).format(Date(end))}"
            unlimited -> words[2]
            else -> words[3]
        }
    }
}

/** Provider subscription expiry, separate from the app licence. */
internal class V132PlaylistExpiryRepository(context: Context) {
    private val cache = context.applicationContext.getSharedPreferences("v132_playlist_expiry", Context.MODE_PRIVATE)
    companion object {
        private const val FRESH_MS = 6*60*60*1000L
        private const val RETRY_MS = 10*60*1000L
        private const val MAX_RESPONSE = 64*1024
        internal fun identity(profile: PlaylistProfile?): String {
            if (profile == null) return "none"
            val value = listOf(profile.id, profile.type.name, profile.server, profile.username,
                profile.password, profile.originalUrl).joinToString("\u0000")
            return MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") { "%02x".format(it) }
        }
        internal fun providerProfile(profile: PlaylistProfile?): PlaylistProfile? {
            if (profile == null) return null
            val normalized = if (profile.type == PlaylistType.XTREAM) profile else
                runCatching { PlaylistParser.parse(profile.name, profile.originalUrl).copy(id = profile.id) }.getOrNull()
            return normalized?.takeIf { it.type == PlaylistType.XTREAM && it.server.isNotBlank() &&
                it.username.isNotBlank() && it.password.isNotBlank() }
        }
        internal fun parse(root: JSONObject): V132PlaylistExpiry {
            val info = root.optJSONObject("user_info") ?: return V132PlaylistExpiry()
            if (!info.has("exp_date")) return V132PlaylistExpiry()
            val raw = info.optString("exp_date").trim()
            val active = info.optString("auth") == "1" && info.optString("status").equals("Active", true)
            if (info.isNull("exp_date") || raw.lowercase(Locale.ROOT) in setOf("", "null", "0", "-1", "unlimited", "lifetime", "never"))
                return V132PlaylistExpiry(unlimited = active)
            val number = raw.toLongOrNull()
            val timestamp = if (number != null) {
                if (number in 1..32_503_680_000L) number*1000L else number
            } else {
                listOf("yyyy-MM-dd'T'HH:mm:ssXXX", "yyyy-MM-dd HH:mm:ss", "yyyy-MM-dd").firstNotNullOfOrNull { pattern ->
                    val formatter = SimpleDateFormat(pattern, Locale.ROOT).apply { isLenient = false; timeZone = TimeZone.getTimeZone("UTC") }
                    val pos = ParsePosition(0)
                    formatter.parse(raw, pos)?.takeIf { pos.index == raw.length }?.time
                }
            }
            return V132PlaylistExpiry(untilMs = timestamp?.takeIf { it in 1..32_503_680_000_000L })
        }
        private fun fetch(profile: PlaylistProfile): JSONObject {
            val encode: (String) -> String = { URLEncoder.encode(it, "UTF-8") }
            val base = PlaylistParser.normalizeXtreamServer(profile.server)
            val url = URL("$base/player_api.php?username=${encode(profile.username)}&password=${encode(profile.password)}")
            require(url.protocol in setOf("http", "https"))
            val connection = (url.openConnection() as HttpURLConnection).apply {
                connectTimeout = 4_000; readTimeout = 6_000
                setRequestProperty("Accept", "application/json"); setRequestProperty("User-Agent", "EpiMediaHub/1.0.32")
            }
            try {
                require(connection.responseCode in 200..299)
                val bytes = connection.inputStream.use { stream ->
                    val out = java.io.ByteArrayOutputStream(); val buffer = ByteArray(4096)
                    while (true) {
                        val count = stream.read(buffer); if (count < 0) break
                        require(out.size()+count <= MAX_RESPONSE); out.write(buffer, 0, count)
                    }
                    out.toByteArray()
                }
                return JSONObject(String(bytes, Charsets.UTF_8))
            } finally { connection.disconnect() }
        }
    }
    private fun saved(profile: PlaylistProfile?): JSONObject? = runCatching {
        JSONObject(cache.getString(identity(profile), "") ?: "")
    }.getOrNull()
    fun cached(profile: PlaylistProfile?): V132PlaylistExpiry {
        val data = saved(profile) ?: return V132PlaylistExpiry()
        return V132PlaylistExpiry(data.optLong("until").takeIf { it > 0 }, data.optBoolean("unlimited"))
    }
    suspend fun refresh(profile: PlaylistProfile?, now: Long = System.currentTimeMillis(),
        load: (PlaylistProfile) -> JSONObject = ::fetch): V132PlaylistExpiry = withContext(Dispatchers.IO) {
        val account = providerProfile(profile) ?: return@withContext V132PlaylistExpiry()
        val key = identity(profile); val previous = saved(profile)
        if (previous != null && now < previous.optLong("nextCheck")) return@withContext cached(profile)
        val response = runCatching { load(account) }.getOrNull(); val result = response?.let(::parse)
        val known = result != null && (result.untilMs != null || result.unlimited)
        val info = response?.optJSONObject("user_info")
        val inactive = info != null && (info.optString("auth") == "0" || info.optString("status").equals("Expired", true))
        val value = if (known) result!! else cached(profile).let { if (inactive) it.copy(unlimited = false) else it }
        val data = JSONObject().put("until", value.untilMs ?: 0L).put("unlimited", value.unlimited)
            .put("nextCheck", now + if (known) FRESH_MS else RETRY_MS)
        val editor = cache.edit()
        if (cache.all.size >= 20 && !cache.contains(key)) {
            cache.all.keys.sortedBy { name -> runCatching { JSONObject(cache.getString(name, "")!!).optLong("nextCheck") }.getOrDefault(0L) }
                .take(cache.all.size-19).forEach { editor.remove(it) }
        }
        editor.putString(key, data.toString()).apply(); value
    }
}
