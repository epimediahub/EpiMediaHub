#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?PROJECT_ROOT must point at the reconstructed Android project}"

bash build_tools/install_android_v098_source.sh

resource_dir="$PROJECT_ROOT/app/src/main/res"
if [[ ! -f "$resource_dir/raw/theme_catalog.json" || ! -f "$resource_dir/drawable-nodpi/brand_header.png" ]]; then
  temp_dir="$(mktemp -d)"
  trap 'rm -rf "$temp_dir"' EXIT
  ar p EpiMediaHub_v0.9.7.ipk data.tar.gz > "$temp_dir/data.tar.gz"
  tar --no-same-owner -xzf "$temp_dir/data.tar.gz" -C "$temp_dir"
  plugin="$temp_dir/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub"
  mkdir -p "$resource_dir/raw" "$resource_dir/drawable-nodpi"
  cp "$plugin/themes/catalog.json" "$resource_dir/raw/theme_catalog.json"
  cp "$plugin/header.png" "$resource_dir/drawable-nodpi/brand_header.png"
  cp "$plugin/header.png" "$resource_dir/drawable-nodpi/tv_banner.png"
  cp "$plugin/plugin.png" "$resource_dir/drawable-nodpi/app_icon.png"
  cp "$plugin/splash.png" "$resource_dir/drawable-nodpi/splash.png"
  cp "$plugin/home_live.png" "$resource_dir/drawable-nodpi/icon_live.png"
  cp "$plugin/home_movies.png" "$resource_dir/drawable-nodpi/icon_movies.png"
  cp "$plugin/home_series.png" "$resource_dir/drawable-nodpi/icon_series.png"
  cp "$plugin/home_settings.png" "$resource_dir/drawable-nodpi/icon_settings.png"
  cp "$plugin/home_playlist.png" "$resource_dir/drawable-nodpi/icon_playlist.png"
fi

python3 build_tools/augment_android_v097_skins.py
python3 android/v0.9.9/patch_v099.py
grep -Fq 'versionCode = 909' "$PROJECT_ROOT/app/build.gradle.kts"
grep -Fq 'officialMarkRes' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/data/ThemeRepository.kt"
grep -Fq 'V099CategoryCard' "$PROJECT_ROOT/app/src/main/java/de/epimediahub/app/ui/V079Themes.kt"
echo "Android 0.9.9 source reconstructed successfully"
