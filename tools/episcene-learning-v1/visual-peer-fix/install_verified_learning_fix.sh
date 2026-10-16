#!/usr/bin/env bash
# Guarded, version-pinned EpiScene learning rollout. No analysis-worker restart.
set -Eeuo pipefail
umask 077
[[ "$EUID" == 0 ]] || { echo "STOP: root required";exit 2; }
for cmd in curl python3 systemctl install cp mv stat df flock awk; do command -v "$cmd" >/dev/null || exit 2;done

REV=8d239dab75c21107b85afab4918d593b4a3a5527
BASE=https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1
APP=/opt/epimediahub/provisioning
CODE=/opt/episcene-learning
DB=/var/lib/epimediahub/provisioning.db
PY=$APP/.venv/bin/python
SERVICE=episcene-safe-release-learning.service
TIMER=episcene-safe-release-learning.timer
A=$CODE/safe_release_rollout.py
B=$CODE/safe_release_rollout_v2.py
OLD_A=ad63fe10cf69841bc84bf795405de23ae4b9f5d7
OLD_B=4a0096c712dbc665ed4a875b7cd9189759bb682e
NEW_A=946f251068fc462678f64249103a8e07c75147c6
NEW_B=1351d2b41cf3159ca8fdfd2f3fb7bc5b97221d1e

work="$(mktemp -d -t epilern.XXXXXXXX)"
timer_paused=0
restore_timer(){
  if [[ "$timer_paused" == 1 ]]; then
    systemctl start "$TIMER" >/dev/null || echo "WARNING: unable to restart learning timer"
  fi
}
trap 'restore_timer;rm -rf -- "$work"' EXIT
blob(){
python3 - "$1" <<'PYCODE'
import sys,pathlib,hashlib
data=pathlib.Path(sys.argv[1]).read_bytes()
print(hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest())
PYCODE
}
fetch(){
  curl -fsSL --retry 2 --max-time 40 "$BASE/$1/$2" -o "$work/$2"
  [[ "$(blob "$work/$2")" == "$3" ]] || { echo "STOP: download hash mismatch: $2";exit 3; }
}

echo "=== 1/5: Validate existing versions and runtime ==="
[[ -x "$PY" ]] || { echo "STOP: expected Python venv missing";exit 2; }
for p in "$DB" "$A" "$B" "$CODE/feedback_learning.py" "$APP/skip_release.py";do
  [[ -f "$p" && ! -L "$p" ]] || { echo "STOP: missing or linked: $p";exit 2; }
done
systemctl cat "$SERVICE" >/dev/null
systemctl cat "$TIMER" >/dev/null
systemctl show "$SERVICE" -p ExecStart --value | grep -q 'safe_release_rollout_v2.py' || {
  echo "STOP: different production learning entrypoint; no change";exit 2;
}
[[ "$(stat -c %u "$A")" == 0 && "$(stat -c %u "$B")" == 0 ]] || {
  echo "STOP: unexpected code ownership";exit 2;
}
sha_a="$(blob "$A")";sha_b="$(blob "$B")"
[[ "$sha_a" == "$OLD_A" || "$sha_a" == "$NEW_A" ]] || {
  echo "STOP: custom release version $sha_a";exit 3;
}
[[ "$sha_b" == "$OLD_B" || "$sha_b" == "$NEW_B" ]] || {
  echo "STOP: custom peer version $sha_b";exit 3;
}
if [[ "$sha_a" == "$NEW_A" && "$sha_b" == "$NEW_B" ]];then
  echo "ALREADY_INSTALLED: both learning fixes present";exit 0;
fi

echo "=== 2/5: Download pinned reviewed code and syntax-check ==="
fetch safe-release-bundle safe_release_rollout.py "$NEW_A"
fetch visual-peer-fix safe_release_rollout_v2.py "$NEW_B"
"$PY" -m py_compile "$work/safe_release_rollout.py" "$work/safe_release_rollout_v2.py"
echo "=== 3/5: Read-only preflight ==="
PYTHONPATH="$work:$CODE:$APP" PYTHONDONTWRITEBYTECODE=1 \
  "$PY" "$work/safe_release_rollout.py" --check > "$work/check.json"
python3 - "$work/check.json" <<'PYCODE'
import json,sys
s=json.load(open(sys.argv[1]))
assert s.get("mode")=="PREFLIGHT_READ_ONLY"
print("Old manual marks:",s.get("old_manual_pending"),
      "eligible in first bounded batch:",s.get("eligible_exact_manual_marks"))
PYCODE

echo "=== 4/5: Stop only hourly learning timer and back up ==="
exec 9>/var/lib/epimediahub/.episcene-human-learning-installer.lock
flock -n 9 || { echo "STOP: installer already running";exit 2; }
if systemctl is-active --quiet "$TIMER";then
  systemctl stop "$TIMER";timer_paused=1
fi
if systemctl is-active --quiet "$SERVICE";then
  echo "STOP: learning service running; no files changed";exit 2;
fi
BACKUPS=/var/lib/epimediahub/episcene-learning-fix-backups
[[ ! -L "$BACKUPS" ]] || { echo "STOP: unexpected backup symlink";exit 2; }
install -d -m 0700 -o root -g root "$BACKUPS"
[[ "$(stat -c %u "$BACKUPS")" == 0 ]] || exit 2
STAMP="$(date -u +%Y%m%dT%H%M%SZ)-$$"
DEST="$BACKUPS/$STAMP"
install -d -m 0700 -o root -g root "$DEST"
cp -p "$A" "$DEST/safe_release_rollout.py"
cp -p "$B" "$DEST/safe_release_rollout_v2.py"
FREE="$(df -PB1 "$BACKUPS" | awk 'NR==2{print $4}')"
SIZE="$(stat -c %s "$DB")"
(( FREE >= SIZE*2+100000000 )) || { echo "STOP: not enough backup disk space";exit 2; }
python3 - "$DB" "$DEST/provisioning.sqlite3" <<'PYCODE'
import sqlite3,sys
with sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True,timeout=30) as src:
    with sqlite3.connect(sys.argv[2],timeout=30) as dst:
        src.backup(dst)
        assert dst.execute("PRAGMA quick_check").fetchone()[0]=="ok"
print("Database backup integrity verified")
PYCODE
chmod 0600 "$DEST/provisioning.sqlite3"
# Both replacement files are staged in the same filesystem for atomic renames.
install -m 0644 -o root -g root "$work/safe_release_rollout.py" "$CODE/.epilern-original-$$"
install -m 0644 -o root -g root "$work/safe_release_rollout_v2.py" "$CODE/.epilern-peer-$$"
mv -f "$CODE/.epilern-original-$$" "$A"
mv -f "$CODE/.epilern-peer-$$" "$B"
[[ "$(blob "$A")" == "$NEW_A" && "$(blob "$B")" == "$NEW_B" ]] || {
  cp -p "$DEST/safe_release_rollout.py" "$A"
  cp -p "$DEST/safe_release_rollout_v2.py" "$B"
  echo "STOP: verification mismatch; original code restored";exit 4;
}

echo "=== 5/5: Run existing guarded release/learning service once ==="
if ! systemctl start "$SERVICE";then
  echo "WARNING: service failed. Preserved code and DB backup: $DEST"
  echo "Original releases were not bypassed. See systemctl status of learning service."
  exit 5
fi
echo "VERIFIED_INSTALL_OK"
systemctl show "$SERVICE" -p Result -p ExecMainStatus --no-pager
echo "Backup directory: $DEST"
echo "Original analyzer and playback services were not restarted."
