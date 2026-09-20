#!/usr/bin/env bash
set -Eeuo pipefail

BRANCH="${EPIMEDIAHUB_UPGRADE_BRANCH:-raspberry-v0.6.0-dashboard}"
RAW="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${BRANCH}/server/epimediahub_provisioning/deploy"

install -d -m 0755 /usr/local/lib/epimediahub
install -d -m 0755 /srv/epimediahub-downloads/android
install -d -m 0755 /etc/default

curl -fsSL "${RAW}/sync_android_release.py" -o /usr/local/lib/epimediahub/sync_android_release.py
chmod 0755 /usr/local/lib/epimediahub/sync_android_release.py

curl -fsSL "${RAW}/epimediahub-android-sync.service" -o /etc/systemd/system/epimediahub-android-sync.service
curl -fsSL "${RAW}/epimediahub-android-sync.timer" -o /etc/systemd/system/epimediahub-android-sync.timer
chmod 0644 /etc/systemd/system/epimediahub-android-sync.service /etc/systemd/system/epimediahub-android-sync.timer

if [[ ! -f /etc/default/epimediahub-android-sync ]]; then
  cat > /etc/default/epimediahub-android-sync <<'EOF'
EPIMEDIAHUB_RELEASE_REPO=epimediahub/EpiMediaHub
EPIMEDIAHUB_DOWNLOAD_DIR=/srv/epimediahub-downloads/android
EPIMEDIAHUB_SYNC_STATUS=/srv/epimediahub-downloads/android/sync-status.json
EOF
  chmod 0644 /etc/default/epimediahub-android-sync
fi

systemctl daemon-reload
systemctl enable --now epimediahub-android-sync.timer
systemctl start epimediahub-android-sync.service

echo
echo "=== Android release sync ==="
systemctl --no-pager --full status epimediahub-android-sync.service || true
echo
echo "=== Timer ==="
systemctl --no-pager list-timers epimediahub-android-sync.timer || true
echo
echo "=== Sync status ==="
cat /srv/epimediahub-downloads/android/sync-status.json 2>/dev/null || true
