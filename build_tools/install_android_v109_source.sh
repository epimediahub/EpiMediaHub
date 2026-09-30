#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v108_source.sh

RAW_DIR="$PROJECT_ROOT/app/src/main/res/raw"
mkdir -p "$RAW_DIR"
python3 build_tools/generate_intro_sound_v109.py   "$RAW_DIR/epimedia_intro_organic_orchestral_chime.wav"

python3 android/v1.0.9/patch_v109.py

grep -Fq 'versionCode = 1009' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'versionName = "1.0.9"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'V109IntroSound.play(context)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Intro.kt"
grep -Fq 'R.raw.epimedia_intro_organic_orchestral_chime' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V070Intro.kt"
test -s "$RAW_DIR/epimedia_intro_organic_orchestral_chime.wav"

python3 - "$RAW_DIR/epimedia_intro_organic_orchestral_chime.wav" <<'PY'
import sys, wave
with wave.open(sys.argv[1], "rb") as w:
    assert w.getnchannels() == 2
    assert w.getframerate() == 48000
    duration = w.getnframes() / w.getframerate()
    assert abs(duration - 2.85) < 0.001, duration
print("Android 1.0.9 intro WAV verified at 2.85 seconds")
PY

echo "Android 1.0.9 development source reconstructed successfully"
