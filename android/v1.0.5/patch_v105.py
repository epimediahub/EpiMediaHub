#!/usr/bin/env python3
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1004", "versionCode = 1005", "versionCode")
replace_once(gradle, 'versionName = "1.0.4"', 'versionName = "1.0.5"', "versionName")

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("1.0.4", "1.0.5"))

# Host playback core: keep the working 1.0.4 account/home UI but replace
# the playback resolver with a Media3-compatible SmartTube provider.
shutil.copyfile(here / "V105SmartTubeCore.kt", java / "ui/V105SmartTubeCore.kt")
shell = java / "ui/V104SmartTubeShell.kt"
replace_once(
    shell,
    "V104SmartTubeCore.",
    "V105SmartTubeCore.",
    "SmartTube 1.0.5 core route #1",
)
# Replace all remaining core references in the same shell.
shell.write_text(shell.read_text().replace("V104SmartTubeCore.", "V105SmartTubeCore."))

# Add a public bridge inside the pinned MediaServiceCore module. This bridge
# can call internal FormatInfoWrapper APIs while exposing only the one host
# method EpiMediaHub needs.
media_root = root / ".smarttube/MediaServiceCore"
bridge_target = media_root / "youtubeapi/src/main/java/com/liskovsoft/youtubeapi/service/internal/EpiMediaPlaybackBridge.kt"
bridge_target.parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(here / "EpiMediaPlaybackBridge.kt", bridge_target)

format_wrapper = media_root / "youtubeapi/src/main/java/com/liskovsoft/youtubeapi/service/internal/FormatInfoWrapper.kt"
fw = format_wrapper.read_text()
anchor = '''    @JvmStatic
    fun getFormatInfo(videoId: String, clickTrackingParams: String?): MediaItemFormatInfo? {
        return selectPlaybackFormatInfo(videoId, clickTrackingParams)
    }
'''
if anchor not in fw:
    raise SystemExit("FormatInfoWrapper getFormatInfo anchor missing")

host_method = anchor + '''
    /**
     * EpiMediaHub uses AndroidX Media3 rather than SmartTube's custom SABR
     * ExoPlayer extension. Prefer the normal SmartTube result, then rotate
     * through legacy playback clients until one returns DASH/HLS/progressive
     * media that Media3 can consume.
     */
    @JvmStatic
    fun getMedia3CompatibleFormatInfo(
        videoId: String,
        clickTrackingParams: String?
    ): MediaItemFormatInfo? {
        invalidateCache()

        val initial = selectPlaybackFormatInfo(videoId, clickTrackingParams)
        if (isMedia3Compatible(initial)) {
            return initial
        }

        var fallback = initial

        // Innertube currently often returns SABR-only media. SmartTube's first
        // legacy client is VISIONOS; move immediately to TV_DOWNGRADED because
        // it supports authenticated playback and is not marked playback-broken.
        mTryInnertubeFirst = false
        getVideoInfoService().resetInfoType()
        getVideoInfoService().switchNextFormat(true)

        var attempts = 0
        var endReached = false
        while (!endReached && attempts < 12) {
            invalidateCache()
            val candidate = mLegacyProvider(videoId, clickTrackingParams)

            if (candidate != null && !candidate.isUnplayable) {
                fallback = candidate
                if (isMedia3Compatible(candidate)) {
                    return candidate
                }
            }

            endReached = getVideoInfoService().switchNextFormat(true)
            attempts++
        }

        return fallback
    }

    private fun isMedia3Compatible(info: MediaItemFormatInfo?): Boolean {
        return info != null &&
            !info.isUnplayable &&
            (info.containsDashFormats() ||
                info.containsUrlFormats() ||
                info.containsHlsUrl() ||
                info.containsDashUrl())
    }
'''
fw = fw.replace(anchor, host_method, 1)
format_wrapper.write_text(fw)

home = java / "ui/V083Home.kt"
if "V104SmartTubeShell(" not in home.read_text():
    raise SystemExit("SmartTube shell route missing")

checks = [
    (gradle, "versionCode = 1005"),
    (gradle, 'versionName = "1.0.5"'),
    (gradle, "minSdk = 25"),
    (java / "ui/V105SmartTubeCore.kt", "EpiMediaPlaybackBridge.getMedia3CompatibleFormatInfo"),
    (shell, "V105SmartTubeCore.resolvePlayback"),
    (bridge_target, "getMedia3CompatibleFormatInfo"),
    (format_wrapper, "fun getMedia3CompatibleFormatInfo("),
    (format_wrapper, "AppClient"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.5 SmartTube Media3 playback fallback applied")
