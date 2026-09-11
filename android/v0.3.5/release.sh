#!/usr/bin/env bash
set -euo pipefail

: "${ANDROID_KEYSTORE_B64:?ANDROID_KEYSTORE_B64 missing}"
: "${ANDROID_KEYSTORE_PASSWORD:?ANDROID_KEYSTORE_PASSWORD missing}"
: "${GITHUB_WORKSPACE:?GITHUB_WORKSPACE missing}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY missing}"
: "${GITHUB_SHA:?GITHUB_SHA missing}"

cd "$GITHUB_WORKSPACE"
rm -rf .ci-android dist
mkdir -p .ci-android
cat android/source_parts/source_* > .ci-android/source.b64
base64 --decode .ci-android/source.b64 > .ci-android/source.tar.gz
echo "192960b4363b3b9db132442d003717d3767f5c56e1b20b996cfb67e41656808c  .ci-android/source.tar.gz" | sha256sum -c -
tar -xzf .ci-android/source.tar.gz -C .ci-android
PROJECT_ROOT="$(find .ci-android -maxdepth 4 -name settings.gradle.kts -printf '%h\n' | head -n1)"
test -n "$PROJECT_ROOT"

cat > "$PROJECT_ROOT/build.gradle.kts" <<'EOF'
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
}
EOF
cat > "$PROJECT_ROOT/settings.gradle.kts" <<'EOF'
pluginManagement { repositories { google(); mavenCentral(); gradlePluginPortal() } }
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories { google(); mavenCentral() }
}
rootProject.name = "EpiMediaHubAndroid"
include(":app")
EOF

rm -rf "$PROJECT_ROOT/app/src/main/java"
rm -f "$PROJECT_ROOT/app/src/main/AndroidManifest.xml"
for version in v0.3.0 v0.3.1 v0.3.2 v0.3.3 v0.3.4 v0.3.5; do
    cp -a "android/$version/app/." "$PROJECT_ROOT/app/"
done

python3 - "$PROJECT_ROOT" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'app/src/main/java/de/epimediahub/app/ui/Screens.kt'
s=p.read_text()
s=s.replace('onClick={if(kind==MediaKind.SERIES){{vm.navigate(Screen.Episodes(m))}}else{{vm.play(m)}}}', 'onClick={if(kind==MediaKind.SERIES) vm.navigate(Screen.Episodes(m)) else vm.play(m)}')
s=s.replace('onClick={if(m.kind==MediaKind.SERIES){{vm.navigate(Screen.Episodes(m))}}else{{vm.play(m)}}}', 'onClick={if(m.kind==MediaKind.SERIES) vm.navigate(Screen.Episodes(m)) else vm.play(m)}')
s=s.replace('LinearProgressIndicator({it},Modifier.fillMaxWidth().padding(top=6.dp))', 'LinearProgressIndicator(progress={it},modifier=Modifier.fillMaxWidth().padding(top=6.dp))')
p.write_text(s)
PY

python3 android/v0.3.2/patch_screens.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
python3 android/v0.3.3/patch_mainviewmodel.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
python3 android/v0.3.3/patch_screens.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
python3 android/v0.3.4/patch_screens.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/Screens.kt"
python3 android/v0.3.5/patch_mainviewmodel.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
python3 android/v0.3.5/patch_app.py "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"

grep -q 'versionName = "0.3.5"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 35' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'V035HomeScreen' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"
grep -q 'fun openLibrary' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -q 'rememberBrowserPosition' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
test -f "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V035Screens.kt"
test -f "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/BrowserRows.kt"

