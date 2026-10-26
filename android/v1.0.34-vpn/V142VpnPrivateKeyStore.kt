package de.epimediahub.app.vpn

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import com.wireguard.crypto.KeyPair
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * One private key per registered Android installation. Separate from beta-import
 * profiles, never uploaded or exported via an HTTP API.
 * AndroidKeyStore ciphertext is excluded from Android Auto Backup.
 */
internal object V142VpnPrivateKeyStore {
    data class Identity(val privateKey: String, val publicKey: String)
    private const val ALIAS = "epimediahub_auto_vpn_identity_v1"
    private const val NAME = "wg-auto-identity.bin"
    private const val VERSION: Byte = 1
    private const val IV_SIZE = 12

    private fun file(context: Context) = AtomicFile(File(context.noBackupFilesDir, NAME))

    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        val found = store.getKey(ALIAS, null)
        if (found is SecretKey) return found
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .setRandomizedEncryptionRequired(true).build()
        )
        return generator.generateKey()
    }

    @Synchronized
    fun getOrCreate(context: Context): Identity {
        val encrypted = File(context.noBackupFilesDir, NAME)
        if (encrypted.isFile) {
            val raw = file(context).readFully()
            try {
                require(raw.size in 48..512 && raw[0] == VERSION) { "VPN identity storage is invalid" }
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE, key(),
                    GCMParameterSpec(128, raw.copyOfRange(1, 1 + IV_SIZE)))
                val decoded = cipher.doFinal(raw, 1 + IV_SIZE, raw.size - 1 - IV_SIZE)
                try {
                    val parts = decoded.toString(Charsets.US_ASCII).split("\n")
                    require(parts.size == 2 && parts.all { it.length == 44 }) { "VPN identity is invalid" }
                    return Identity(parts[0], parts[1])
                } finally { decoded.fill(0) }
            } finally { raw.fill(0) }
        }
        val pair = KeyPair()
        val identity = Identity(pair.privateKey.toBase64(), pair.publicKey.toBase64())
        val plain = (identity.privateKey + "\n" + identity.publicKey).toByteArray(Charsets.US_ASCII)
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key())
            require(cipher.iv.size == IV_SIZE)
            val encryptedData = byteArrayOf(VERSION) + cipher.iv + cipher.doFinal(plain)
            val target = file(context)
            var writer: java.io.FileOutputStream? = null
            try {
                writer = target.startWrite()
                writer.write(encryptedData)
                target.finishWrite(writer)
            } catch (ex: Exception) {
                writer?.let { target.failWrite(it) }
                throw ex
            } finally { encryptedData.fill(0) }
        } finally { plain.fill(0) }
        return identity
    }
}
