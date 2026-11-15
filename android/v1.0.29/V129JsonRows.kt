package de.epimediahub.app.data

import android.util.JsonReader
import android.util.JsonToken
import org.json.JSONObject
import java.io.Reader
import java.net.HttpURLConnection
import java.net.URL
import kotlinx.coroutines.CancellationException

/** Decode one catalogue record at a time, without retaining the response text/JSON tree. */
internal object V129JsonRows {
    fun <T : Any> parse(input: Reader, checkActive: () -> Unit = {}, convert: (JSONObject) -> T?): List<T> =
        JsonReader(input).use { reader ->
            val result = ArrayList<T>()
            reader.beginArray()
            while (reader.hasNext()) {
                checkActive()
                if (reader.peek() != JsonToken.BEGIN_OBJECT) { reader.skipValue(); continue }
                val row = JSONObject()
                reader.beginObject()
                while (reader.hasNext()) {
                    val key = reader.nextName()
                    when (reader.peek()) {
                        JsonToken.STRING, JsonToken.NUMBER -> row.put(key, reader.nextString())
                        JsonToken.BOOLEAN -> row.put(key, reader.nextBoolean())
                        else -> reader.skipValue() // Catalogue fields used by the app are scalars.
                    }
                }
                reader.endObject()
                convert(row)?.let(result::add)
            }
            reader.endArray()
            checkActive()
            check(reader.peek() == JsonToken.END_DOCUMENT) { "Ungültiges Katalogende" }
            result
        }

    fun <T : Any> load(urls: List<String>, checkActive: () -> Unit = {}, convert: (JSONObject) -> T?): List<T> {
        var failure: Exception? = null
        for (url in urls) {
            checkActive()
            try { return read(url, checkActive, convert) }
            catch (cancelled: CancellationException) { throw cancelled }
            catch (error: Exception) { failure = error }
        }
        // Never expose provider credentials or a full URL in UI/errors.
        throw IllegalStateException("Katalog konnte nicht geladen werden. Bitte erneut versuchen.", failure)
    }

    private fun <T : Any> read(url: String, checkActive: () -> Unit, convert: (JSONObject) -> T?): List<T> {
        var current = URL(url)
        repeat(5) {
            checkActive()
            val connection = (current.openConnection() as HttpURLConnection).apply {
                connectTimeout = 10_000; readTimeout = 25_000; instanceFollowRedirects = false
                setRequestProperty("User-Agent", "VLC/3.0.21 LibVLC/3.0.21")
                setRequestProperty("Accept", "application/json")
            }
            try {
                val code = connection.responseCode
                if (code in listOf(301, 302, 303, 307, 308)) {
                    val location = connection.getHeaderField("Location")?.takeIf { it.isNotBlank() }
                        ?: error("Katalogweiterleitung ohne Ziel")
                    current = URL(current, location)
                    check(current.protocol in setOf("http", "https"))
                } else {
                    check(code in 200..299) { "Katalog HTTP $code" }
                    return connection.inputStream.bufferedReader(Charsets.UTF_8).use { parse(it, checkActive, convert) }
                }
            } finally { connection.disconnect() }
        }
        error("Zu viele Katalogweiterleitungen")
    }
}
