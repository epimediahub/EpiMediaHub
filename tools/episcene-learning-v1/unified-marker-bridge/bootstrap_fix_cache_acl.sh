#!/usr/bin/env bash
# EpiScene final trusted-source cache ACL repair.
# Only known reviewed runtime validator and two POSIX ACLs change.
# API receives no directory listing/write permission; prefetch stays private.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
[[ "$(id -u)" == 0 ]] || { echo "STOP: root required"; exit 2; }

for bin in curl cmp cp mv install stat systemctl getfacl setfacl runuser id mktemp python3 flock; do
  command -v "$bin" >/dev/null || { echo "STOP: $bin unavailable"; exit 2; }
done

ROOT=https://raw.githubusercontent.com/epimediahub/EpiMediaHub
SUB=tools/episcene-learning-v1/unified-marker-bridge
NEW=2317a84f118da7868cf60709e134eacd7fba7617
OLD=270d35fd4f7b4a064cdeb2b7cc70cd229c871de4
DEST=/opt/episcene-learning/unified
PRIVATE=/var/lib/episcene-learning
CACHE=$PRIVATE/trusted-sources.sqlite3
BASE=$DEST/runtime_integration.py
UNIT=episcene-trusted-sources.service
TIMER=episcene-trusted-sources.timer
API_UNIT=epimediahub-provisioning.service

[[ -d "$DEST" && ! -L "$DEST" &&
   -d "$PRIVATE" && ! -L "$PRIVATE" &&
   -f "$CACHE" && ! -L "$CACHE" &&
   -f "$BASE" && ! -L "$BASE" ]] || {
  echo "STOP: unexpected EpiScene installation"; exit 2;
}
systemctl is-active --quiet "$TIMER" || { echo "STOP: prefetch timer offline"; exit 2; }
systemctl is-active --quiet "$API_UNIT" || { echo "STOP: API offline"; exit 2; }
[[ "$(systemctl show -p User --value "$API_UNIT")" == epimediahub ]] || {
  echo "STOP: API account changed"; exit 2;
}
[[ "$(systemctl show -p DynamicUser --value "$API_UNIT")" != yes ]] || {
  echo "STOP: API DynamicUser unsupported"; exit 2;
}
API_UID="$(id -u epimediahub)"
[[ "$(stat -c %u "$PRIVATE")" != "$API_UID" &&
   "$(stat -c %u "$CACHE")" != "$API_UID" ]] || {
  echo "STOP: API must not own original private cache"; exit 2;
}
[[ "$(stat -c %a "$PRIVATE")" == 700 &&
   "$(stat -c %a "$CACHE")" == 600 ]] || {
  echo "STOP: expected masked private baseline (0700 / 0600)"; exit 2;
}
[[ "$(systemctl show "$UNIT" -p ActiveState --value)" == inactive ]] || {
  echo "STOP: prefetch one-shot running or failed; no changes"; exit 2;
}

exec 9>"$PRIVATE/.trusted-cache-acl-install.lock"
flock -n 9 || { echo "STOP: another installer active"; exit 2; }
WORK="$(mktemp -d -t episcene-safe-acl.XXXXXXXX)"
trap 'rm -rf -- "$WORK"' EXIT
for f in runtime_integration.py test_runtime_integration.py test_bridge.py; do
  curl -fsSL --retry 2 --max-time 45 "$ROOT/$NEW/$SUB/$f" -o "$WORK/$f"
  [[ -s "$WORK/$f" ]] || { echo "STOP: incomplete patch files"; exit 2; }
done
curl -fsSL --retry 2 --max-time 45 "$ROOT/$OLD/$SUB/runtime_integration.py" \
  -o "$WORK/old_runtime_integration.py"
cmp -s "$BASE" "$WORK/old_runtime_integration.py" || {
  echo "STOP: installed runtime validator differs from expected version"; exit 2;
}
echo "=== Strict cache ACL regression tests ==="
(
  cd "$WORK"
  PYTHONPATH="$WORK:$DEST" python3 -m py_compile runtime_integration.py test_runtime_integration.py test_bridge.py
  PYTHONPATH="$WORK:$DEST" python3 -m unittest -q test_runtime_integration
)

