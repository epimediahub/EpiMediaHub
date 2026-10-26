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
replace_once(gradle, "versionCode = 1001", "versionCode = 1002", "versionCode")
replace_once(gradle, 'versionName = "1.0.1"', 'versionName = "1.0.2"', "versionName")

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("1.0.1", "1.0.2"))

proguard = root / "app/proguard-rules.pro"
pg = proguard.read_text() if proguard.exists() else ""
rules = """
# SmartTube MediaServiceCore is reflection-heavy (Retrofit/Gson/JsonPath) and
# upstream SmartTube ships release builds without shrinking this core.
-keepattributes Signature
-keepattributes *Annotation*
-keep class com.liskovsoft.** { *; }
-keep interface com.liskovsoft.** { *; }
-keep class com.eclipsesource.v8.** { *; }
-dontwarn com.jayway.jsonpath.**
-dontwarn retrofit2.**
"""
if "-keep class com.liskovsoft.** { *; }" not in pg:
    pg += rules
proguard.write_text(pg)

core = java / "ui/V100SmartTubeCore.kt"
text = core.read_text()
if "import kotlinx.coroutines.delay" not in text:
    text = text.replace("import kotlinx.coroutines.Dispatchers\n", "import kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.delay\n", 1)
old = """    suspend fun home(context: Context): Result<List<V100SmartTubeRow>> =
        withContext(Dispatchers.IO) {
            runCatching {
                val groups = service(context).contentService.home
                mapGroups(groups)
            }
        }
"""
new = """    suspend fun home(context: Context): Result<List<V100SmartTubeRow>> =
        withContext(Dispatchers.IO) {
            val first = runCatching {
                val groups = service(context).contentService.home
                mapGroups(groups)
            }
            if (first.isSuccess) {
                first
            } else {
                // SmartTube initializes some preference/account helpers asynchronously.
                // A short one-time retry avoids the cold-start race seen on slower Fire OS 6 devices.
                delay(500)
                runCatching {
                    val groups = service(context).contentService.home
                    mapGroups(groups)
                }.fold(
                    onSuccess = { Result.success(it) },
                    onFailure = { second ->
                        Result.failure(
                            IllegalStateException(
                                "SmartTube-Core: " + describeFailure(second),
                                second
                            )
                        )
                    }
                )
            }
        }
"""
if old not in text:
    raise SystemExit("SmartTube home anchor missing")
text = text.replace(old, new, 1)
helper = """
    private fun describeFailure(error: Throwable): String {
        var root = error
        while (root.cause != null && root.cause !== root) {
            root = root.cause!!
        }
        val type = root.javaClass.simpleName.ifBlank { root.javaClass.name }
        val detail = root.message?.trim()?.takeIf { it.isNotBlank() }
        return if (detail == null) type else "$type: $detail"
    }

"""
anchor = "    private fun mapGroups(groups: List<MediaGroup>?): List<V100SmartTubeRow> =\n"
if anchor not in text:
    raise SystemExit("SmartTube helper anchor missing")
text = text.replace(anchor, helper + anchor, 1)
core.write_text(text)

# Hidden movie/series categories must also be excluded from the synthetic
# recently-added feed. The same filtered list drives both the Hero rotation
# and the "Zuletzt hinzugefügt" row.
hub = java / "ui/V060CinematicHub.kt"
hub_text = hub.read_text()
old_newest = '    val newest = u.catalogRows["__recently_added__"].orEmpty().sortedByDescending { it.addedAt }'
new_newest = '''    val newest = u.catalogRows["__recently_added__"].orEmpty()
        .filter { it.categoryId !in u.hiddenCategoryIds }
        .sortedByDescending { it.addedAt }'''
if old_newest not in hub_text:
    raise SystemExit("recently-added hidden-category anchor missing")
hub.write_text(hub_text.replace(old_newest, new_newest, 1))

checks = [
    (gradle, "versionCode = 1002"),
    (gradle, 'versionName = "1.0.2"'),
    (gradle, "minSdk = 25"),
    (proguard, "-keep class com.liskovsoft.** { *; }"),
    (core, "delay(500)"),
    (core, "SmartTube-Core: "),
    (hub, ".filter { it.categoryId !in u.hiddenCategoryIds }"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.2 SmartTube runtime compatibility patch applied")
