#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

if [[ $# -ne 1 || ! "$1" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Aufruf: sudo bash install_catalogue_sync.sh <Git-Commit>"
  exit 2
fi
if [[ "$EUID" -ne 0 ]]; then
  echo "Bitte auf Hetzner mit sudo starten."
  exit 2
fi

release="$1"
target=/opt/episcene-learning/unified
service=episcene-trusted-sources.service
timer=episcene-trusted-sources.timer
files=(analysis_identity_balanced.py catalogue_sources.py trusted_external.py trusted_external_sync.py)
tests=(test_bridge.py test_trusted_external.py test_trusted_external_sync.py)
source_url="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$release/tools/episcene-learning-v1/unified-marker-bridge"

if [[ ! -d "$target" || -L "$target" ]] ||
   [[ "$(systemctl show "$timer" --property=LoadState --value)" != loaded ]] ||
   [[ "$(systemctl show "$service" --property=ExecStart --value)" != *"$target/trusted_external_sync.py"* ]]; then
  echo "Der vorhandene EpiScene-Online-Abgleich wurde an diesem Pfad nicht gefunden."
  exit 2
fi

exec 9>"$target/.catalogue-install.lock"
flock -w 30 9
stage="$(mktemp -d -t episcene-catalogue.XXXXXXXX)"
backup=""
stopped=0
changed=0
timer_active=0
cleanup() {
  local result=$?
  if (( result != 0 && changed )); then
    echo "Stelle die vorherigen Abgleichmodule aus $backup wieder her."
    for name in "${files[@]}"; do
      if [[ -f "$backup/$name" ]]; then
        cp -p -- "$backup/$name" "$target/.$name.restore"
        mv -f -- "$target/.$name.restore" "$target/$name"
      else
        rm -f -- "$target/$name"
      fi
    done
  fi
  if (( stopped && timer_active )); then
    systemctl start "$timer" || result=1
  fi
  rm -rf -- "$stage"
  exit "$result"
}
trap cleanup EXIT

for name in "${files[@]}" "${tests[@]}"; do
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$source_url/$name" --output "$stage/$name"
done
(
  cd "$stage"
  PYTHONPATH="$target" python3 -B -m unittest -q test_trusted_external test_trusted_external_sync
)

python3 -B - "$target" "$stage" <<'PY'
import hashlib
from pathlib import Path
import sys

target, stage = map(Path, sys.argv[1:])
baseline = {
    "analysis_identity_balanced.py": "05723a405cc2a85a1b57f4c7030e67c7dfcff979",
    "trusted_external.py": "c3a7cef17d65a0a3d34bcf0026838d163e3a16d6",
    "trusted_external_sync.py": "7f00334ed9140d5b7b8ab1a3f67522f9306e5c21",
}
for name in (*baseline, "catalogue_sources.py"):
    original = target / name
    if original.is_symlink():
        raise SystemExit(f"Unerwarteter symbolischer Link bei {name}.")
    if name == "catalogue_sources.py" and not original.exists():
        continue
    data = original.read_bytes()
    if data == (stage / name).read_bytes():
        continue
    git_blob = b"blob " + str(len(data)).encode() + b"\0" + data
    if hashlib.sha1(git_blob).hexdigest() != baseline.get(name):
        raise SystemExit(f"Serverversion von {name} weicht vom geprüften Stand ab.")
PY

backup="$(mktemp -d -p /var/backups episcene-katalog.XXXXXXXX)"
for name in "${files[@]}"; do
  if [[ -f "$target/$name" ]]; then
    cp -p -- "$target/$name" "$backup/$name"
  fi
done
if systemctl is-active --quiet "$timer"; then
  timer_active=1
fi
stopped=1
systemctl stop "$timer"
systemctl stop "$service"
changed=1
for name in "${files[@]}"; do
  install -m 0644 -o root -g root -- "$stage/$name" "$target/.$name.install"
  mv -f -- "$target/.$name.install" "$target/$name"
done
echo "Katalogabgleich für IntroDB und TheIntroDB startet."
systemctl start "$service"
systemctl start "$timer"
stopped=0
changed=0
echo "EpiScene-Katalogabgleich installiert. Sicherung: $backup"
journalctl -u "$service" -n 30 --no-pager -o cat
