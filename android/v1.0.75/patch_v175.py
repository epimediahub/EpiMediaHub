#!/usr/bin/env python3
"""Only opt-in GalaBox encryption fallback; Fire TV's original VPN implementation stays unchanged."""
import os
import shutil
from pathlib import Path

root=Path(os.environ["PROJECT_ROOT"])
here=Path(__file__).resolve().parent
vpn=root/"app/src/main/java/de/epimediahub/app/vpn"

def replace(file,old,new):
    source=file.read_text()
    count=source.count(old)
    if count!=1:
        raise RuntimeError(f"v175 guarded patch: {file.name} expected one anchor, saw {count}: {old[:120]}")
    file.write_text(source.replace(old,new,1))

build=root/"app/build.gradle.kts"
replace(build,"versionCode = 1074","versionCode = 1075")
replace(build,'versionName = "1.0.74"','versionName = "1.0.75"')
shutil.copyfile(here/"V175GalaBoxServerVault.kt",vpn/"V175GalaBoxServerVault.kt")

identity=vpn/"V142VpnPrivateKeyStore.kt"
replace(identity,
'''                    V173GalaBoxKeyCompat.VERSION ->
                        V173GalaBoxKeyCompat.open(context,
                            V173GalaBoxKeyCompat.IDENTITY_ALIAS, raw)
                    else -> error("VPN identity storage version not supported")
''',
'''                    V173GalaBoxKeyCompat.VERSION ->
                        V173GalaBoxKeyCompat.open(context,
                            V173GalaBoxKeyCompat.IDENTITY_ALIAS, raw)
                    V175GalaBoxServerVault.VERSION ->
                        V175GalaBoxServerVault.open(context, "identity", raw)
                    else -> error("VPN identity storage version not supported")
''')
replace(identity,
'''                if (!V173GalaBoxKeyCompat.enabled(context)) throw error
                V173GalaBoxKeyCompat.seal(context,
                    V173GalaBoxKeyCompat.IDENTITY_ALIAS, plain)
''',
'''                if (!V173GalaBoxKeyCompat.enabled(context)) throw error
                try {
                    V173GalaBoxKeyCompat.seal(context,
                        V173GalaBoxKeyCompat.IDENTITY_ALIAS, plain)
                } catch (rsaError: Exception) {
                    V175GalaBoxServerVault.seal(context, "identity", plain)
                }
''')

profile=vpn/"V139VpnEncryptedProfileStore.kt"
replace(profile,
'''                V173GalaBoxKeyCompat.VERSION ->
                    V173GalaBoxKeyCompat.open(context,
                        V173GalaBoxKeyCompat.PROFILE_ALIAS, input)
                else -> error("Unbekanntes VPN-Profilformat")
''',
'''                V173GalaBoxKeyCompat.VERSION ->
                    V173GalaBoxKeyCompat.open(context,
                        V173GalaBoxKeyCompat.PROFILE_ALIAS, input)
                V175GalaBoxServerVault.VERSION ->
                    V175GalaBoxServerVault.open(context, "profile", input)
                else -> error("Unbekanntes VPN-Profilformat")
''')
replace(profile,
'''                if (!V173GalaBoxKeyCompat.enabled(context)) throw error
                V173GalaBoxKeyCompat.seal(context,
                    V173GalaBoxKeyCompat.PROFILE_ALIAS, plain)
''',
'''                if (!V173GalaBoxKeyCompat.enabled(context)) throw error
                try {
                    V173GalaBoxKeyCompat.seal(context,
                        V173GalaBoxKeyCompat.PROFILE_ALIAS, plain)
                } catch (rsaError: Exception) {
                    V175GalaBoxServerVault.seal(context, "profile", plain)
                }
''')

settings=vpn/"V141VpnSettings.kt"
replace(settings,
'''                Text("GalaBox-Kompatibilitätsmodus aktiviert · kein unverschlüsselter Schlüsselspeicher.",
                    color = Color.LightGray, fontSize = 14.sp)
''',
'''                Text("GalaBox-Kompatibilitätsmodus aktiv: Verschlüsselung am Gerät oder " +
                    "servergestützter Tresor. Ohne bestätigte VPN-Lizenz keine Verbindung.",
                    color = Color.LightGray, fontSize = 14.sp)
''')

vault=(vpn/"V175GalaBoxServerVault.kt").read_text()
assert 'V173GalaBoxKeyCompat.enabled(context)' in vault
assert 'Cache-Control", "no-store"' in vault
assert 'AES/GCM/NoPadding' in vault
assert 'https://api.epimediahub.com' in vault
assert 'V175GalaBoxServerVault.open(context, "identity", raw)' in identity.read_text()
assert 'V175GalaBoxServerVault.open(context, "profile", input)' in profile.read_text()
assert 'V173GalaBoxKeyCompat.enabled(context)' in identity.read_text()
print("v175: only opted-in non-Amazon GalaBox remote vault fallback, 0 Fire/entitlement changes")
