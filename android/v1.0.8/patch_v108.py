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
replace_once(gradle, "versionCode = 1007", "versionCode = 1008", "versionCode")
replace_once(gradle, 'versionName = "1.0.7"', 'versionName = "1.0.8"', "versionName")

for relative in (
    "ui/Screens.kt",
    "ui/V078DashboardPairingGate.kt",
    "ui/V083Home.kt",
    "data/V070WeatherClient.kt",
    "ui/V106SmartTubePlayer.kt",
):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("1.0.7", "1.0.8"))

shutil.copyfile(here / "V108SmartTubeCore.kt", java / "ui/V108SmartTubeCore.kt")
shutil.copyfile(here / "V108SmartTubeShell.kt", java / "ui/V108SmartTubeShell.kt")

# Faster SmartTube startup: the 1.0.5 bridge first queried Innertube even
# though EpiMediaHub cannot consume SABR. Skip that known-slow SABR-first
# request and try the last successful legacy client first (TV_DOWNGRADED by
# default). Only fall back through other clients when needed.
format_wrapper = root / ".smarttube/MediaServiceCore/youtubeapi/src/main/java/com/liskovsoft/youtubeapi/service/internal/FormatInfoWrapper.kt"
fw = format_wrapper.read_text()
field_anchor = "    private var mTryInnertubeFirst: Boolean = true\n"
if field_anchor not in fw:
    raise SystemExit("FormatInfoWrapper mTryInnertubeFirst anchor missing")
if "mEpiMediaPreferredLegacySteps" not in fw:
    fw = fw.replace(
        field_anchor,
        field_anchor + "    private var mEpiMediaPreferredLegacySteps: Int = 1\n",
        1,
    )

old_method = '''    @JvmStatic
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
'''

new_method = '''    @JvmStatic
    fun getMedia3CompatibleFormatInfo(
        videoId: String,
        clickTrackingParams: String?
    ): MediaItemFormatInfo? {
        // EpiMediaHub uses Media3 and cannot consume SmartTube's SABR-only
        // result. Starting with Innertube therefore adds a network round-trip
        // before nearly every video. Go directly to the legacy client path.
        mTryInnertubeFirst = false
        getVideoInfoService().resetInfoType()

        val preferredSteps = mEpiMediaPreferredLegacySteps.coerceIn(1, 10)
        repeat(preferredSteps) {
            getVideoInfoService().switchNextFormat(true)
        }

        invalidateCache()
        var candidate = mLegacyProvider(videoId, clickTrackingParams)
        var fallback = candidate
        if (isMedia3Compatible(candidate)) {
            return candidate
        }

        var currentSteps = preferredSteps
        var attempts = 0
        while (attempts < 10) {
            val endReached = getVideoInfoService().switchNextFormat(true)
            if (endReached) break
            currentSteps++
            invalidateCache()
            candidate = mLegacyProvider(videoId, clickTrackingParams)

            if (candidate != null && !candidate.isUnplayable) {
                fallback = candidate
                if (isMedia3Compatible(candidate)) {
                    mEpiMediaPreferredLegacySteps = currentSteps
                    return candidate
                }
            }
            attempts++
        }

        // Rare fallback: if legacy clients all fail, still allow the original
        // Innertube provider to return something useful.
        mTryInnertubeFirst = true
        invalidateCache()
        val innertube = mInnertubeProvider(videoId, clickTrackingParams)
        return if (isMedia3Compatible(innertube)) innertube else fallback ?: innertube
    }
'''

if old_method not in fw:
    raise SystemExit("old EpiMedia playback bridge method missing")
fw = fw.replace(old_method, new_method, 1)
format_wrapper.write_text(fw)

home = java / "ui/V083Home.kt"
replace_once(
    home,
    "        V104SmartTubeShell(\n",
    "        V108SmartTubeShell(\n",
    "SmartTube 1.0.8 shell route",
)


# ---------------------------------------------------------------------------
# SmartTube playback startup speed.
#
# 1.0.5 deliberately scanned playback clients from scratch for every video so
# Media3 could avoid SABR-only responses. That is robust but slow. Remember the
# last compatible legacy client and try it first on the next video. Only scan
# other clients again if that fast path stops working.
# ---------------------------------------------------------------------------
media_root = root / ".smarttube/MediaServiceCore"
format_wrapper = media_root / "youtubeapi/src/main/java/com/liskovsoft/youtubeapi/service/internal/FormatInfoWrapper.kt"
fw = format_wrapper.read_text()

state_anchor = "    private var mTryInnertubeFirst: Boolean = true\n"
if state_anchor not in fw:
    raise SystemExit("FormatInfoWrapper playback state anchor missing")
if "mEpiMedia3LegacyReady" not in fw:
    fw = fw.replace(
        state_anchor,
        state_anchor + "    private var mEpiMedia3LegacyReady: Boolean = false\n",
        1,
    )

reset_old = """    @JvmStatic
    fun resetFormat() {
        getVideoInfoService().resetInfoType()
    }
"""
reset_new = """    @JvmStatic
    fun resetFormat() {
        mEpiMedia3LegacyReady = false
        mTryInnertubeFirst = true
        getVideoInfoService().resetInfoType()
    }
"""
if reset_old not in fw:
    raise SystemExit("FormatInfoWrapper resetFormat anchor missing")
