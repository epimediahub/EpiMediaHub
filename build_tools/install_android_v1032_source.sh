#!/usr/bin/env bash
set -euo pipefail
: "${PROJECT_ROOT:?Missing PROJECT_ROOT}"
bash build_tools/install_android_v1031_source.sh
python3 build_tools/install_skin_assets_v132.py
python3 android/v1.0.32/patch_v132.py
python3 build_tools/verify_skin_assets_v132.py
