#!/usr/bin/env bash
# EpiScene independent analysis ownership: one-shot, pinned and fail-closed.
# DOES NOT change any marker if the production eligibility preflight stays zero.
set -Eeuo pipefail
umask 077

[[ "$EUID" == 0 ]] || { echo 'STOP: root required';exit 2; }
for cmd in curl python3 systemctl install cp mv stat df flock awk;do
  command -v "$cmd" >/dev/null || { echo "STOP: missing $cmd";exit 2; }
done

REV=a280113ae36586ec05b18a988ff597e372c57453
BASE=https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/safe-release-bundle
CODE=/opt/episcene-learning
APP=/opt/epimediahub/provisioning
DB=/var/lib/epimediahub/provisioning.db
PY=$APP/.venv/bin/python
SERVICE=episcene-safe-release-learning.service
TIMER=episcene-safe-release-learning.timer
ORIGINAL=$CODE/safe_release_rollout.py
FEEDBACK=$CODE/feedback_learning.py
PEER=$CODE/safe_release_rollout_v2.py

OLD_ORIGINAL=946f251068fc462678f64249103a8e07c75147c6
NEW_ORIGINAL=b18a584d8af5d9d95d4ffe8960d828c28ac8dbc3
OLD_FEEDBACK=1480af391d48226f76cb34ee4c43381184f5954b
NEW_FEEDBACK=8f02ddf6d034ed698ae484e7d96ca695db3ea17f
REQUIRED_PEER=1351d2b41cf3159ca8fdfd2f3fb7bc5b97221d1e

work="$(mktemp -d -t episcene-source-fix.XXXXXXXX)"
timer_paused=0
cleanup() {
  if [[ "$timer_paused" == 1 ]];then
    systemctl start "$TIMER" >/dev/null || echo 'WARNING: timer restart failed'
  fi
  rm -rf -- "$work"
}
trap cleanup EXIT
blob_sha() {
  python3 - "$1" <<'PY'
from pathlib import Path
import hashlib,sys
b=Path(sys.argv[1]).read_bytes()
print(hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest())
PY
}
fetch() {
  curl -fsSL --retry 2 --max-time 45 "$BASE/$1" -o "$work/$1"
  [[ "$(blob_sha "$work/$1")" == "$2" ]] || {
    echo "STOP: remote file version mismatch: $1"; exit 3;
  }
}

echo "=== Analysis-source ownership fix: validate ==="
[[ -x "$PY" ]] || { echo 'STOP: Python venv unavailable';exit 2; }
for file in "$ORIGINAL" "$FEEDBACK" "$PEER" "$DB" "$APP/skip_release.py";do
  [[ -f "$file" && ! -L "$file" ]] || { echo "STOP: missing/linked $file";exit 2; }
done
systemctl cat "$SERVICE" >/dev/null
systemctl cat "$TIMER" >/dev/null
systemctl show "$SERVICE" -p ExecStart --value | grep -q 'safe_release_rollout_v2.py' || {
  echo 'STOP: custom learning service entrypoint; no writes';exit 3;
}
[[ "$(blob_sha "$PEER")" == "$REQUIRED_PEER" ]] || {
  echo 'STOP: unexpected peer planner version; no writes';exit 3;
}
current_o="$(blob_sha "$ORIGINAL")"
current_f="$(blob_sha "$FEEDBACK")"
[[ "$current_o" == "$OLD_ORIGINAL" || "$current_o" == "$NEW_ORIGINAL" ]] || {
  echo 'STOP: unexpected local release version';exit 3;
}
[[ "$current_f" == "$OLD_FEEDBACK" || "$current_f" == "$NEW_FEEDBACK" ]] || {
  echo 'STOP: unexpected feedback exporter version';exit 3;
}
if [[ "$current_o" == "$NEW_ORIGINAL" && "$current_f" == "$NEW_FEEDBACK" ]];then
  echo 'ALREADY_INSTALLED: independent analysis ownership repair';exit 0;
fi
fetch safe_release_rollout.py "$NEW_ORIGINAL"
fetch feedback_learning.py "$NEW_FEEDBACK"
"$PY" -m py_compile "$work/safe_release_rollout.py" "$work/feedback_learning.py"

echo '=== Production evidence preflight (no writes) ==='
PYTHONPATH="$work:$CODE:$APP" PYTHONDONTWRITEBYTECODE=1 \
  "$PY" "$work/safe_release_rollout.py" --check > "$work/preflight.json"
