#!/usr/bin/env python3
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1002", "versionCode = 1003", "versionCode")
replace_once(gradle, 'versionName = "1.0.2"', 'versionName = "1.0.3"', "versionName")

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("1.0.2", "1.0.3"))

# The runtime error shown on Fire TV is Retrofit's classic R8/full-mode
# signature stripping failure ("Call return type must be parameterized").
# Upstream SmartTube itself ships its app release without minification.
# For 1.0.3 we deliberately turn R8/resource shrinking off for release so the
# embedded MediaServiceCore keeps its generic Retrofit signatures intact.
g = gradle.read_text()
release_override = r'''

// EpiMediaHub 1.0.3: SmartTube MediaServiceCore relies on Retrofit reflection.
// Keep the signed test release unminified until the integration is stable.
android {
    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            isShrinkResources = false
        }
    }
}
'''
if "EpiMediaHub 1.0.3: SmartTube MediaServiceCore relies on Retrofit reflection." not in g:
    gradle.write_text(g + release_override)

# Keep the full modern Retrofit reflection contract in place as well. These
# rules match Retrofit's R8/full-mode consumer configuration and let us safely
# re-enable shrinking later after device verification.
proguard = root / "app/proguard-rules.pro"
pg = proguard.read_text() if proguard.exists() else ""
retrofit_rules = r'''

# Retrofit / R8 full-mode reflection contract for embedded SmartTube.
-keepattributes Signature, InnerClasses, EnclosingMethod
-keepattributes RuntimeVisibleAnnotations, RuntimeVisibleParameterAnnotations
-keepattributes AnnotationDefault

-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}

-if interface * { @retrofit2.http.* <methods>; }
-keep,allowobfuscation interface <1>

-if interface * { @retrofit2.http.* <methods>; }
-keep,allowobfuscation interface * extends <1>

-keep,allowoptimization,allowshrinking,allowobfuscation class kotlin.coroutines.Continuation

-if interface * { @retrofit2.http.* public *** *(...); }
-keep,allowoptimization,allowshrinking,allowobfuscation class <3>

-keep,allowoptimization,allowshrinking,allowobfuscation class retrofit2.Response
-dontwarn org.codehaus.mojo.animal_sniffer.IgnoreJRERequirement
-dontwarn javax.annotation.**
-dontwarn kotlin.Unit
-dontwarn retrofit2.KotlinExtensions
-dontwarn retrofit2.KotlinExtensions$*
'''
if "Retrofit / R8 full-mode reflection contract for embedded SmartTube." not in pg:
    proguard.write_text(pg + retrofit_rules)

checks = [
    (gradle, "versionCode = 1003"),
    (gradle, 'versionName = "1.0.3"'),
    (gradle, "minSdk = 25"),
    (gradle, "isMinifyEnabled = false"),
    (gradle, "isShrinkResources = false"),
    (proguard, "-keepattributes Signature, InnerClasses, EnclosingMethod"),
    (proguard, "@retrofit2.http.* <methods>;"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.3 SmartTube Retrofit/R8 runtime fix applied")
