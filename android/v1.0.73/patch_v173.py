#!/usr/bin/env python3
"""GalaBox opt-in AndroidKeyStore encrypted compatibility pilot, Fire TV untouched."""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app/vpn"
tests = root / "app/src/test/java/de/epimediahub/app/vpn"

def replace(path, old, new):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"v173 guarded patch mismatch {path.name}: {count}: {old[:105]!r}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1072", "versionCode = 1073")
replace(gradle, 'versionName = "1.0.72"', 'versionName = "1.0.73"')

shutil.copyfile(here / "V173GalaBoxKeyCompat.kt", java / "V173GalaBoxKeyCompat.kt")
identity = java / "V142VpnPrivateKeyStore.kt"
replace(identity,
'''                require(raw.size in 48..512 && raw[0] == VERSION) { "VPN identity storage is invalid" }
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.DECRYPT_MODE, key(),
                    GCMParameterSpec(128, raw.copyOfRange(1, 1 + IV_SIZE)))
                val decoded = cipher.doFinal(raw, 1 + IV_SIZE, raw.size - 1 - IV_SIZE)
''',
'''                require(raw.size in 48..512) { "VPN identity storage is invalid" }
                val decoded = when (raw[0]) {
                    VERSION -> {
                        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                        cipher.init(Cipher.DECRYPT_MODE, key(),
                            GCMParameterSpec(128, raw.copyOfRange(1, 1 + IV_SIZE)))
                        cipher.doFinal(raw, 1 + IV_SIZE, raw.size - 1 - IV_SIZE)
                    }
                    V173GalaBoxKeyCompat.VERSION ->
                        V173GalaBoxKeyCompat.open(context,
                            V173GalaBoxKeyCompat.IDENTITY_ALIAS, raw)
                    else -> error("VPN identity storage version not supported")
                }
''')
replace(identity,
'''            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, key())
            require(cipher.iv.size == IV_SIZE)
            val encryptedData = byteArrayOf(VERSION) + cipher.iv + cipher.doFinal(plain)
''',
'''            // Amazon/Fire TV remains byte-identical to the verified v171 path.
            val encryptedData = try {
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.ENCRYPT_MODE, key())
                require(cipher.iv.size == IV_SIZE)
                byteArrayOf(VERSION) + cipher.iv + cipher.doFinal(plain)
            } catch (error: Exception) {
                if (!V173GalaBoxKeyCompat.enabled(context)) throw error
                V173GalaBoxKeyCompat.seal(context,
                    V173GalaBoxKeyCompat.IDENTITY_ALIAS, plain)
            }
''')

profile = java / "V139VpnEncryptedProfileStore.kt"
replace(profile,
'''        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
        val iv = cipher.iv
        check(iv.size == IV_BYTES) { "Keystore-GCM-IV nicht unterstützt" }
        val data = byteArrayOf(VERSION) + iv +
            cipher.doFinal(profile.toByteArray(Charsets.UTF_8))
''',
'''        val plain = profile.toByteArray(Charsets.UTF_8)
        val data = try {
            try {
                val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
                val iv = cipher.iv
                check(iv.size == IV_BYTES) { "Keystore-GCM-IV nicht unterstützt" }
                byteArrayOf(VERSION) + iv + cipher.doFinal(plain)
            } catch (error: Exception) {
                if (!V173GalaBoxKeyCompat.enabled(context)) throw error
                V173GalaBoxKeyCompat.seal(context,
                    V173GalaBoxKeyCompat.PROFILE_ALIAS, plain)
            }
        } finally {
            plain.fill(0)
        }
''')
replace(profile,
'''            require(input[0] == VERSION) { "Unbekanntes VPN-Profilformat" }
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                getOrCreateKey(),
                GCMParameterSpec(GCM_TAG_BITS, input.copyOfRange(1, 1 + IV_BYTES))
            )
            val plain = cipher.doFinal(input, 1 + IV_BYTES, input.size - 1 - IV_BYTES)
''',
'''            val plain = when (input[0]) {
                VERSION -> {
                    val cipher = Cipher.getInstance("AES/GCM/NoPadding")
                    cipher.init(
                        Cipher.DECRYPT_MODE,
                        getOrCreateKey(),
                        GCMParameterSpec(GCM_TAG_BITS, input.copyOfRange(1, 1 + IV_BYTES))
                    )
                    cipher.doFinal(input, 1 + IV_BYTES, input.size - 1 - IV_BYTES)
                }
                V173GalaBoxKeyCompat.VERSION ->
                    V173GalaBoxKeyCompat.open(context,
                        V173GalaBoxKeyCompat.PROFILE_ALIAS, input)
                else -> error("Unbekanntes VPN-Profilformat")
            }
''')

settings = java / "V141VpnSettings.kt"
replace(settings,
'''        V141FocusButton("Finnland-VPN verbinden / prüfen", accent, onClick = {
''',
'''        // Explicit GalaBox pilot opt-in; this section is hidden on every Fire TV.
        if (V173GalaBoxKeyCompat.supported(context)) {
            if (!V173GalaBoxKeyCompat.enabled(context)) {
                V141FocusButton("GalaBox: sicheren VPN-Kompatibilitätsmodus aktivieren",
                    accent, onClick = {
                        V173GalaBoxKeyCompat.enableForManualGalaBoxTest(context)
                        status = "GalaBox-Kompatibilitätsmodus aktiv. Jetzt VPN verbinden / prüfen. " +
                            "Schlüssel bleiben verschlüsselt; Fire TV ist nicht betroffen."
                    }, enabled = !busy)
            } else {
                Text("GalaBox-Kompatibilitätsmodus aktiviert · kein unverschlüsselter Schlüsselspeicher.",
                    color = Color.LightGray, fontSize = 14.sp)
            }
        }
        V141FocusButton("Finnland-VPN verbinden / prüfen", accent, onClick = {
''')
replace(settings,
'''                status = "VPN nicht freigegeben: ${it.message ?: "Verbindung fehlgeschlagen"}. Kein Direkt-Fallback."
''',
'''                status = if (V173GalaBoxKeyCompat.supported(context))
                    "VPN-Einrichtung fehlgeschlagen: ${it.message ?: "Verbindung fehlgeschlagen"}. Kein Direkt-Fallback."
                else "VPN nicht freigegeben: ${it.message ?: "Verbindung fehlgeschlagen"}. Kein Direkt-Fallback."
''')

shutil.copyfile(here / "V173GalaBoxKeyCompatTest.kt", tests / "V173GalaBoxKeyCompatTest.kt")
assert "V173GalaBoxKeyCompat.enabled(context)" in identity.read_text()
assert "V173GalaBoxKeyCompat.PROFILE_ALIAS" in profile.read_text()
assert "V173GalaBoxKeyCompat.supported(context)" in settings.read_text()
print("v173: GalaBox manual opt-in, encrypted RSA-wrapped AES-GCM, Fire TV not changed")