PYTHONPATH="$work:$CODE:$APP" PYTHONDONTWRITEBYTECODE=1 \
  "$PY" "$work/feedback_learning.py" --check > "$work/feedback.json"
python3 - "$work/preflight.json" "$work/feedback.json" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
l=json.load(open(sys.argv[2]))
assert m.get('mode')=='PREFLIGHT_READ_ONLY'
assert l.get('mode')=='FEEDBACK_PREFLIGHT_READ_ONLY'
print('Manuelle Einträge:',m.get('old_manual_pending'),
      'nach Quellenkorrektur gültig:',m.get('eligible_exact_manual_marks'))
print('Nicht freigabefähig (aggregiert):',
      json.dumps(m.get('excluded',{}),sort_keys=True))
print('Verwertbare Lernmarkierungen:',l.get('eligible'))
if not m.get('eligible_exact_manual_marks',0):
    print('STOP: Noch immer keine sicher bestätigbare manuelle Markierung.')
    print('Keine Installation; keine Freigaben. Ursache liegt in fehlender')
    print('Geräteherkunft oder einer nicht nachweisbaren Provider-Datei.')
    raise SystemExit(4)
PY

echo '=== Safe backup and bounded apply ==='
exec 9>/var/lib/epimediahub/.episcene-independent-source-installer.lock
flock -n 9 || { echo 'STOP: another rollout running';exit 2; }
if systemctl is-active --quiet "$TIMER";then
  systemctl stop "$TIMER";timer_paused=1
fi
if systemctl is-active --quiet "$SERVICE";then
  echo 'STOP: existing learning service active';exit 2;
fi
backup_root=/var/lib/epimediahub/episcene-independent-analysis-backups
[[ ! -L "$backup_root" ]] || { echo 'STOP: backup directory is linked';exit 2; }
install -d -o root -g root -m 0700 "$backup_root"
[[ "$(stat -c %u "$backup_root")" == 0 ]] || exit 2
dest="$backup_root/$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -d -o root -g root -m 0700 "$dest"
cp -p "$ORIGINAL" "$dest/safe_release_rollout.py"
cp -p "$FEEDBACK" "$dest/feedback_learning.py"
chmod 0600 "$dest"/*.py
free="$(df -PB1 "$backup_root" | awk 'NR==2{print $4}')"
size="$(stat -c %s "$DB")"
((free > 2*size+100000000)) || { echo 'STOP: insufficient backup space';exit 2; }
python3 - "$DB" "$dest/provisioning.sqlite3" <<'PY'
import sqlite3,sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True,timeout=30) as src:
    with sqlite3.connect(sys.argv[2],timeout=30) as target:
        src.backup(target)
        assert target.execute('PRAGMA quick_check').fetchone()[0]=='ok'
print('SQLite backup verified')
PY
chmod 0600 "$dest/provisioning.sqlite3"
install -m 0644 -o root -g root "$work/safe_release_rollout.py" "$CODE/.episcene-independent-release-$$"
install -m 0644 -o root -g root "$work/feedback_learning.py" "$CODE/.episcene-independent-feedback-$$"
mv -f "$CODE/.episcene-independent-release-$$" "$ORIGINAL"
mv -f "$CODE/.episcene-independent-feedback-$$" "$FEEDBACK"
if [[ "$(blob_sha "$ORIGINAL")" != "$NEW_ORIGINAL" ||
      "$(blob_sha "$FEEDBACK")" != "$NEW_FEEDBACK" ]];then
  cp -p "$dest/safe_release_rollout.py" "$ORIGINAL"
  cp -p "$dest/feedback_learning.py" "$FEEDBACK"
  echo 'STOP: code verification failed; restored old code';exit 5;
fi

echo '=== Run existing guarded release and feedback workflow ==='
if ! systemctl start "$SERVICE";then
  echo "WARNING: learning workflow failed. Backups: $dest"
  echo 'No database rollback: other services may have written concurrently.'
  exit 6
fi
echo 'VERIFIED_INDEPENDENT_SOURCE_INSTALL_OK'
systemctl show "$SERVICE" -p Result -p ExecMainStatus --no-pager
echo "Backup: $dest"
echo 'Analysis workers and customer apps were not restarted.'
