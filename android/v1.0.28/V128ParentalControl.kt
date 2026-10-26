package de.epimediahub.app.data

import android.content.Context
import android.os.Build
import android.util.Base64
import de.epimediahub.app.model.MediaCategory
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

data class V128ParentalSettings(
    val hasPin: Boolean = false,
    val lockAdult: Boolean = false,
    val lockMenu: Boolean = false,
    val lockUnrated: Boolean = false
)

data class V128PinPrompt(val id: Long, val title: String)
data class V128PinResult(val accepted: Boolean, val message: String = "")

/** Customer-chosen PIN, independent of the existing skin/maintenance access codes. */
class V128ParentalControl(context: Context, private val now: () -> Long = System::currentTimeMillis) {
    private val prefs = context.applicationContext.getSharedPreferences("epi_parental_v128", Context.MODE_PRIVATE)

    fun settings() = V128ParentalSettings(
        hasPin = prefs.contains("hash"),
        lockAdult = prefs.contains("hash") && prefs.getBoolean("adult", false),
        lockMenu = prefs.contains("hash") && prefs.getBoolean("menu", false),
        lockUnrated = prefs.contains("hash") && prefs.getBoolean("unrated", false)
    )

    fun setPin(pin: String) {
        require(validPin(pin)) { "Die PIN muss aus genau vier Ziffern bestehen." }
        val salt = ByteArray(24).also { SecureRandom().nextBytes(it) }
        val algorithm = if (Build.VERSION.SDK_INT >= 26) "PBKDF2WithHmacSHA256" else "PBKDF2WithHmacSHA1"
        val hash = derive(pin, salt, algorithm)
        check(prefs.edit().putString("salt", encode(salt)).putString("hash", encode(hash))
            .putString("algorithm", algorithm).remove("failures").remove("blocked_until").commit())
    }

    fun update(adult: Boolean, menu: Boolean, unrated: Boolean) {
        check(settings().hasPin)
        prefs.edit().putBoolean("adult", adult).putBoolean("menu", menu).putBoolean("unrated", unrated).apply()
    }

    fun removePin() { check(prefs.edit().clear().commit()) }

    fun verify(pin: String): V128PinResult {
        val blockedUntil = prefs.getLong("blocked_until", 0L)
        if (blockedUntil > now()) {
            val seconds = ((blockedUntil - now() + 999L) / 1000L).coerceAtLeast(1L)
            return V128PinResult(false, "Bitte in $seconds Sekunden erneut versuchen.")
        }
        if (!settings().hasPin) return V128PinResult(false, "Es wurde noch keine PIN festgelegt.")
        val accepted = validPin(pin) && runCatching {
            val expected = decode(prefs.getString("hash", "").orEmpty())
            val actual = derive(pin, decode(prefs.getString("salt", "").orEmpty()),
                prefs.getString("algorithm", "PBKDF2WithHmacSHA1").orEmpty())
            MessageDigest.isEqual(expected, actual)
        }.getOrDefault(false)
        if (accepted) {
            prefs.edit().remove("failures").remove("blocked_until").apply()
            return V128PinResult(true)
        }
        val failures = prefs.getInt("failures", 0) + 1
        val edit = prefs.edit().putInt("failures", failures)
        if (failures >= 5) {
            val delayMs = (30_000L * (1L shl ((failures - 5) / 5).coerceAtMost(4))).coerceAtMost(300_000L)
            edit.putLong("blocked_until", now() + delayMs)
        }
        edit.apply()
        return V128PinResult(false, if (failures >= 5) "PIN falsch. Bitte kurz warten und erneut versuchen." else "PIN falsch. Bitte erneut eingeben.")
    }

    private fun derive(pin: String, salt: ByteArray, algorithm: String): ByteArray {
        require(salt.size == 24)
        require(algorithm == "PBKDF2WithHmacSHA1" || algorithm == "PBKDF2WithHmacSHA256")
        val spec = PBEKeySpec(pin.toCharArray(), salt, 100_000, 256)
        return try { SecretKeyFactory.getInstance(algorithm).generateSecret(spec).encoded }
        finally { spec.clearPassword() }
    }

    private fun encode(bytes: ByteArray) = Base64.encodeToString(bytes, Base64.NO_WRAP)
    private fun decode(value: String) = Base64.decode(value, Base64.NO_WRAP)
    companion object {
        fun validPin(pin: String): Boolean = pin.length == 4 && pin.all { it in '0'..'9' }
    }
}

object V128AdultContent {
    private val adultWords = Regex("(?i)(?:\\b(?:adult|adults|erwachsene[nr]?|xxx|porn\\w*|erotik|erotic|hentai|nc[- ]?17|tv[- ]?ma)\\b|\\b(?:fsk|ab)\\s*18\\b|\\b18\\s*\\+)")
    private val ageFields = listOf("age_rating", "age_limit", "age_restriction", "minimum_age", "required_age", "parental_rating", "certification", "mpaa", "fsk", "content_rating")

    fun marked(text: String): Boolean = adultWords.containsMatchIn(text)
    fun providerAdult(data: JSONObject): Boolean = listOf("is_adult", "adult").any {
        data.optString(it).trim().lowercase() in setOf("1", "true", "yes")
    }
    fun providerAge(data: JSONObject): Int = ageFields.mapNotNull { key ->
        val raw = data.optString(key).trim()
        when {
            marked(raw) -> 18
            raw.matches(Regex("(?:0|6|7|10|12|13|14|15|16|17|18|21)\\+?")) -> raw.removeSuffix("+").toInt()
            else -> Regex("(?i)\\b(?:FSK|ab|age|rated)\\s*[:=-]?\\s*(0|6|12|16|18)\\b").find(raw)?.groupValues?.get(1)?.toInt()
        }
    }.maxOrNull() ?: -1

    fun bind(entries: List<MediaEntry>, categories: List<MediaCategory>): List<MediaEntry> {
        val names = categories.associateBy { it.id }
        return entries.map { item ->
            val category = names[item.categoryId]
            val name = category?.name ?: item.categoryName
            item.copy(categoryName = name, adult = item.adult || category?.adult == true || marked(name))
        }
    }

    fun restricted(item: MediaEntry, settings: V128ParentalSettings): Boolean {
        if (!settings.hasPin || !settings.lockAdult) return false
        return item.adult || item.ageRating >= 18 || marked(item.name) || marked(item.categoryName) ||
            marked(item.genre) || marked(item.rating) ||
            (settings.lockUnrated && item.kind != MediaKind.LIVE && item.ageRating < 0)
    }

    fun scope(item: MediaEntry): String = if (item.kind == MediaKind.EPISODE || item.kind == MediaKind.SERIES) {
        "series:${item.sourceProfileId}:${item.seriesId.ifBlank { item.id }}"
    } else item.resumeKey
}
