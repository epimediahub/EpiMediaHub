#!/usr/bin/env bash
set -euo pipefail

: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

SMARTTUBE_ROOT="$PROJECT_ROOT/.smarttube"
SHARED_ROOT="$SMARTTUBE_ROOT/SharedModules"
MEDIA_ROOT="$SMARTTUBE_ROOT/MediaServiceCore"

SHARED_SHA="13f5687dd6757b02fbcdf14c5403d0339e377db5"
MEDIA_SHA="f48669efbf1987266f5e1d89c392cd2422e8bcb3"

clone_pin() {
  local url="$1"
  local dir="$2"
  local sha="$3"
  rm -rf "$dir"
  mkdir -p "$dir"
  git init -q "$dir"
  git -C "$dir" remote add origin "$url"
  git -C "$dir" fetch -q --depth=1 origin "$sha"
  git -C "$dir" checkout -q --detach FETCH_HEAD
  test "$(git -C "$dir" rev-parse HEAD)" = "$sha"
}

clone_pin "https://github.com/yuliskov/SharedModules.git" "$SHARED_ROOT" "$SHARED_SHA"
clone_pin "https://github.com/yuliskov/MediaServiceCore.git" "$MEDIA_ROOT" "$MEDIA_SHA"

python3 - <<'PY'
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
smart = root / ".smarttube"
shared = smart / "SharedModules"
media = smart / "MediaServiceCore"

def replace_once(path: Path, old: str, new: str, label: str):
    value = path.read_text()
    if value.count(old) != 1:
        raise SystemExit(f"{label}: expected one anchor in {path}, got {value.count(old)}")
    path.write_text(value.replace(old, new, 1))

def add_namespace(path: Path, namespace: str, build_config: bool = False):
    text = path.read_text()
    anchor = "android {\n"
    if anchor not in text:
        raise SystemExit(f"android block missing: {path}")
    extra = f"android {{\n    namespace '{namespace}'\n"
    if build_config:
        extra += "    buildFeatures { buildConfig true }\n"
    text = text.replace(anchor, extra, 1)
    text = text.replace("        lintConfig rootProject.file('lint.xml')\n", "")
    text = text.replace("    lintConfig rootProject.file('lint.xml')\n", "")
    path.write_text(text)

# AGP 8 requires explicit namespaces for these older library modules.
add_namespace(shared / "sharedutils/build.gradle", "com.liskovsoft.sharedutils", True)
add_namespace(shared / "commons-io-2.8.0/build.gradle", "com.liskovsoft.commonsio")
add_namespace(shared / "j2v8/build.gradle", "com.liskovsoft.j2v8")
add_namespace(media / "mediaserviceinterfaces/build.gradle", "com.liskovsoft.mediaserviceinterfaces")
add_namespace(media / "youtubeapi/build.gradle", "com.liskovsoft.youtubeapi")

# Strip test-only project self references and old product flavors. The 1.0.0
# host uses one pinned SmartTube-core variant and packages the local j2v8 module.
for path in (
    shared / "sharedutils/build.gradle",
    shared / "j2v8/build.gradle",
    media / "youtubeapi/build.gradle",
):
    text = path.read_text()
    text = text.replace("    testImplementation project(path: ':sharedtests')\n", "")
    text = text.replace("    testImplementation project(path: ':sharedutils')\n", "")
    text = text.replace("    testImplementation project(':j2v8')\n", "")
    text = text.replace("    androidTestImplementation project(':j2v8')\n", "")
    text = text.replace("    testImplementation project(':youtubeapi')\n", "")
    text = text.replace("    androidTestImplementation project(':youtubeapi')\n", "")
    text = text.replace("    testImplementation project(':sharedtests')\n", "")
    text = text.replace("    androidTestImplementation project(':sharedtests')\n", "")
    text = text.replace("    androidTestImplementation project(path: ':sharedtests')\n", "")
    path.write_text(text)

yt = media / "youtubeapi/build.gradle"
text = yt.read_text()
start = text.find('    flavorDimensions "default"')
if start < 0:
    raise SystemExit("youtubeapi flavorDimensions anchor missing")
