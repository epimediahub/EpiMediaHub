#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"

bash build_tools/install_android_v062_source.sh
PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.6.3/run_v063_core.py

# The reconstructed 0.6.2 PlayerScreen no longer always contains the legacy
# TV-help overlay. Make that cleanup optional before applying the Live-TV patch.
python3 - <<'PY'
from pathlib import Path
p = Path('android/v0.6.3/patch_v063_player.py')
s = p.read_text()
old = '''# Keep the useful remote hint for VOD/episodes only. It must not appear over Live TV.
replace_once(
    '        if (isTv && controls) {\\n',
    '        if (isTv && controls && item.kind != MediaKind.LIVE) {\\n',
    'TV help overlay Live exclusion',
)
'''
new = '''# Keep the useful remote hint for VOD/episodes only when that legacy overlay exists.
legacy_tv_help = '        if (isTv && controls) {\\n'
if legacy_tv_help in s:
    s = s.replace(legacy_tv_help, '        if (isTv && controls && item.kind != MediaKind.LIVE) {\\n', 1)
'''
if old not in s:
    raise SystemExit('v0.6.3 player compatibility anchor missing')
s = s.replace(old, new, 1)
s = s.replace("assert 'if (isTv && controls && item.kind != MediaKind.LIVE)' in final\n", "")
p.write_text(s)
PY

PROJECT_ROOT="$PROJECT_ROOT" python3 android/v0.6.3/patch_v063_player.py

grep -q 'versionName = "0.6.3"' "$PROJECT_ROOT/app/build.gradle.kts"
grep -q 'versionCode = 603' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'sourceProfileId' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/model/Models.kt"
grep -Fq 'sourceProfile ?: _ui.value.active' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'catalogRows = emptyMap()' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq '_ui.value.active?.id != p.id' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/MainViewModel.kt"
grep -Fq 'urls += "$server/live/$user/$pass/$id"' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/XtreamClient.kt"
grep -Fq 'useController = item.kind != MediaKind.LIVE' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'if (item.kind == MediaKind.LIVE && controls)' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
grep -Fq 'EpiMediaHub beenden?' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/EpiMediaHubApp.kt"

echo "Android v0.6.3 source reconstructed successfully"
