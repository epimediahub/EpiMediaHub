package de.epimediahub.app.data

import android.content.Context
import kotlinx.coroutines.*
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.serialization.builtins.ListSerializer
import kotlinx.serialization.json.*
import okhttp3.*
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.net.InetAddress
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

internal fun interface RadioTransport { suspend fun get(url: String): String }

internal class RadioHttpTransport : RadioTransport {
    private val http = OkHttpClient.Builder().connectTimeout(4, TimeUnit.SECONDS).readTimeout(7, TimeUnit.SECONDS)
        .callTimeout(10, TimeUnit.SECONDS).build()
    override suspend fun get(url: String): String = suspendCancellableCoroutine { continuation ->
        val call = http.newCall(Request.Builder().url(url).header("User-Agent", "EpiMediaHub/1.0.19 Radio")
            .header("Accept", "application/json").build())
        continuation.invokeOnCancellation { call.cancel() }
        call.enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) { if (continuation.isActive) continuation.resumeWithException(e) }
            override fun onResponse(call: Call, response: Response) {
                try {
                    val text = response.use {
                        if (!it.isSuccessful) throw IOException("HTTP ${it.code}")
                        val body = it.body ?: throw IOException("Empty radio response")
                        body.byteStream().use { stream ->
                            val result = ByteArrayOutputStream(); val buffer = ByteArray(8192)
                            while (true) {
                                val size = stream.read(buffer); if (size < 0) break
                                if (result.size() + size > 1_048_576) throw IOException("Radio response too large")
                                result.write(buffer, 0, size)
                            }
                            result.toString("UTF-8")
                        }
                    }
                    if (continuation.isActive) continuation.resume(text)
                } catch (e: Exception) { if (continuation.isActive) continuation.resumeWithException(e) }
            }
        })
    }
}

internal data class RadioResponse(val json: JsonArray, val cached: Boolean = false)
internal data class RadioPage(val stations: List<RadioStation>, val hasMore: Boolean, val cached: Boolean = false,
    val partial: Boolean = false)