echo "=== Safeguard original cache ACL and validator ==="
BACKUP="$(mktemp -d -p "$PRIVATE" trusted-cache-acl-backup.XXXXXXXX)"
chmod 700 "$BACKUP"
cp -p "$BASE" "$BACKUP/runtime_integration.py"
getfacl -p "$PRIVATE" "$CACHE" > "$BACKUP/original.acl"
chmod 600 "$BACKUP/original.acl"
systemctl stop "$TIMER"
if [[ "$(systemctl show "$UNIT" -p ActiveState --value)" != inactive ]]; then
  systemctl start "$TIMER" || true
  echo "STOP: source service became busy; unchanged"; exit 2
fi

COMPLETE=0
CHANGED=0
rollback() {
  result=$?
  if [[ "$COMPLETE" == 0 ]]; then
    if [[ "$CHANGED" == 1 ]]; then
      echo "ROLLBACK: restore validator and original ACL" >&2
      cp -p "$BACKUP/runtime_integration.py" "$DEST/.runtime_integration.py.rollback"
      mv -f "$DEST/.runtime_integration.py.rollback" "$BASE"
      setfacl --restore="$BACKUP/original.acl" || true
    fi
    systemctl reset-failed "$UNIT" >/dev/null 2>&1 || true
    systemctl start "$TIMER" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$WORK"
  exit "$result"
}
trap rollback EXIT

CHANGED=1
install -o root -g root -m 0644 "$WORK/runtime_integration.py" \
  "$DEST/.runtime_integration.py.new"
mv -f "$DEST/.runtime_integration.py.new" "$BASE"

# POSIX mask is the effective permission of the named-user entries.
# Group-owner permissions and everyone-else permissions remain 0.
setfacl -m 'u:epimediahub:--x,m::--x' "$PRIVATE"
setfacl -m 'u:epimediahub:r--,m::r--' "$CACHE"

echo "=== Confirm EXACT restrictive ACL as root ==="
PYTHONPATH="$DEST" python3 - <<'PY'
from runtime_integration import _cache_path
from pathlib import Path
p=Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
assert _cache_path(p)==p
print("STRICT_READONLY_ACL_ACCEPTED_BY_PREFETCH")
PY
echo "=== Confirm genuine cache read, no write, under API account ==="
runuser -u epimediahub -- python3 - <<'PY'
import os,sqlite3
p="/var/lib/episcene-learning/trusted-sources.sqlite3"
with sqlite3.connect("file:"+p+"?mode=ro",uri=True,timeout=4) as db:
    db.execute("PRAGMA query_only=ON")
    n=db.execute("SELECT COUNT(*) FROM trusted_external_cache").fetchone()[0]
if os.access(p,os.W_OK,effective_ids=True):
    raise SystemExit("STOP: API can write trusted cache")
if os.access(os.path.dirname(p),os.W_OK,effective_ids=True):
    raise SystemExit("STOP: API can write EpiScene directory")
print("API_TRUSTED_MARKER_CACHE_READ_ONLY_OK",n)
PY

echo "=== Live prefetch under restrictive ACL ==="
systemctl start "$UNIT"
[[ "$(systemctl show "$UNIT" -p Result --value)" == success ]] || {
  echo "STOP: live prefetch failed"; exit 3;
}
systemctl start "$TIMER"
systemctl is-active --quiet "$TIMER" || {
  echo "STOP: prefetch timer not active"; exit 3;
}
systemctl is-active --quiet "$API_UNIT" || {
  echo "STOP: API unexpectedly inactive"; exit 3;
}
COMPLETE=1
trap 'rm -rf -- "$WORK"' EXIT
echo "EPISCENE PREFETCH AND API CACHE ACCESS VERIFIED"
echo "Original approved markers, device auth and customer DB untouched."
echo "Original ACL/validator backup: $BACKUP"
