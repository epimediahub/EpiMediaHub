#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT is required}"
: "${GITHUB_WORKSPACE:=$(pwd)}"

TMP="$GITHUB_WORKSPACE/.ci-android/ipk-v0941"
rm -rf "$TMP"
mkdir -p "$TMP"
cd "$TMP"
ar x "$GITHUB_WORKSPACE/EpiMediaHub_v0.9.41.ipk"
DATA_TAR=""
for candidate in data.tar.gz data.tar.xz data.tar.zst data.tar.bz2 data.tar; do
  if [ -f "$candidate" ]; then DATA_TAR="$candidate"; break; fi
done
test -n "$DATA_TAR"
case "$DATA_TAR" in
  *.tar.gz) tar -xzf "$DATA_TAR" ;;
  *.tar.xz) tar -xJf "$DATA_TAR" ;;
  *.tar.zst) tar --zstd -xf "$DATA_TAR" ;;
  *.tar.bz2) tar -xjf "$DATA_TAR" ;;
  *.tar) tar -xf "$DATA_TAR" ;;
esac
PLUGIN="$PWD/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
APP="$GITHUB_WORKSPACE/$PROJECT_ROOT/app/src/main"
DRAW="$APP/res/drawable-nodpi"
mkdir -p "$DRAW" "$APP/res/raw"
test -f "$PLUGIN/themes/catalog.json"

python3 - "$PLUGIN" "$DRAW" <<'PY'
import json,re,shutil,sys
from pathlib import Path
plugin=Path(sys.argv[1]); draw=Path(sys.argv[2])
catalog=json.loads((plugin/'themes/catalog.json').read_text())
def safe(v): return re.sub(r'[^a-z0-9_]+','_',str(v).lower()).strip('_')
family_count=0
for theme_id,meta in catalog.get('themes',{}).items():
    rid=safe(theme_id)
    if meta.get('family', False): family_count += 1
    bg=plugin/'themes'/str(meta.get('background',f'{theme_id}.png'))
    if bg.is_file(): shutil.copyfile(bg,draw/f'theme_{rid}.png')
    for folder,prefix in [('marks','mark'),('home_motifs','home_motif'),('center_marks','center_mark'),('banner_marks','banner_mark')]:
        src=plugin/'themes'/folder/f'{theme_id}.png'
        if src.is_file(): shutil.copyfile(src,draw/f'{prefix}_{rid}.png')
if family_count < 1: raise SystemExit('Frozen Enigma catalog contains no family=true themes')
print('Family themes in catalog:', family_count)
PY

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

test "$(find "$DRAW" -maxdepth 1 -type f -name 'theme_*.png' | wc -l)" -ge 50
test "$(find "$DRAW" -maxdepth 1 -type f -name 'mark_*.png' | wc -l)" -ge 50
test "$(find "$DRAW" -maxdepth 1 -type f -name 'home_motif_*.png' | wc -l)" -ge 1

echo "Enigma v0.9.41 assets imported"
