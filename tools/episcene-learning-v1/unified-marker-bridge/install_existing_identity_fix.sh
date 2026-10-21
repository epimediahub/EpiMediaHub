#!/usr/bin/env bash
# EpiScene metadata-only prefetch update with exact-release verification.
# Original database, existing approvals, playback API and Android unchanged.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
[[ $# -eq 1 && ( "$1" == "--check" || "$1" == "--apply" ) ]] || {
  echo "Usage: bash install_existing_identity_fix.sh --check|--apply" >&2; exit 2;
}
[[ "$EUID" == 0 ]] || { echo "STOP: root required" >&2; exit 2; }
for cmd in python3 systemctl cp cmp install mv mktemp stat readlink; do
  command -v "$cmd" >/dev/null || { echo "STOP: missing $cmd" >&2; exit 2; }
done
PYTHON="$(readlink -f "$(command -v python3)")"
SOURCE="$(cd "$(dirname "$0")" && pwd -P)"
DEST=/opt/episcene-learning/unified
DATA=/var/lib/episcene-learning
FILES="bridge.py trusted_external.py trusted_external_sync.py"
NEWFILE=analysis_identity.py
[[ -d "$DEST" && ! -L "$DEST" && -d "$DATA" && ! -L "$DATA" ]] || {
  echo "STOP: installed EpiScene private bridge unavailable" >&2; exit 2;
}
[[ "$(stat -c '%a' "$DATA")" == "700" ]] || {
  echo "STOP: private store directory is not 0700" >&2; exit 2;
}
[[ -f /var/lib/epimediahub/provisioning.db &&
   ! -L /var/lib/epimediahub/provisioning.db ]] || {
  echo "STOP: original production source unavailable" >&2; exit 2;
}
for f in $FILES; do
  [[ -f "$DEST/$f" && ! -L "$DEST/$f" &&
     -f "$SOURCE/$f" && ! -L "$SOURCE/$f" &&
     -f "$SOURCE/baseline/$f" && ! -L "$SOURCE/baseline/$f" ]] || {
    echo "STOP: missing trusted baseline or new $f" >&2; exit 2;
  }
  cmp -s "$DEST/$f" "$SOURCE/baseline/$f" || {
    echo "STOP: installed $f differs from known release; no change made" >&2; exit 2;
  }
done
[[ ! -e "$DEST/$NEWFILE" && ! -L "$DEST/$NEWFILE" &&
   -f "$SOURCE/$NEWFILE" && ! -L "$SOURCE/$NEWFILE" ]] || {
  echo "STOP: identity patch already exists or missing" >&2; exit 2;
}
systemctl is-active --quiet episcene-trusted-sources.timer || {
  echo "STOP: original trusted source timer not active" >&2; exit 2;
}
! systemctl is-active --quiet episcene-trusted-sources.service || {
  echo "STOP: trusted source job active; no changes made" >&2; exit 2;
}
echo "=== Full isolated identity tests ==="
(cd "$SOURCE" && "$PYTHON" -m py_compile bridge.py trusted_external.py \
 trusted_external_sync.py analysis_identity.py &&
 "$PYTHON" -m unittest -q test_bridge test_trusted_external \
 test_trusted_external_sync test_analysis_identity)
echo "=== Read-only inventory probe ==="
(cd "$SOURCE" && "$PYTHON" -c '
from analysis_identity import catalog_batch
from pathlib import Path
import tempfile
with tempfile.TemporaryDirectory(dir="/var/lib/episcene-learning") as d:
    rows,status,meta=catalog_batch(
        "/var/lib/epimediahub/provisioning.db",
        Path(d)/"probe.sqlite3",limit=40)
print("identity_preflight_status:",status)
print("identity_candidates_checked:",meta["candidates"])
print("candidate_episodes_with_ids:",len(rows))
print("conflicting_identities_rejected:",meta["conflicts"])
')
if [[ "$1" == "--check" ]]; then
  echo "CHECK OK: installed service unchanged"
  exit 0
fi
BACKUP="$(mktemp -d -p "$DATA" trusted-id-fix-backup.XXXXXXXX)"
chmod 700 "$BACKUP"
for f in $FILES; do cp -p -- "$DEST/$f" "$BACKUP/$f"; done
ROLLED_BACK=0
SUCCESS=0
rollback() {
  if [[ "$SUCCESS" == 1 || "$ROLLED_BACK" == 1 ]]; then return 0; fi
  ROLLED_BACK=1
  echo "ROLLBACK: restoring previous trusted external modules" >&2
  for f in $FILES; do
    cp -p -- "$BACKUP/$f" "$DEST/.$f.recovery"
    mv -f -- "$DEST/.$f.recovery" "$DEST/$f"
  done
  rm -f -- "$DEST/$NEWFILE"
  systemctl enable --now episcene-trusted-sources.timer >/dev/null 2>&1 || true
}
trap 'rollback' EXIT
systemctl stop episcene-trusted-sources.timer
for f in $FILES "$NEWFILE"; do
  install -m 0644 -o root -g root "$SOURCE/$f" "$DEST/.$f.new"
  mv -f -- "$DEST/.$f.new" "$DEST/$f"
done
echo "=== First updated external ID lookup ==="
systemctl start episcene-trusted-sources.service
systemctl enable --now episcene-trusted-sources.timer
systemctl is-active --quiet episcene-trusted-sources.timer
SUCCESS=1
trap - EXIT
echo "EPISCENE EXISTING IDENTITY FIX INSTALLED"
echo "Previous revision backed up in private server directory."
echo "Only dedicated analysis inventories 8 and 10 were read."
echo "Original production database and Android app unchanged."