prod = text.find("    productFlavors {", start)
if prod < 0:
    raise SystemExit("youtubeapi productFlavors anchor missing")
brace = text.find("{", prod)
depth = 0
end = None
for i in range(brace, len(text)):
    if text[i] == "{":
        depth += 1
    elif text[i] == "}":
        depth -= 1
        if depth == 0:
            end = i + 1
            break
if end is None:
    raise SystemExit("youtubeapi productFlavors closing brace missing")
text = text[:start] + text[end:]
text = text.replace("    stbetaImplementation project(':j2v8')\n", "")
text = text.replace("    ststableImplementation project(':j2v8')\n", "")
text = text.replace("    stfdroidImplementation 'com.eclipsesource.j2v8:j2v8:' + j2v8Version + '@aar'\n",
                    "    implementation project(':j2v8')\n")
yt.write_text(text)

# The core is hosted by EpiMediaHub, so it must not make USB host capability a
# device-install requirement and must inherit the host's SDK declaration.
manifest = media / "youtubeapi/src/main/AndroidManifest.xml"
manifest.write_text("""<manifest xmlns:android=\"http://schemas.android.com/apk/res/android\"
    package=\"com.liskovsoft.youtubeapi\">
    <uses-permission android:name=\"android.permission.INTERNET\"/>
</manifest>
""")

# Make the Android library plugin available to old Groovy subprojects.
root_gradle = root / "build.gradle.kts"
rg = root_gradle.read_text()
if 'id("com.android.library")' not in rg:
    rg = rg.replace(
        'id("com.android.application") version "8.5.2" apply false',
        'id("com.android.application") version "8.5.2" apply false\n    id("com.android.library") version "8.5.2" apply false',
        1,
    )
root_gradle.write_text(rg)

settings = root / "settings.gradle.kts"
st = settings.read_text()
if 'https://jitpack.io' not in st:
    st = st.replace(
        'repositories { google(); mavenCentral() }',
        'repositories { google(); mavenCentral(); maven { url = uri("https://jitpack.io") } }',
        1,
    )
marker = 'include(":app")'
if marker not in st:
    raise SystemExit("host settings :app anchor missing")
extra = r'''
include(":sharedutils", ":commons-io-2.8.0", ":j2v8", ":mediaserviceinterfaces", ":youtubeapi")
project(":sharedutils").projectDir = file(".smarttube/SharedModules/sharedutils")
project(":commons-io-2.8.0").projectDir = file(".smarttube/SharedModules/commons-io-2.8.0")
project(":j2v8").projectDir = file(".smarttube/SharedModules/j2v8")
project(":mediaserviceinterfaces").projectDir = file(".smarttube/MediaServiceCore/mediaserviceinterfaces")
project(":youtubeapi").projectDir = file(".smarttube/MediaServiceCore/youtubeapi")
'''
if 'project(":youtubeapi")' not in st:
    st = st.replace(marker, marker + "\n" + extra, 1)
settings.write_text(st)

app = root / "app/build.gradle.kts"
ap = app.read_text()
dep = "dependencies {\n"
if dep not in ap:
    raise SystemExit("host dependencies block missing")
if 'implementation(project(":youtubeapi"))' not in ap:
    ap = ap.replace(dep, dep + '    implementation(project(":youtubeapi"))\n', 1)
app.write_text(ap)

# Preserve upstream attribution inside the APK.
assets = root / "app/src/main/assets/licenses"
assets.mkdir(parents=True, exist_ok=True)
(assets / "SmartTube-MIT.txt").write_text("""SmartTube
Copyright (c) 2020-present yuliskov

MIT License. Upstream project:
https://github.com/yuliskov/SmartTube

EpiMediaHub 1.0.0 integrates a pinned subset of SmartTube's media-service
architecture. Upstream SmartTube commit: a7212c531ac06ec87108180d5d8ab1bebebe528e
MediaServiceCore: f48669efbf1987266f5e1d89c392cd2422e8bcb3
SharedModules: 13f5687dd6757b02fbcdf14c5403d0339e377db5

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
""")

print("Pinned SmartTube media-service core prepared for EpiMediaHub")
PY
