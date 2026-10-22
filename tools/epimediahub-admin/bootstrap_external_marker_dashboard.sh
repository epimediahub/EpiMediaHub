#!/usr/bin/env bash
# One operator action: checked private Admin marker-list deployment.
set -Eeuo pipefail
umask 077
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required"; exit 2; }
for b in curl mktemp python3 bash; do
  command -v "$b" >/dev/null || { echo "STOP: missing $b"; exit 2; }
done
BASE=https://raw.githubusercontent.com/epimediahub/EpiMediaHub
REV=09ce61f0962ff6829a391285e38c0afb2f02fa05
OLD=104f041fd8d367f3b4c89e49f1e2eea9c94c0295
WORK="$(mktemp -d -t episcene-marker-dashboard.XXXXXXXX)"
trap 'rm -rf -- "$WORK"' EXIT
for name in mobile_flask.py native_external_markers.py \
            report_trusted_marker_series.py install_external_markers_dashboard.py; do
  case "$name" in
    report_trusted_marker_series.py) folder=tools/episcene-learning-v1/unified-marker-bridge ;;
    *) folder=tools/epimediahub-admin ;;
  esac
  curl --fail --location --silent --show-error --retry 2 --max-time 45 \
    "$BASE/$REV/$folder/$name" -o "$WORK/$name"
  [[ -s "$WORK/$name" ]] || { echo "STOP: incomplete marker dashboard release"; exit 2; }
done
curl --fail --location --silent --show-error --retry 2 --max-time 45 \
  "$BASE/$OLD/tools/epimediahub-admin/mobile_flask.py" \
  -o "$WORK/previous_mobile_flask.py"
[[ -s "$WORK/previous_mobile_flask.py" ]] || {
  echo "STOP: existing API baseline missing"; exit 2;
}
python3 -m py_compile "$WORK/"*.py
python3 "$WORK/install_external_markers_dashboard.py" --check
python3 "$WORK/install_external_markers_dashboard.py" --apply
echo "MARKER_OVERVIEW_READY_FOR_WEB_AND_NEXT_SIGNED_ANDROID_ADMIN_RELEASE"
