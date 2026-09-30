#!/usr/bin/env bash
set -Eeuo pipefail
if [ "$(id -u)" -ne 0 ]; then
  echo 'Bitte als root starten: sudo bash upgrade_to_v082.sh' >&2
  exit 1
fi
export EPIMEDIAHUB_UPGRADE_BRANCH="${EPIMEDIAHUB_UPGRADE_BRANCH:-raspberry-v0.8.2-skip-markers}"
export EPIMEDIAHUB_TARGET_VERSION="0.8.2"
export EPIMEDIAHUB_DASHBOARD_MODULE="dashboard_v080.py"
export EPIMEDIAHUB_SMOKE_TEST="tests/smoke_v082.py"
mkdir -p /var/tmp
export TMPDIR=/var/tmp
task_dir="$(mktemp -d -p /var/tmp epimediahub-v082.XXXXXX)"
trap 'rm -rf "$task_dir"' EXIT
raw_branch="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${EPIMEDIAHUB_UPGRADE_BRANCH}/server/epimediahub_provisioning/deploy"
core_ref="9f9b64da18d0b76e9c28ea39725e9d95ca4ddbeb"
curl -fsSL "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/${core_ref}/server/epimediahub_provisioning/deploy/upgrade_to_v052.sh" -o "$task_dir/core.sh"
curl -fsSL "$raw_branch/epimediahub-skip-analysis.service" -o "$task_dir/analysis.service"
curl -fsSL "$raw_branch/epimediahub-skip-analysis.timer" -o "$task_dir/analysis.timer"
apt-get update
apt-get install -y ffmpeg libchromaprint1
# The established upgrader backs up code, secrets and SQLite and rolls back on failure.
bash "$task_dir/core.sh"
install -m 0644 "$task_dir/analysis.service" /etc/systemd/system/epimediahub-skip-analysis.service
install -m 0644 "$task_dir/analysis.timer" /etc/systemd/system/epimediahub-skip-analysis.timer
systemctl daemon-reload
systemctl enable --now epimediahub-skip-analysis.timer
curl -fsS http://127.0.0.1:8787/health
echo
echo 'Raspberry 0.8.2 ist aktiv. Zeitmarken prüfen: https://admin.epimediahub.com/admin/skip'
echo 'Audioanalyse je Playlist im Dashboard aktivieren, wenn der Anbieter eine zusätzliche Verbindung erlaubt.'