mkdir -p .ci-android/ipk
(
    cd .ci-android/ipk
    ar x "$GITHUB_WORKSPACE/EpiMediaHub_v0.9.7.ipk"
    tar -xzf data.tar.gz
    PLUGIN="$PWD/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
    APP="$GITHUB_WORKSPACE/$PROJECT_ROOT/app/src/main"
    DRAW="$APP/res/drawable-nodpi"
    mkdir -p "$DRAW" "$APP/res/raw"
    for file in "$PLUGIN"/themes/*.png; do cp "$file" "$DRAW/theme_$(basename "$file")"; done
    for file in "$PLUGIN"/themes/marks/*.png; do cp "$file" "$DRAW/mark_$(basename "$file")"; done
    cp "$PLUGIN/themes/catalog.json" "$APP/res/raw/theme_catalog.json"
    cp "$PLUGIN/header.png" "$DRAW/brand_header.png"
    cp "$PLUGIN/header.png" "$DRAW/tv_banner.png"
    cp "$PLUGIN/plugin.png" "$DRAW/app_icon.png"
    cp "$PLUGIN/splash.png" "$DRAW/splash.png"
    cp "$PLUGIN/home_live.png" "$DRAW/icon_live.png"
    cp "$PLUGIN/home_movies.png" "$DRAW/icon_movies.png"
    cp "$PLUGIN/home_series.png" "$DRAW/icon_series.png"
    cp "$PLUGIN/home_search.png" "$DRAW/icon_search.png"
    cp "$PLUGIN/home_settings.png" "$DRAW/icon_settings.png"
    cp "$PLUGIN/home_playlist.png" "$DRAW/icon_playlist.png"
    test "$(find "$DRAW" -maxdepth 1 -type f -name 'theme_*.png' | wc -l)" -eq 59
    test "$(find "$DRAW" -maxdepth 1 -type f -name 'mark_*.png' | wc -l)" -eq 59
)

KEYSTORE="$RUNNER_TEMP/epimediahub-release.jks"
printf '%s' "$ANDROID_KEYSTORE_B64" | base64 --decode > "$KEYSTORE"
chmod 600 "$KEYSTORE"
keytool -list -keystore "$KEYSTORE" -storepass "$ANDROID_KEYSTORE_PASSWORD" -alias epimediahub >/dev/null
export ANDROID_KEYSTORE_PATH="$KEYSTORE"

python3 - "$PROJECT_ROOT" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])/'app/build.gradle.kts'
s=p.read_text()
anchor='    buildTypes {\n'
signing='''    signingConfigs {\n        create("release") {\n            storeFile = file(System.getenv("ANDROID_KEYSTORE_PATH"))\n            storePassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")\n            keyAlias = "epimediahub"\n            keyPassword = System.getenv("ANDROID_KEYSTORE_PASSWORD")\n        }\n    }\n\n'''
if anchor not in s: raise SystemExit('buildTypes anchor missing')
s=s.replace(anchor,signing+anchor,1)
s=s.replace('        release {\n            isMinifyEnabled = false','        release {\n            signingConfig = signingConfigs.getByName("release")\n            isMinifyEnabled = false',1)
p.write_text(s)
PY

(
    cd "$PROJECT_ROOT"
    gradle :app:assembleRelease --stacktrace --no-daemon
)

APK="$PROJECT_ROOT/app/build/outputs/apk/release/app-release.apk"
"$ANDROID_HOME/build-tools/35.0.0/apksigner" verify --verbose --print-certs "$APK" | tee /tmp/apk-signature.txt
CERT="$(grep -i 'certificate SHA-256 digest:' /tmp/apk-signature.txt | head -n1 | awk -F': ' '{print $2}' | tr -d ':' | tr '[:lower:]' '[:upper:]')"
test "$CERT" = "7939E7DDCBABA56F03D5FB0833D8A580B7797C12C4CCE378CA086C46F1B36D8E"

mkdir -p dist
cp "$APK" dist/EpiMediaHub-Android.apk
cp "$APK" dist/EpiMediaHub_Android_v0.3.5-release.apk
sha256sum dist/EpiMediaHub-Android.apk | tee dist/SHA256SUMS.txt

TAG="android-latest"
NOTES="Cleaner IBO-inspired navigation: Home now contains only Live TV, Movies, Series and Settings. Search and favorites are inside each library. On TV, categories stay in a left sidebar while content remains on the right. Returning from playback restores and focuses the last played row instead of jumping back to the top."
if gh release view "$TAG" >/dev/null 2>&1; then
    gh release upload "$TAG" dist/EpiMediaHub-Android.apk --clobber
    gh release edit "$TAG" --title "EpiMediaHub Android v0.3.5" --notes "$NOTES"
else
    gh release create "$TAG" dist/EpiMediaHub-Android.apk --target "$GITHUB_SHA" --title "EpiMediaHub Android v0.3.5" --notes "$NOTES"
fi

SHA="$(sha256sum dist/EpiMediaHub-Android.apk | awk '{print $1}')"
python3 - "$SHA" <<'PY'
import json,sys
from pathlib import Path
data={
  "version":"0.3.5",
  "versionCode":35,
  "url":"https://github.com/epimediahub/EpiMediaHub/releases/download/android-latest/EpiMediaHub-Android.apk",
  "sha256":sys.argv[1],
  "notes":"Reduzierte Startseite mit Live TV, Filme, Serien und Einstellungen. IBO-inspirierter TV-Browser mit Kategorien links und Inhalten rechts. Suche und Favoriten liegen im jeweiligen Bereich. Nach dem Beenden eines Senders kehrt die Liste zum zuletzt abgespielten Sender zurück und fokussiert ihn wieder."
}
Path('/tmp/update.json').write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
PY
FILE_SHA="$(gh api "repos/$GITHUB_REPOSITORY/contents/android/update.json?ref=main" --jq .sha)"
CONTENT="$(base64 -w0 /tmp/update.json)"
gh api --method PUT "repos/$GITHUB_REPOSITORY/contents/android/update.json" -f message="Update Android updater manifest to signed v0.3.5" -f content="$CONTENT" -f sha="$FILE_SHA" -f branch="main" >/dev/null

echo "https://github.com/epimediahub/EpiMediaHub/releases/download/android-latest/EpiMediaHub-Android.apk"
