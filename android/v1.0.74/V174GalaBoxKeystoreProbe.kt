package de.epimediahub.app.vpn

import android.content.Context
import android.os.Build
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * User-triggered non-Amazon GalaBox diagnostic. Temporary aliases ONLY.
 * Does not read/write/delete registered VPN identity, profiles, session tokens,
 * or the license. Reports class names, never private keys or exception strings.
 */
internal object V174GalaBoxKeystoreProbe {
    private fun sanitized(error: Throwable): String {
        val chain = ArrayList<String>()
        var current: Throwable? = error
        for (i in 0..2) {
            val node = current ?: break
            chain.add(node.javaClass.simpleName.take(45))
            current = node.cause
        }
        return chain.joinToString(" -> ")
    }

    private fun attempt(name: String, run: () -> Unit): String =
        try {
            run()
            name + ": OK"
        } catch (error: Exception) {
            name + ": FEHLER (" + sanitized(error) + ")"
        }

    private fun temporaryKeyStoreAlias(suffix: String): String =
        "epimediahub_v174_probe_" + suffix + "_" + System.nanoTime()

    private fun aesKeyStoreTest(bits: Int) {
        val alias = temporaryKeyStoreAlias("aes" + bits)
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        try {
            val generator = KeyGenerator.getInstance("AES", "AndroidKeyStore")
            generator.init(
                KeyGenParameterSpec.Builder(
                    alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
                ).setKeySize(bits)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build()
            )
            val key = generator.generateKey()
            val encrypted = Cipher.getInstance("AES/GCM/NoPadding")
            encrypted.init(Cipher.ENCRYPT_MODE, key)
            val secret = ByteArray(32).also { SecureRandom().nextBytes(it) }
            val ciphertext = encrypted.doFinal(secret)
            try {
                val decrypt = Cipher.getInstance("AES/GCM/NoPadding")
                decrypt.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, encrypted.iv))
                val plain = decrypt.doFinal(ciphertext)
                try { check(plain.contentEquals(secret)) } finally { plain.fill(0) }
            } finally {
                secret.fill(0)
                ciphertext.fill(0)
            }
        } finally {
            runCatching { if (store.containsAlias(alias)) store.deleteEntry(alias) }
        }
    }

    private fun rsaKeyStoreTest() {
        val alias = temporaryKeyStoreAlias("rsa")
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        try {
            val generator = KeyPairGenerator.getInstance("RSA", "AndroidKeyStore")
            generator.initialize(
                KeyGenParameterSpec.Builder(
                    alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
                ).setKeySize(2048)
                    .setDigests(KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_SHA1)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_RSA_OAEP)
                    .setUserAuthenticationRequired(false)
                    .build()
            )
            val pair = generator.generateKeyPair()
            val key = ByteArray(32).also { SecureRandom().nextBytes(it) }
            try {
                val encrypted = Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding")
                encrypted.init(Cipher.ENCRYPT_MODE, pair.getPublic())
                val wrapped = encrypted.doFinal(key)
                val decrypt = Cipher.getInstance("RSA/ECB/OAEPWithSHA-256AndMGF1Padding")
                decrypt.init(Cipher.DECRYPT_MODE, pair.getPrivate())
                val result = decrypt.doFinal(wrapped)
                try { check(result.contentEquals(key)) } finally {
                    wrapped.fill(0)
                    result.fill(0)
                }
            } finally { key.fill(0) }
        } finally {
            runCatching { if (store.containsAlias(alias)) store.deleteEntry(alias) }
        }
    }

    private fun softwareCipherCheck() {
        val key = ByteArray(32).also { SecureRandom().nextBytes(it) }
        val data = ByteArray(32).also { SecureRandom().nextBytes(it) }
        try {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(key, "AES"))
            val ct = cipher.doFinal(data)
            val open = Cipher.getInstance("AES/GCM/NoPadding")
            open.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"),
                GCMParameterSpec(128, cipher.iv))
            val plain = open.doFinal(ct)
            try { check(plain.contentEquals(data)) } finally { ct.fill(0); plain.fill(0) }
        } finally { key.fill(0); data.fill(0) }
    }

    fun summary(context: Context): String {
        check(V173GalaBoxKeyCompat.supported(context)) {
            "Nicht für Fire TV / Amazon-Geräte verfügbar."
        }
        val tests = arrayListOf<String>()
        tests.add("Android " + Build.VERSION.RELEASE + " (API " + Build.VERSION.SDK_INT +
            ") · " + Build.MANUFACTURER + " " + Build.MODEL)
        tests.add(attempt("AndroidKeyStore laden") {
            KeyStore.getInstance("AndroidKeyStore").load(null)
        })
        tests.add(attempt("AndroidKeyStore AES-256 GCM") { aesKeyStoreTest(256) })
        tests.add(attempt("AndroidKeyStore AES-128 GCM") { aesKeyStoreTest(128) })
        tests.add(attempt("AndroidKeyStore RSA-2048 OAEP") { rsaKeyStoreTest() })
        tests.add(attempt("Software AES-256 GCM (nur RAM)") { softwareCipherCheck() })
        tests.add("Keine gespeicherten VPN-Schlüssel oder Lizenzen geändert.")
        return tests.joinToString("\n")
    }
}
