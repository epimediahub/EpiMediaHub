package de.epimediahub.app.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.Locale

data class V070WeatherSnapshot(
    val temperatureC: Int,
    val description: String,
    val code: Int,
    val city: String,
    val languageCode: String
)

object V070WeatherClient {
    private const val CACHE = "v070_weather"
    private const val CACHE_MAX_AGE = 30L * 60L * 1000L
    private const val KEY_POSTAL = "postal_code"
    private const val KEY_COUNTRY = "country_code"
    private const val KEY_LOCATION = "location_key"

    fun postalCode(context: Context): String =
        context.getSharedPreferences(CACHE, Context.MODE_PRIVATE)
            .getString(KEY_POSTAL, "").orEmpty().trim()

    fun countryCode(context: Context): String =
        context.getSharedPreferences(CACHE, Context.MODE_PRIVATE)
            .getString(KEY_COUNTRY, "DE").orEmpty().trim().uppercase(Locale.ROOT).ifBlank { "DE" }

    fun saveLocation(context: Context, postalCode: String, countryCode: String) {
        val postal = postalCode.trim()
        val country = countryCode.trim().uppercase(Locale.ROOT).ifBlank { "DE" }
        context.getSharedPreferences(CACHE, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_POSTAL, postal)
            .putString(KEY_COUNTRY, country)
            .remove("payload")
            .remove("language")
            .remove(KEY_LOCATION)
            .putLong("time", 0L)
            .apply()
    }

    private fun locationKey(context: Context): String {
        val postal = postalCode(context)
        val country = countryCode(context)
        return if (postal.isBlank()) "auto" else "$postal|$country"
    }

    fun cached(context: Context): V070WeatherSnapshot? {
        val prefs = context.getSharedPreferences(CACHE, Context.MODE_PRIVATE)
        val json = prefs.getString("payload", null) ?: return null
        val lang = menuLanguage(context)
        val key = locationKey(context)
        if (prefs.getString("language", "") != lang) return null
        if (prefs.getString(KEY_LOCATION, "") != key) return null
        return parse(json, lang, postalCode(context))
    }

    suspend fun refresh(context: Context): V070WeatherSnapshot? = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences(CACHE, Context.MODE_PRIVATE)
        val lang = menuLanguage(context)
        val key = locationKey(context)
        val age = System.currentTimeMillis() - prefs.getLong("time", 0L)
        val cachedLanguage = prefs.getString("language", "")
        val cachedLocation = prefs.getString(KEY_LOCATION, "")
        if (age in 0 until CACHE_MAX_AGE && cachedLanguage == lang && cachedLocation == key) {
            return@withContext cached(context)
        }

