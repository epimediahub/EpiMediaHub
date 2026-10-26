package de.epimediahub.app.vpn

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.AtomicFile
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Separate VPN beta only. Encrypts the WireGuard client profile at rest using
 * non-exportable AndroidKeyStore AES-GCM; ciphertext lives in noBackupFilesDir.
 * No plaintext profile is written to app preferences, logs, GitHub or backups.
 * Requires Android API 23+ (Fire OS 6+). If Keystore fails, import fails closed.
 */
internal object V139VpnEncryptedProfileStore {
    private const val KEY_ALIAS = "epimediahub_vpnfi_beta_aes_v1"
    private const val FILENAME = "wireguard-fi.enc"
    private const val VERSION: Byte = 1
    private const val IV_BYTES = 12
    private const val GCM_TAG_BITS = 128

    private fun encryptedFile(context: Context) =
        AtomicFile(File(context.noBackupFilesDir, FILENAME))

    fun exists(context: Context): Boolean =
        File(context.noBackupFilesDir, FILENAME).isFile

    private fun getOrCreateKey(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore")
        store.load(null)
        val existing = store.getKey(KEY_ALIAS, null)
        if (existing is SecretKey) return existing
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        val params = KeyGenParameterSpec.Builder(
            KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .setRandomizedEncryptionRequired(true)
            .build()
        generator.init(params)
        return generator.generateKey()
    }

    @Synchronized
    fun save(context: Context, profile: String) {
        require(profile.length in 150..11800) { "VPN-Profilgröße ungültig" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val iv = cipher.iv
        check(iv.size == IV_BYTES) { "Keystore-GCM-IV nicht unterstützt" }
        val data = byteArrayOf(VERSION) + iv +
            cipher.doFinal(profile.toByteArray(Charsets.UTF_8))
        val target = encryptedFile(context)
        var out: java.io.FileOutputStream? = null
        try {
            out = target.startWrite()
            out.write(data)
            target.finishWrite(out)
        } catch (error: Exception) {
            out?.let { target.failWrite(it) }
            throw error
        } finally {
            data.fill(0)
        }
    }

    @Synchronized
    fun load(context: Context): String? {
        if (!exists(context)) return null
        val input = encryptedFile(context).readFully()
        try {
            require(input.size in 30..15_000) { "Gespeichertes VPN-Profil beschädigt" }
            require(input[0] == VERSION) { "Unbekanntes VPN-Profilformat" }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateKey(),
                GCMParameterSpec(GCM_TAG_BITS, input.copyOfRange(1, 1 + IV_BYTES))
            )
            val plain = cipher.doFinal(input, 1 + IV_BYTES, input.size - 1 - IV_BYTES)
            return try {
                val config = plain.toString(Charsets.UTF_8)
                require(config.length in 150..11800) { "Gespeichertes VPN-Profil ungültig" }
                config
            } finally {
                plain.fill(0)
            }
        } finally {
            input.fill(0)
        }
    }

    @Synchronized
    fun erase(context: Context) {
        encryptedFile(context).delete()
        val store = KeyStore.getInstance("AndroidKeyStore")
        store.load(null)
        if (store.containsAlias(KEY_ALIAS)) store.deleteEntry(KEY_ALIAS)
    }
}
