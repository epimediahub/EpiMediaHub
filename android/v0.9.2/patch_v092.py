#!/usr/bin/env python3
"""Android 0.9.2: smart Live TV no-picture/no-audio fallback without disturbing working Exo channels."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))

# Version only; keep the complete 0.9.1 series/player work below us in the patch chain.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 901', 'versionCode = 902', 'versionCode')
replace_once(gradle, 'versionName = "0.9.1"', 'versionName = "0.9.2"', 'versionName')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.9.1", "0.9.2"))

player = java / "ui/PlayerScreen.kt"

# The old first-frame watchdog still exists but was deliberately disabled in
# v0.6.4.6 for faster zapping. Since 0.9.0 is Exo-first, a stream that connects
# but never renders can now stay black/silent forever without raising an error.
# Re-enable the watchdog, but DO NOT cycle through more Exo URLs on a silent
# connection. Use the exact current working/request URL in VLC after 6.5 s.
old_watchdog = '''            if (false && item.kind == MediaKind.LIVE) {
                val attempt = index
                watchdogRunnable = Runnable {
                    if (!firstFrameRendered && activeUrl == attempt) {
                        val next = attempt + 1
                        if (next < playbackUrls.size) {
                            openUrl(next)
                        } else {
                            playbackError = "Live-Stream verbunden, aber kein Videobild empfangen. Alle Stream-Varianten wurden getestet."
                        }
                    }
                }.also { watchdogHandler.postDelayed(it, 6500L) }
            }'''
new_watchdog = '''            if (item.kind == MediaKind.LIVE) {
                val attempt = index
                watchdogRunnable = Runnable {
                    if (!firstFrameRendered && activeUrl == attempt && !manualPlayerChoice) {
                        val tracks = player.currentTracks
                        val hasAudio = tracks.containsType(C.TRACK_TYPE_AUDIO)
                        val hasVideo = tracks.containsType(C.TRACK_TYPE_VIDEO)
                        // Leave genuine audio-only streams on Exo when they are
                        // actually playing. A TV stream with a video track but no
                        // rendered frame, no audio track, or no playback progress
                        // is a real compatibility failure.
                        val needsCompatibilityPlayer = hasVideo || !hasAudio || !player.isPlaying
                        if (needsCompatibilityPlayer) {
                            compatibilityUrl = playbackUrls.getOrNull(attempt).orEmpty()
                            playbackError = ""
                            useVlc = true
                        }
                    }
                }.also { watchdogHandler.postDelayed(it, 6500L) }
            }'''
replace_once(player, old_watchdog, new_watchdog, 'Live first-frame compatibility watchdog')

# Decoder errors already switch to VLC immediately. For transport/HTTP/source
# errors we still try the next provider candidate first. If all candidates fail,
# give VLC the last exact request before showing a terminal error.
old_error_tail = '''                val next = activeUrl + 1
                if (next < playbackUrls.size) {
                    openUrl(next)
                } else {
                    val detail = httpCode?.let { "HTTP $it" } ?: error.errorCodeName
                    playbackError = "Der Anbieter hat alle kompatiblen Stream-Adressen abgelehnt. Letzter Fehler: $detail (Kandidat ${activeUrl + 1}/${playbackUrls.size})."
                }'''
new_error_tail = '''                val next = activeUrl + 1
                if (next < playbackUrls.size) {
                    openUrl(next)
                } else if (item.kind == MediaKind.LIVE && !manualPlayerChoice) {
                    compatibilityUrl = playbackUrls.getOrNull(activeUrl).orEmpty()
                    playbackError = ""
                    useVlc = true
                } else {
                    val detail = httpCode?.let { "HTTP $it" } ?: error.errorCodeName
                    playbackError = "Der Anbieter hat alle kompatiblen Stream-Adressen abgelehnt. Letzter Fehler: $detail (Kandidat ${activeUrl + 1}/${playbackUrls.size})."
                }'''
replace_once(player, old_error_tail, new_error_tail, 'Live exhausted-candidate VLC fallback')

checks = [
    (gradle, 'versionCode = 902'),
    (gradle, 'versionName = "0.9.2"'),
    (player, 'if (item.kind == MediaKind.LIVE) {'),
    (player, 'val tracks = player.currentTracks'),
    (player, 'val hasAudio = tracks.containsType(C.TRACK_TYPE_AUDIO)'),
    (player, 'val hasVideo = tracks.containsType(C.TRACK_TYPE_VIDEO)'),
    (player, 'val needsCompatibilityPlayer = hasVideo || !hasAudio || !player.isPlaying'),
    (player, 'compatibilityUrl = playbackUrls.getOrNull(attempt).orEmpty()'),
    (player, 'else if (item.kind == MediaKind.LIVE && !manualPlayerChoice)'),
    (player, 'useVlc = true'),
    (player, 'tracks.isTypeSupported(C.TRACK_TYPE_AUDIO)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.2 marker missing in {path}: {marker}")

if 'if (false && item.kind == MediaKind.LIVE)' in player.read_text():
    raise SystemExit("Disabled Live watchdog is still present")

print("Android 0.9.2 smart Exo-to-VLC Live fallback applied")