        runCatching {
            val postal = postalCode(context)
            val country = countryCode(context)
            val encodedLanguage = URLEncoder.encode(lang, "UTF-8")
            val path = if (postal.isBlank()) "" else "/" + URLEncoder.encode("$postal,$country", "UTF-8").replace("+", "%20")
            val connection = (
                URL("https://wttr.in$path?format=j1&lang=$encodedLanguage")
                    .openConnection() as HttpURLConnection
            ).apply {
                connectTimeout = 7000
                readTimeout = 7000
                useCaches = true
                setRequestProperty("Accept", "application/json")
                setRequestProperty("Accept-Language", lang)
                setRequestProperty("User-Agent", "EpiMediaHub-Android/0.8.1")
            }

            try {
                if (connection.responseCode !in 200..299) {
                    error("weather HTTP ${connection.responseCode}")
                }
                val body = connection.inputStream.bufferedReader().use { it.readText() }
                val parsed = parse(body, lang, postal) ?: error("weather response incomplete")
                prefs.edit()
                    .putString("payload", body)
                    .putString("language", lang)
                    .putString(KEY_LOCATION, key)
                    .putLong("time", System.currentTimeMillis())
                    .apply()
                parsed
            } finally {
                connection.disconnect()
            }
        }.getOrNull() ?: cached(context)
    }

    private fun menuLanguage(context: Context): String {
        val prefs = context.getSharedPreferences("epimediahub", Context.MODE_PRIVATE)
        val keys = listOf("menu_lang", "menu_language", "app_language", "ui_language", "language")
        for (key in keys) {
            val value = prefs.getString(key, null)?.trim().orEmpty()
            if (value.isNotBlank()) return normalizeLanguage(value)
        }
        val configured = runCatching {
            context.resources.configuration.locales[0].language
        }.getOrNull().orEmpty()
        return normalizeLanguage(configured.ifBlank { Locale.getDefault().language })
    }

    private fun normalizeLanguage(value: String): String {
        val raw = value.lowercase(Locale.ROOT).substringBefore('-').substringBefore('_')
        return when (raw) {
            "de", "en", "it", "tr", "fr", "es", "el" -> raw
            else -> "de"
        }
    }

    private fun parse(body: String, language: String, fallbackCity: String): V070WeatherSnapshot? = runCatching {
        val root = JSONObject(body)
        val current = root.getJSONArray("current_condition").getJSONObject(0)
        val code = current.optString("weatherCode", "0").toIntOrNull() ?: 0
        val remoteDescription = current.optJSONArray("weatherDesc")
            ?.optJSONObject(0)?.optString("value").orEmpty().trim()
        val nearest = root.optJSONArray("nearest_area")?.optJSONObject(0)
        val city = nearest?.optJSONArray("areaName")
            ?.optJSONObject(0)?.optString("value").orEmpty().trim()
            .ifBlank { fallbackCity }

        V070WeatherSnapshot(
            temperatureC = current.getString("temp_C").toInt(),
            description = localizedDescription(code, language)
                .ifBlank { remoteDescription }
                .ifBlank { localizedFallback(language) },
            code = code,
            city = city,
            languageCode = language
        )
    }.getOrNull()

    private fun localizedFallback(lang: String): String = when (lang) {
        "en" -> "Weather"
        "it" -> "Meteo"
        "tr" -> "Hava"
        "fr" -> "Météo"
        "es" -> "Tiempo"
        "el" -> "Καιρός"
        else -> "Wetter"
    }

    private fun localizedDescription(code: Int, lang: String): String {
        val key = when (code) {
            113 -> "clear"
            116 -> "partly"
            119, 122 -> "cloudy"
            143, 248, 260 -> "fog"
            176, 263, 266, 293, 296 -> "light_rain"
            299, 302, 305, 308, 353, 356, 359 -> "rain"
            179, 182, 185, 281, 284, 311, 314, 317, 350, 362, 365 -> "sleet"
            200, 386, 389, 392, 395 -> "storm"
            227, 230, 323, 326, 329, 332, 335, 338, 368, 371 -> "snow"
            else -> ""
        }
        if (key.isBlank()) return ""

        val translations = mapOf(
            "de" to mapOf("clear" to "Klar","partly" to "Teilweise bewölkt","cloudy" to "Bewölkt","fog" to "Nebel","light_rain" to "Leichter Regen","rain" to "Regen","sleet" to "Schneeregen","storm" to "Gewitter","snow" to "Schnee"),
            "en" to mapOf("clear" to "Clear","partly" to "Partly cloudy","cloudy" to "Cloudy","fog" to "Fog","light_rain" to "Light rain","rain" to "Rain","sleet" to "Sleet","storm" to "Thunderstorm","snow" to "Snow"),
            "it" to mapOf("clear" to "Sereno","partly" to "Parzialmente nuvoloso","cloudy" to "Nuvoloso","fog" to "Nebbia","light_rain" to "Pioggia leggera","rain" to "Pioggia","sleet" to "Nevischio","storm" to "Temporale","snow" to "Neve"),
            "tr" to mapOf("clear" to "Açık","partly" to "Parçalı bulutlu","cloudy" to "Bulutlu","fog" to "Sisli","light_rain" to "Hafif yağmur","rain" to "Yağmur","sleet" to "Karla karışık yağmur","storm" to "Gök gürültülü","snow" to "Kar"),
            "fr" to mapOf("clear" to "Clair","partly" to "Partiellement nuageux","cloudy" to "Nuageux","fog" to "Brouillard","light_rain" to "Pluie légère","rain" to "Pluie","sleet" to "Neige fondue","storm" to "Orage","snow" to "Neige"),
            "es" to mapOf("clear" to "Despejado","partly" to "Parcialmente nublado","cloudy" to "Nublado","fog" to "Niebla","light_rain" to "Lluvia ligera","rain" to "Lluvia","sleet" to "Aguanieve","storm" to "Tormenta","snow" to "Nieve"),
            "el" to mapOf("clear" to "Αίθριος","partly" to "Μερική συννεφιά","cloudy" to "Συννεφιά","fog" to "Ομίχλη","light_rain" to "Ελαφριά βροχή","rain" to "Βροχή","sleet" to "Χιονόνερο","storm" to "Καταιγίδα","snow" to "Χιόνι")
        )
        return translations[lang]?.get(key).orEmpty()
    }
}
