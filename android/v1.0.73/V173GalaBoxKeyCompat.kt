package de.epimediahub.app.vpn

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.nio.ByteBuffer
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Explicit, NON-Amazon Android TV/box interoperability pilot. Never selected
 * for Fire TV, nor on any device before user opt-in. The existing AndroidKeyStore
 * AES-GCM v1 format remains unchanged and readable.
 *
 * Alternative v2: AndroidKeyStore RSA-2048 OAEP wraps a fresh random 256-bit
 * AES key; software AES-GCM (authenticated encryption) protects the secret.
 * Only RSA-wrapped AES key, nonce and ciphertext are written to noBackupFilesDir.
 * No raw AES, WireGuard private key or plaintext profile is persisted.
 *
 * If AndroidKeyStore RSA also fails, fail closed. Never regenerate keys for an
 * existing encrypted identity and never delete user files or server entitlements.
 */
internal object V173GalaBoxKeyCompat {
    const val VERSION: Byte = 2
    const val IDENTITY_ALIAS = "epimediahub_galabox_v173_identity_rsa"
    const val PROFILE_ALIAS = "epimediahub_galabox_v173_profile_rsa"
    private const val PREFS = "galabox-vpn-compat-v173"
    private const val ENABLED = "user_opt_in"
    private const val IV_BYTES = 12
    private const val AES_BYTES = 32
    private const val TAG_BITS = 128

    internal fun isAmazon(manufacturer: String, brand: String): Boolean =
        manufacturer.contains("amazon", ignoreCase = true) ||
            brand.contains("amazon", ignoreCase = true)

    fun supported(context: Context): Boolean =
        Build.VERSION.SDK_INT >= 23 &&
            !isAmazon(Build.MANUFACTURER ?: "", Build.BRAND ?: "") &&
            context.packageName == "de.epimediahub.app"

    fun enabled(context: Context): Boolean =
        supported(context) &&
            context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(ENABLED, false)

    fun enableForManualGalaBoxTest(context: Context) {
        check(supported(context)) { "Der GalaBox-Testmodus ist auf diesem Gerät nicht verfügbar." }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putBoolean(ENABLED, true).apply()
    }

    private fun keyPair(alias: String): KeyPair {
        require(alias == IDENTITY_ALIAS || alias == PROFILE_ALIAS)
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val key = ks.getKey(alias, null)
        if (key != null) {
            val privateKey = key as? java.security.PrivateKey
                ?: error("GalaBox: vorhandener RSA-Schlüssel hat den falschen Typ")
            val publicKey = ks.getCertificate(alias)?.publicKey
                ?: error("GalaBox: RSA-Zertifikat fehlt")
            return KeyPair(publicKey, privateKey)
        }
        val gen = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_RSA, "AndroidKeyStore")
        gen.initialize(
            KeyGenParameterSpec.Builder(
                alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            ).setKeySize(2048)
                .setDigests(KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_SHA1)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_RSA_OAEP)
                .setUserAuthenticationRequired(false)
                .build()
        )
        return gen.generateKeyPair()
    }

    /** New v2 file format: version[1], wrappedLength[2], wrappedKey[N], iv[12], AES-GCM ciphertext. */
    fun seal(context: Context, alias: String, plaintext: ByteArray): ByteArray {
        check(enabled(context)) { "GalaBox-Kompatibilitätsmodus nicht ausdrücklich aktiviert" }
        require(plaintext.isNotEmpty() && plaintext.size <= 12_000)
        val aesKey = ByteArray(AES_BYTES)
        SecureRandom().nextBytes(aesKey)
        try {
            val rsa = try { keyPair(alias) } catch (e: Exception) {
                throw IllegalStateException("GalaBox: geschützter RSA-Keystore ebenfalls nicht verfügbar", e)
            }
            val wrap = Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding")
            wrap.init(Cipher.ENCRYPT_MODE, rsa.getPublic())
            val wrapped = wrap.doFinal(aesKey)
            require(wrapped.size in 128..512)
            val aes = Cipher.getInstance("AES/GCM/NoPadding")
            aes.init(Cipher.ENCRYPT_MODE, SecretKeySpec(aesKey, "AES"))
            val iv = aes.iv
            require(iv.size == IV_BYTES)
            val ciphertext = aes.doFinal(plaintext)
            val result = ByteBuffer.allocate(1 + 2 + wrapped.size + IV_BYTES + ciphertext.size)
            result.put(VERSION).putShort(wrapped.size.toShort())
                .put(wrapped).put(iv).put(ciphertext)
            ciphertext.fill(0)
            return result.array()
        } finally {
            aesKey.fill(0)
        }
    }

    fun open(context: Context, alias: String, stored: ByteArray): ByteArray {
        check(supported(context)) { "GalaBox-Schlüsselspeicher nicht auf Amazon/Fire TV freigegeben" }
        require(stored.size in 160..16_000 && stored[0] == VERSION)
        val buffer = ByteBuffer.wrap(stored)
        buffer.get()
        val wrappedLength = buffer.getShort().toInt() and 0xffff
        require(wrappedLength in 128..512 && buffer.remaining() >= wrappedLength + IV_BYTES + 16) {
            "GalaBox: gesicherte VPN-Datei ungültig"
        }
        val wrapped = ByteArray(wrappedLength)
        buffer.get(wrapped)
        val iv = ByteArray(IV_BYTES)
        buffer.get(iv)
        val ciphertext = ByteArray(buffer.remaining())
        buffer.get(ciphertext)
        try {
            val pair = keyPair(alias)
            val unwrap = Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding")
            unwrap.init(Cipher.DECRYPT_MODE, pair.getPrivate())
            val aesKey = unwrap.doFinal(wrapped)
            try {
                require(aesKey.size == AES_BYTES)
                val aes = Cipher.getInstance("AES/GCM/NoPadding")
                aes.init(Cipher.DECRYPT_MODE, SecretKeySpec(aesKey, "AES"),
                    GCMParameterSpec(TAG_BITS, iv))
                return aes.doFinal(ciphertext)
            } finally {
                aesKey.fill(0)
            }
        } finally {
            wrapped.fill(0)
            ciphertext.fill(0)
        }
    }
}