fw = fw.replace(reset_old, reset_new, 1)

method_start = fw.find("    @JvmStatic\n    fun getMedia3CompatibleFormatInfo(")
helper_start = fw.find("    private fun isMedia3Compatible", method_start)
if method_start < 0 or helper_start < 0:
    raise SystemExit("FormatInfoWrapper Media3 method anchors missing")

fast_method = """    @JvmStatic
    fun getMedia3CompatibleFormatInfo(
        videoId: String,
        clickTrackingParams: String?
    ): MediaItemFormatInfo? {
        invalidateCache()
        mTryInnertubeFirst = false
        var fallback: MediaItemFormatInfo? = null

        // Fast path: reuse the client that produced a Media3-compatible stream
        // for the previous video. This avoids re-probing YouTube clients on
        // every click.
        if (mEpiMedia3LegacyReady) {
            val preferred = mLegacyProvider(videoId, clickTrackingParams)
            if (preferred != null && !preferred.isUnplayable) {
                fallback = preferred
                if (isMedia3Compatible(preferred)) {
                    return preferred
                }
            }
            getVideoInfoService().switchNextFormat(true)
        } else {
            // First playback: skip VISIONOS (commonly SABR-only) and begin with
            // TV_DOWNGRADED, which supports authenticated playback.
            getVideoInfoService().resetInfoType()
            getVideoInfoService().switchNextFormat(true)
        }

        var attempts = 0
        var endReached = false
        while (!endReached && attempts < 10) {
            invalidateCache()
            val candidate = mLegacyProvider(videoId, clickTrackingParams)

            if (candidate != null && !candidate.isUnplayable) {
                fallback = candidate
                if (isMedia3Compatible(candidate)) {
                    mEpiMedia3LegacyReady = true
                    return candidate
                }
            }

            endReached = getVideoInfoService().switchNextFormat(true)
            attempts++
        }

        // Rare fallback only: allow the normal Innertube provider one chance.
        // If it is SABR-only, the caller will surface the existing friendly
        // compatibility error instead of repeatedly probing.
        mEpiMedia3LegacyReady = false
        mTryInnertubeFirst = true
        invalidateCache()
        val initial = mInnertubeProvider(videoId, clickTrackingParams)
        return if (isMedia3Compatible(initial)) initial else (fallback ?: initial)
    }

"""
fw = fw[:method_start] + fast_method + fw[helper_start:]
format_wrapper.write_text(fw)

# Start rendering with a smaller initial buffer. Keep a healthy forward buffer
# so faster startup does not turn into constant rebuffering on Fire TV.
player = java / "ui/V106SmartTubePlayer.kt"
ps = player.read_text()
if "import androidx.media3.exoplayer.DefaultLoadControl\n" not in ps:
    import_anchor = "import androidx.media3.exoplayer.ExoPlayer\n"
    if import_anchor not in ps:
        raise SystemExit("SmartTube ExoPlayer import anchor missing")
    ps = ps.replace(
        import_anchor,
        "import androidx.media3.exoplayer.DefaultLoadControl\n" + import_anchor,
        1,
    )

data_anchor = "            val dataSource = DefaultDataSource.Factory(context, http)\n"
if data_anchor not in ps:
    raise SystemExit("SmartTube data source anchor missing")
if "val loadControl = DefaultLoadControl.Builder()" not in ps:
    ps = ps.replace(
        data_anchor,
        data_anchor +
        """            val loadControl = DefaultLoadControl.Builder()
                .setBufferDurationsMs(
                    5_000,
                    30_000,
                    750,
                    1_250
                )
                .build()
""",
        1,
    )

builder_anchor = "            ExoPlayer.Builder(context)\n                .setMediaSourceFactory(sourceFactory)\n"
if builder_anchor not in ps:
    raise SystemExit("SmartTube source factory builder anchor missing")
ps = ps.replace(
    builder_anchor,
    "            ExoPlayer.Builder(context)\n                .setLoadControl(loadControl)\n                .setMediaSourceFactory(sourceFactory)\n",
    1,
)
player.write_text(ps)

checks = [
    (gradle, "versionCode = 1008"),
    (gradle, 'versionName = "1.0.8"'),
    (gradle, "minSdk = 25"),
    (home, "V108SmartTubeShell("),
    (java / "ui/V108SmartTubeCore.kt", "V108SmartTubeSection"),
    (java / "ui/V108SmartTubeCore.kt", "collectGroups(service.getTrendingObserve())"),
    (java / "ui/V108SmartTubeShell.kt", "V108SmartTubeSidebar("),
    (java / "ui/V108SmartTubeShell.kt", "V108TopAction("),
    (java / "ui/V108SmartTubeShell.kt", "if (focused) 2.dp else 1.dp"),
    (java / "ui/V108SmartTubeShell.kt", "V106SmartTubePlayer("),
    (java / "ui/V108SmartTubeCore.kt", "playbackCache"),
    (format_wrapper, "mEpiMediaPreferredLegacySteps"),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing marker {marker} in {path}")

print("Android 1.0.8 SmartTube navigation and focus UI applied")
