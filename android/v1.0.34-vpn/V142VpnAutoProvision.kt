package de.epimediahub.app.vpn

import android.content.Context
import de.epimediahub.app.data.SetupCodeProvisioning
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Uses the exact registered EpiMediaHub device ID + current customer session.
 * The server learns only this installation's PUBLIC WireGuard key. The private
 * key is generated once and kept encrypted in noBackupFilesDir/AndroidKeyStore.
 * Android's one-time VPN permission dialog remains mandatory.
 */
internal object V142VpnAutoProvision {
    private const val ORIGIN = "https://api.epimediahub.com"

    data class Status(val deviceId: String, val status: String, val enabled: Boolean,
                      val expiry: String?)
    @Volatile private var lastStatus = Status("", "NOT_REGISTERED", false, null)

    fun currentStatus(): Status = lastStatus
    fun registeredDeviceId(context: Context): String = SetupCodeProvisioning.deviceId(context)

    private fun request(context: Context, path: String, post: JSONObject? = null): JSONObject {
        val token = SetupCodeProvisioning.sessionToken(context)
            ?.takeIf { it.length >= 32 } ?: error("Gerät noch nicht im EpiMediaHub-Dashboard registriert")
        require(path.startsWith("/v1/device/") && !path.contains(".."))
        val connection = URL(ORIGIN + path).openConnection() as HttpURLConnection
        try {
            connection.instanceFollowRedirects = false
            connection.connectTimeout = 7000
            connection.readTimeout = 7000
            connection.useCaches = false
            connection.requestMethod = if (post == null) "GET" else "POST"
            connection.setRequestProperty("Authorization", "Bearer $token")
            connection.setRequestProperty("Accept", "application/json")
            connection.setRequestProperty("Cache-Control", "no-store")
            if (post != null) {
                connection.setRequestProperty("Content-Type", "application/json")
                connection.doOutput = true
                val bytes = post.toString().toByteArray(Charsets.UTF_8)
                require(bytes.size <= 4096)
                connection.outputStream.use { it.write(bytes) }
            }
            val code = connection.responseCode
            if (code !in 200..299) {
                val message = when (code) {
                    401, 403 -> "Geräte-Anmeldung abgelaufen. Bitte Gerät erneut mit dem Dashboard verbinden."
                    409 -> "VPN-Schlüssel dieses Geräts stimmt nicht überein. Bitte im Admin-Dashboard prüfen."
                    else -> "VPN-Server antwortet mit Status $code"
                }
                error(message)
            }
            val body = connection.inputStream.use { input ->
                input.readNBytes(16_385)
            }
            require(body.size <= 16_384) { "VPN-Serverantwort zu groß" }
            return JSONObject(body.toString(Charsets.UTF_8))
        } finally { connection.disconnect() }
    }

    private fun remember(context: Context, data: JSONObject): Status {
        val deviceId = registeredDeviceId(context)
        check(data.optString("device_id") == deviceId) { "VPN-Geräte-ID stimmt nicht überein" }
        val status = Status(deviceId, data.optString("status", "UNKNOWN"),
            data.optBoolean("enabled", false),
            data.optString("expires_at").takeIf { it.isNotBlank() })
        lastStatus = status
        return status
    }

    /** Read-only license check. Does NOT generate a new device ID. */
    fun checkStatus(context: Context): Status {
        val response = request(context, "/v1/device/vpn/status")
        return remember(context, response)
    }

    /**
     * Call on a Dispatchers.IO worker. Requires an already registered session.
     * Does not use ADB, VPN config files, QR codes or a manually copied key.
     * Throws rather than falling back to unprotected streaming.
     */
    @Synchronized
    fun ensureProfile(context: Context): Status {
        val application = context.applicationContext
        var data = request(application, "/v1/device/vpn/status")
        var status = remember(application, data)
        if (status.status == "NO_VPN_LICENSE" || status.status == "EXPIRED" ||
            status.status == "SUSPENDED") {
            error("VPN ist für diese Geräte-ID nicht freigeschaltet: ${status.status}")
        }
        if (!status.enabled) {
            val identity = V142VpnPrivateKeyStore.getOrCreate(application)
            data = request(application, "/v1/device/vpn/enroll", JSONObject()
                .put("device_id", status.deviceId)
                .put("public_key", identity.publicKey))
            status = remember(application, data)
            // A fresh binding requires the Finland reconciliation service to
            // authorize this peer. Bounded retry, never speculative playback.
            for (i in 0..6) {
                if (status.enabled) break
                if (status.status in setOf("EXPIRED","SUSPENDED","NO_VPN_LICENSE"))
                    error("VPN ist gesperrt oder abgelaufen")
                Thread.sleep(1500)
                data = request(application, "/v1/device/vpn/status")
                status = remember(application, data)
            }
        }
        check(status.enabled && status.status == "READY") {
            "VPN ist zugeordnet, aber der Finnland-Server hat die Freigabe noch nicht bestätigt"
        }
        val privateKey = V142VpnPrivateKeyStore.getOrCreate(application).privateKey
        val address = data.getString("client_address")
        val serverKey = data.getString("server_public_key")
        val endpoint = data.getString("endpoint")
        val dns = data.getJSONArray("dns").getString(0)
        check(Regex("10\\.92\\.[0-9]{1,3}\\.[0-9]{1,3}/32").matches(address))
        check(Regex("[A-Za-z0-9+/]{43}=").matches(serverKey))
        check(Regex("[A-Za-z0-9.\\-]+:[0-9]{2,5}").matches(endpoint))
        check(dns == "1.1.1.1")
        val profile = """
            [Interface]
            PrivateKey = $privateKey
            Address = $address
            DNS = $dns
            IncludedApplications = ${application.packageName}

            [Peer]
            PublicKey = $serverKey
            Endpoint = $endpoint
            AllowedIPs = 0.0.0.0/0, ::/0
            PersistentKeepalive = 25
        """.trimIndent()
        val existing = V139VpnEncryptedProfileStore.load(application)
        if (existing != profile) V134VpnSession.storeProfile(application, profile)
        return status
    }
}
