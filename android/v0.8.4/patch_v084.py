#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))

def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace missing: {signature}")
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"closing brace missing: {signature}")

gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 803', 'versionCode = 805', 'versionCode')
replace_once(gradle, 'versionName = "0.8.3"', 'versionName = "0.8.5"', 'versionName')

for rel in ["ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.8.3", "0.8.5"))

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.8.3", "EpiMediaHub-Android/0.8.5"))

player = java / "ui/PlayerScreen.kt"
s = player.read_text()

start, end = function_span(s, "private fun V072UseVlcLiveFallback(item: MediaEntry)")
replacement = r'''private fun V072UseVlcLiveFallback(item: MediaEntry): Boolean {
    if (item.kind != MediaKind.LIVE) return false
    val label = item.name.trim()
    return Regex("""(?i)(?:^|[^A-Z0-9])(?:RAW|HEVC|H\.?265|MP2|MPGA)(?:$|[^A-Z0-9])""")
        .containsMatchIn(label)
}'''
s = s[:start] + replacement + s[end:]

# Make the compatibility intent explicit in LibVLC startup options. We keep
# hardware video decoding enabled, while LibVLC remains responsible for audio
# codec handling instead of Android MediaCodec support deciding per channel.
old_vlc = 'LibVLC(context, arrayListOf("--network-caching=900", "--clock-jitter=0", "--clock-synchro=0"))'
new_vlc = '''LibVLC(
            context,
            arrayListOf(
                "--network-caching=900",
                "--clock-jitter=0",
                "--clock-synchro=0",
                "--audio-replay-gain-mode=none"
            )
        )'''
if old_vlc not in s:
    raise SystemExit("LibVLC startup anchor missing")
s = s.replace(old_vlc, new_vlc, 1)
s = s.replace('media.setHWDecoderEnabled(true, false)', 'media.setHWDecoderEnabled(false, false)', 1)

player.write_text(s)

checks = [
    (gradle, 'versionName = "0.8.5"'),
    (gradle, 'versionCode = 805'),
    (player, 'RAW|HEVC|H\\.?265|MP2|MPGA'),
    (player, 'media.setHWDecoderEnabled(false, false)'),
    (player, '--audio-replay-gain-mode=none'),
    (player, 'V071VlcLivePlayer(vm, item, episodeList, accent, isTv)'),
    (player, 'org.videolan.libvlc'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing Android 0.8.4 marker {marker} in {path}")

print("Android 0.8.5 TV Live playback compatibility applied")
