package de.epimediahub.app.vpn

import android.content.Context
import android.util.Base64
import de.epimediahub.app.data.SetupCodeProvisioning
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * On-demand remote-backed GalaBox vault, only when the user has explicitly
 * enabled the existing v173 non-Amazon compatibility switch AND both Android
 * KeyStore AES and RSA fail. Private WireGuard keys never reach the server.
 *
 * All stored secrets remain AES-256-GCM encrypted; the separate per-device and
 * per-purpose 256-bit key is derived by the provisioning server from a
 * server-held master and received over authenticated HTTPS when needed.
 * It is never written to local storage or logs. If the server/key is missing,
 * no encryption or VPN access is granted (fail closed).
 */
internal object V175GalaBoxServerVault {
    const val VERSION: Byte = 3
    private const val ORIGIN = "https://api.epimediahub.com"
    private const val PATH = "/v1/device/vpn/galabox-vault-key"
    private const val IV_BYTES = 12
    private const val TAG_BITS = 128
    private val random = SecureRandom()

    private fun deviceId(context: Context): String =
        SetupCodeProvisioning.deviceId(context)

    private fun purposeCheck(purpose: String) {
        require(purpose == "identity" || purpose == "profile")
    }

    private fun wrappingKey(context: Context, purpose: String): ByteArray {
        check(V173GalaBoxKeyCompat.enabled(context)) {
            "Der sichere GalaBox-Kompatibilitätsmodus ist nicht aktiviert"
        }
        purposeCheck(purpose)
        val token = SetupCodeProvisioning.sessionToken(context)
            ?.takeIf { it.length >= 32 }
            ?: error("GalaBox noch nicht im Dashboard registriert")
        val id = deviceId(context)
        val body = JSONObject().put("device_id", id).put("purpose", purpose)
            .toString().toByteArray(Charsets.UTF_8)
        val conn = URL(ORIGIN + PATH).openConnection() as HttpURLConnection
        try {
            conn.instanceFollowRedirects = false
            conn.connectTimeout = 7000
            conn.readTimeout = 7000
            conn.useCaches = false
            conn.requestMethod = "POST"
            conn.setRequestProperty("Authorization", "Bearer " + token)
            conn.setRequestProperty("Accept", "application/json")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.setRequestProperty("Cache-Control", "no-store")
            conn.doOutput = true
            conn.outputStream.use { it.write(body) }
            when (conn.responseCode) {
                200 -> Unit
                401, 403 -> error("GalaBox-Server-Tresor: Geräteanmeldung oder VPN-Lizenz ungültig")
                503 -> error("GalaBox-Server-Tresor noch nicht eingerichtet")
                else -> error("GalaBox-Server-Tresor HTTP " + conn.responseCode)
            }
            val output = java.io.ByteArrayOutputStream()
            conn.inputStream.use { input ->
                val buffer = ByteArray(512)
                while (true) {
                    val size = input.read(buffer)
                    if (size < 0) break
                    if (output.size() + size > 1024) error("Serverantwort zu groß")
                    output.write(buffer, 0, size)
                }
            }
            val value = JSONObject(output.toString("UTF-8"))
            check(value.optInt("v", 0) == 1 &&
                value.optString("device_id") == id &&
                value.optString("purpose") == purpose) {
                "Ungültige GalaBox-Tresorantwort"
            }
            val key = Base64.decode(value.getString("key"), Base64.NO_WRAP)
            require(key.size == 32) { "Ungültige GalaBox-Verschlüsselungsstärke" }
            return key
        } finally {
            body.fill(0)
            conn.disconnect()
        }
    }

    private fun aad(context: Context, purpose: String): ByteArray =
        ("EpiMediaHub/GalaVault/v3/" + deviceId(context) + "/" + purpose)
            .toByteArray(Charsets.UTF_8)

    fun seal(context: Context, purpose: String, plain: ByteArray): ByteArray {
        require(plain.isNotEmpty() && plain.size <= 12_000)
        val key = wrappingKey(context, purpose)
        try {
            val iv = ByteArray(IV_BYTES)
            random.nextBytes(iv)
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"),
                GCMParameterSpec(TAG_BITS, iv))
            cipher.updateAAD(aad(context, purpose))
            val ciphertext = cipher.doFinal(plain)
            return byteArrayOf(VERSION) + iv + ciphertext
        } finally {
            key.fill(0)
        }
    }

    fun open(context: Context, purpose: String, raw: ByteArray): ByteArray {
        require(raw.size in 29..16000 && raw[0] == VERSION)
        val key = wrappingKey(context, purpose)
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"),
                GCMParameterSpec(TAG_BITS, raw.copyOfRange(1, 1 + IV_BYTES)))
            cipher.updateAAD(aad(context, purpose))
            return cipher.doFinal(raw, 1 + IV_BYTES, raw.size - 1 - IV_BYTES)
        } finally {
            key.fill(0)
        }
    }
}
