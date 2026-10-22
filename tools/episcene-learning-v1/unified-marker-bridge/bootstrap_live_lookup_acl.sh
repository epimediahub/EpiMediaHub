#!/usr/bin/env bash
# EpiScene controlled live lookup: grant the existing API account ONLY
# traverse on the private directory and read on the trusted public-source
# cache; never run the API as root or publish the original EpiScene database.
set -Eeuo pipefail
umask 077
export PYTHONDONTWRITEBYTECODE=1
[[ $# -eq 1 && ( "$1" == "--check" || "$1" == "--apply" ) ]] || {
  echo "Usage: bash bootstrap_live_lookup_acl.sh --check|--apply" >&2; exit 2;
}
[[ "$(id -u)" -eq 0 ]] || { echo "STOP: root required" >&2; exit 2; }
for b in curl mktemp python3 systemctl stat getfacl setfacl runuser id; do
  command -v "$b" >/dev/null || {
    echo "STOP: missing $b (install ACL tools separately if necessary)" >&2; exit 2;
  }
done
UNIT=epimediahub-provisioning.service
KNOWLEDGE=/var/lib/episcene-learning
CACHE="$KNOWLEDGE/trusted-sources.sqlite3"
BACKEND=/opt/epimediahub/provisioning/skip_markers.py
[[ -d "$KNOWLEDGE" && ! -L "$KNOWLEDGE" &&
   -f "$CACHE" && ! -L "$CACHE" &&
   -f "$BACKEND" && ! -L "$BACKEND" ]] || {
  echo "STOP: expected knowledge cache or original API missing/symlink" >&2; exit 2;
}
# Respect existing cache ownership: EpiScene installations may store
# the private database under their dedicated sync account rather than root.
# The API must never own either resource, and neither can be world-accessible.
# An ACL grants *read only*, no chown or chmod to broaden access.
for resource in "$KNOWLEDGE" "$CACHE"; do
  perms="$(stat -c %a "$resource")"
  [[ "$perms" =~ ^[0-7]{3,4}$ ]] || {
    echo "STOP: unexpected private cache permissions" >&2; exit 2;
  }
  [[ "$((8#$perms & 7))" -eq 0 ]] || {
    echo "STOP: private cache is already accessible by other users" >&2; exit 2;
  }
done
systemctl is-active --quiet "$UNIT" || {
  echo "STOP: original device API not active" >&2; exit 2;
}
systemctl is-active --quiet episcene-trusted-sources.timer || {
  echo "STOP: trusted IntroDB/TheIntroDB timer not active" >&2; exit 2;
}
[[ "$(systemctl show -p DynamicUser --value "$UNIT")" != yes ]] || {
  echo "STOP: dynamic API service user needs alternative per-run read-only snapshot" >&2; exit 2;
}
SERVICE_USER="$(systemctl show -p User --value "$UNIT")"
if [[ -z "$SERVICE_USER" || "$SERVICE_USER" == root ]]; then
  echo "STOP: expected a non-root API service account; review unexpected changes" >&2
  exit 2
fi
[[ "$SERVICE_USER" =~ ^[a-z_][a-z0-9_-]{0,63}$ ]] || {
  echo "STOP: invalid service account identifier" >&2; exit 2;
}
id -u "$SERVICE_USER" >/dev/null || { echo "STOP: unknown API service account" >&2; exit 2; }
API_UID="$(id -u "$SERVICE_USER")"
for resource in "$KNOWLEDGE" "$CACHE"; do
  [[ "$(stat -c %u "$resource")" != "$API_UID" ]] || {
    echo "STOP: API account already owns private cache resource; "
    echo "read-only ACL cannot restrict a file owner" >&2
    exit 2
  }
done

# Review the unit namespace before assuming an ACL can give usable access.
ISOLATION="$(systemctl show -p InaccessiblePaths -p RootDirectory -p RootImage "$UNIT")"
if grep -Eq '/var/lib/episcene-learning|/var/lib($|[[:space:]])' <<< "$ISOLATION"; then
  echo "STOP: API systemd mount namespace blocks private cache path" >&2; exit 2;
fi

# Known reviewed revision. Update this immutable hash only after CI passes.
REV=68c4129edcc1c76c859f03863944181cadcdff74
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/unified-marker-bridge"
TEMP="$(mktemp -d -t episcene-api-acl.XXXXXXXX)"
trap 'rm -rf -- "$TEMP"' EXIT
for f in patch_live_lookup.py production_lookup_cache.py \
         test_patch_live_lookup.py test_production_lookup_cache.py; do
  curl --fail --silent --show-error --location --retry 2 --max-time 45 \
    "$BASE/$f" -o "$TEMP/$f"
  [[ -s "$TEMP/$f" ]] || { echo "STOP: incomplete reviewed release" >&2; exit 2; }
done
echo "=== EpiScene original lookup and cache regression tests ==="
(
 cd "$TEMP"
 python3 -m py_compile patch_live_lookup.py production_lookup_cache.py
 python3 -m unittest -q test_patch_live_lookup test_production_lookup_cache
)
# Validate the EXACT reviewed live handler without changing ACL, service or DB.
PYTHONPATH="$TEMP" python3 - <<'PY'
from patch_live_lookup import SOURCE, DEST, _function, patch_source, _regular, LIVE_HANDLER_SHA
import ast, hashlib, sqlite3
if not _regular(SOURCE):
    raise SystemExit("STOP: original server source unavailable")
if DEST.exists() or DEST.is_symlink():
    raise SystemExit("STOP: playback bridge already installed")
source=SOURCE.read_text(encoding="utf-8")
actual=hashlib.sha256(ast.dump(_function(source),
    include_attributes=False).encode()).hexdigest()[:16]
if actual!=LIVE_HANDLER_SHA:
    raise SystemExit("STOP: original live handler differs from approved source")
patch_source(source)
with sqlite3.connect("file:/var/lib/episcene-learning/trusted-sources.sqlite3?mode=ro",
                     uri=True, timeout=5) as c:
    c.execute("PRAGMA query_only=ON")
    c.execute("SELECT COUNT(*) FROM trusted_external_cache").fetchone()
print("EXACT_ORIGINAL_LOOKUP_AND_TRUSTED_CACHE_OK")
PY

if [[ "$1" == "--check" ]]; then
  echo "CHECK_OK: no production files or cache permissions modified."
  echo "API account needs least-privilege cache ACL during --apply."
  exit 0
fi

# Save both old ACLs, including original mode/mask. This is a private file
# unavailable to the API account; restoring it reverses only this change.
ACL_BACKUP="$(mktemp -p "$KNOWLEDGE" .lookup-acl-original.XXXXXXXX)"
chmod 600 "$ACL_BACKUP"
getfacl -p "$KNOWLEDGE" "$CACHE" > "$ACL_BACKUP"
COMPLETED=0
restore_on_failure() {
  local result=$?
  if [[ "$COMPLETED" == 0 ]]; then
    echo "ROLLBACK: restoring original EpiScene ACL permissions" >&2
    setfacl --restore="$ACL_BACKUP" || true
  fi
  rm -rf -- "$TEMP"
  exit "$result"
}
trap restore_on_failure EXIT
echo "=== Grant private directory traverse + trusted cache read to API account ==="
setfacl -m "u:$SERVICE_USER:--x" "$KNOWLEDGE"
setfacl -m "u:$SERVICE_USER:r--" "$CACHE"
# Verify actual effective read access as service account, including SQLite.
runuser -u "$SERVICE_USER" -- python3 - <<'PY'
import sqlite3
with sqlite3.connect("file:/var/lib/episcene-learning/trusted-sources.sqlite3?mode=ro",
                     uri=True, timeout=3) as db:
    db.execute("PRAGMA query_only=ON")
    db.execute("SELECT COUNT(*) FROM trusted_external_cache").fetchone()
from pathlib import Path
import os
cache=Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
private=cache.parent
if os.access(cache, os.W_OK, effective_ids=True):
    raise SystemExit("STOP: API can modify trusted cache")
if os.access(private, os.W_OK, effective_ids=True):
    raise SystemExit("STOP: API can modify private EpiScene directory")
print("LEAST_PRIVILEGE_API_READ_ONLY_ACCESS_CONFIRMED")
PY
echo "=== Repeat original guarded API preflight ==="
python3 "$TEMP/patch_live_lookup.py" check \
  --dependency "$TEMP/production_lookup_cache.py"
echo "=== Apply existing lookup extension with automatic rollback on restart failure ==="
python3 "$TEMP/patch_live_lookup.py" apply \
  --dependency "$TEMP/production_lookup_cache.py"
systemctl is-active --quiet "$UNIT"
systemctl is-active --quiet episcene-unified-sync.timer
systemctl is-active --quiet episcene-trusted-sources.timer
COMPLETED=1
trap 'rm -rf -- "$TEMP"' EXIT
echo "EPISCENE LEAST_PRIVILEGE LIVE LOOKUP INSTALL SUCCESS"
echo "Existing first-party approval data and customer playlists unchanged."
echo "The original device lookup was restarted; Fire TV end-to-end check still required."