internal class RadioBrowserClient(
    private val cacheDir: File,
    private val transport: RadioTransport = RadioHttpTransport(),
    initialHosts: List<String> = listOf("de1.api.radio-browser.info"),
    private val clock: () -> Long = System::currentTimeMillis
) {
    @Volatile private var hosts = initialHosts.distinct()
    private val requests = Semaphore(2)

    suspend fun discoverServers() = withContext(Dispatchers.IO) {
        val discovered = runCatching {
            InetAddress.getAllByName("all.api.radio-browser.info").map { it.canonicalHostName }
                .filter { it.endsWith(".api.radio-browser.info") && it != "all.api.radio-browser.info" }.distinct().shuffled()
        }.getOrDefault(emptyList())
        if (discovered.isNotEmpty()) hosts = (discovered + hosts).distinct()
    }

    private fun cacheFile(path: String): File {
        val name = MessageDigest.getInstance("SHA-256").digest(path.toByteArray()).joinToString("") { "%02x".format(it) }
        return File(cacheDir, "$name.json")
    }

    suspend fun request(path: String, refresh: Boolean = false): RadioResponse = requests.withPermit {
        val file = cacheFile(path)
        val cached = withContext(Dispatchers.IO) {
            runCatching { if (file.isFile && file.length() <= 1_048_576) radioJson.parseToJsonElement(file.readText()) as JsonArray else null }.getOrNull()
        }
        val age = clock() - file.lastModified()
        if (!refresh && cached != null && age in 0..1_800_000L) return@withPermit RadioResponse(cached, true)
        var failure: Exception = IOException("Radio directory unavailable")
        for (host in hosts.take(3)) {
            currentCoroutineContext().ensureActive()
            try {
                val body = transport.get("https://$host$path")
                val parsed = withContext(Dispatchers.Default) { radioJson.parseToJsonElement(body) as JsonArray }
                withContext(Dispatchers.IO) {
                    runCatching {
                        cacheDir.mkdirs()
                        val temp = File.createTempFile("radio-", ".tmp", cacheDir)
                        try { temp.writeText(parsed.toString()); if (!temp.renameTo(file)) file.writeText(parsed.toString()) }
                        finally { temp.delete() }
                        cacheDir.listFiles()?.filter { it.extension == "json" }?.sortedByDescending { it.lastModified() }
                            ?.drop(80)?.forEach { it.delete() }
                    }
                }
                return@withPermit RadioResponse(parsed)
            } catch (e: CancellationException) { throw e }
            catch (e: Exception) { failure = e }
        }
        if (cached != null && age in 0..604_800_000L) RadioResponse(cached, true) else throw failure
    }

    suspend fun stations(query: RadioQuery, page: Int = 0, refresh: Boolean = false): RadioPage = withContext(Dispatchers.Default) {
        // Aliases are OR searches. Radio Browser's tagList would require EVERY tag.
        val tags: List<String?> = query.category?.tags ?: listOf(null)
        val limit = (60 / tags.size).coerceAtLeast(15)
        val replies = tags.map { tag -> async {
            try { Result.success(request(query.path(tag, page * limit, limit), refresh)) }
            catch (e: CancellationException) { throw e }
            catch (e: Exception) { Result.failure<RadioResponse>(e) }
        } }.awaitAll()
        val good = replies.mapNotNull { it.getOrNull() }
        if (good.isEmpty()) throw replies.first().exceptionOrNull()!!
        RadioPage(radioUniqueStations(good.flatMap { response -> response.json.mapNotNull { (it as? JsonObject)?.let(::radioStationFromApi) } }),
            good.any { it.json.size >= limit }, good.any { it.cached }, good.size != replies.size)
    }

    suspend fun countries(): List<RadioOption> = withContext(Dispatchers.Default) { request("/json/countrycodes?hidebroken=true&limit=500").json.mapNotNull {
        val objectValue = it as? JsonObject ?: return@mapNotNull null
        val code = (objectValue["name"] as? JsonPrimitive)?.contentOrNull.orEmpty()
        if (!code.matches(Regex("[A-Z]{2}"))) return@mapNotNull null
        RadioOption(code, radioCountryName(code), (objectValue["stationcount"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 0)
    }.distinctBy { it.id }.sortedWith(compareBy<RadioOption> { when (it.id) { "DE" -> 0; "IT" -> 1; else -> 2 } }.thenBy { radioNormalized(it.label) }) }

    suspend fun languages(): List<RadioOption> = withContext(Dispatchers.Default) { request("/json/languages?hidebroken=true&limit=1000&order=stationcount&reverse=true").json.mapNotNull {
        val objectValue = it as? JsonObject ?: return@mapNotNull null
        val name = (objectValue["name"] as? JsonPrimitive)?.contentOrNull.orEmpty().trim()
        if (name.isBlank()) return@mapNotNull null
        RadioOption(name, radioLanguageName(name), (objectValue["stationcount"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 0)
    }.distinctBy { it.id }.sortedWith(compareBy<RadioOption> { when (it.id) { "german" -> 0; "italian" -> 1; else -> 2 } }.thenBy { radioNormalized(it.label) }) }

    suspend fun recordClick(uuid: String) {
        if (!uuid.matches(Regex("[a-zA-Z0-9-]{1,64}"))) return
        // Never use the cache: one click is recorded when a listener selects a station.
        for (host in hosts.take(2)) {
            try { transport.get("https://$host/json/url/$uuid"); return }
            catch (e: CancellationException) { throw e }
            catch (_: Exception) { }
        }
    }
}

internal class RadioPreferences(context: Context) {
    private val prefs = context.applicationContext.getSharedPreferences("epimediahub-radio", Context.MODE_PRIVATE)
    private val serializer = ListSerializer(RadioStation.serializer())
    fun read(key: String): List<RadioStation> = runCatching {
        radioJson.decodeFromString(serializer, prefs.getString(key, "[]") ?: "[]").filter { radioHttpUrl(it.streamUrl) }.distinctBy { it.uuid }
    }.getOrDefault(emptyList())
    fun saveFavorites(values: List<RadioStation>) {
        prefs.edit().putString("favorites", radioJson.encodeToString(serializer, values.distinctBy { it.uuid })).apply()
    }
    @Synchronized fun rememberStation(station: RadioStation) {
        val recents = (listOf(station) + read("recent").filterNot { it.uuid == station.uuid }).take(30)
        prefs.edit().putString("recent", radioJson.encodeToString(serializer, recents)).apply()
    }
}
