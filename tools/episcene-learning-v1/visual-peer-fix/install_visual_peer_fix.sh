#!/usr/bin/env bash
# Install tested EpiScene independent-playlist scene proof and peer scheduler
# in ONE user action. Never weakens production release verification.
set -Eeuo pipefail
umask 077

[[ "$EUID" -eq 0 ]] || { echo 'STOP: root required';exit 2; }
REV=0e2a9a037048bdfbe85436248e792ad3025dce0d
ROOT="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/visual-peer-fix"
APP=/opt/epimediahub/provisioning
ENGINE=/opt/episcene-learning
SCENE="$APP/skip_scene.py"
VENV="$APP/.venv/bin/python"
DB=/var/lib/epimediahub/provisioning.db
SERVICE=episcene-safe-release-learning.service
DROP_DIR=/etc/systemd/system/$SERVICE.d
DROP="$DROP_DIR/50-peer-evidence.conf"
RELOAD_FILE=/var/lib/epimediahub/episcene-visual-peer-reload-pending
BACKUPS=/var/lib/epimediahub/visual-peer-fix-backups
TMP="$(mktemp -d -t episcene-visual-peer.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
for cmd in curl sha256sum python3 systemctl install stat flock cmp;do
  command -v "$cmd" >/dev/null || { echo "STOP: missing $cmd";exit 2; }
done
[[ -f "$SCENE" && ! -L "$SCENE" && -x "$VENV" && -d "$ENGINE" &&
   -f "$ENGINE/safe_release_rollout.py" && ! -L "$ENGINE/safe_release_rollout.py" &&
   -f "$DB" && ! -L "$DB" ]] || { echo 'STOP: expected live EpiScene deployment missing';exit 2; }
systemctl is-active --quiet "$SERVICE" && {
  echo 'STOP: maintenance already in progress';exit 2;
} || :
systemctl is-active --quiet episcene-safe-release-learning.timer || {
  echo 'STOP: existing EpiScene learning timer not active';exit 2;
}
exec 9>/var/lib/epimediahub/.episcene-visual-peer-installer.lock
flock -n 9 || { echo 'STOP: concurrent EpiScene install';exit 2; }

get() {
  local f="$1" hash="$2"
  curl -fsSL --retry 2 --max-time 45 "$ROOT/$f" -o "$TMP/$f"
  printf '%s  %s\n' "$hash" "$TMP/$f" | sha256sum -c -
}
get scene_fix.py 17e6758bc89a0b84824fde457799c2cb5e908419786df1fd1a8f77a60467a808
get safe_release_rollout_v2.py 6653aab53d22d5c2fa08a2163f42487bf7bd92b0a4658b6ef150156bf5fa49d2
get test_visual_peer_fix.py 49ea807a4db5b3ade03bda15acdda1619ce7cff90efc3585de9f206b3bf21edc
get reload_when_idle.py 98f0bc9bebedeaa3f3c7b03ef1ad7e870c47c48b0b9a64e22489bb604528c965

echo '=== Alle isolierten Regressionstests ==='
(cd "$TMP" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_visual_peer_fix)
echo '=== Check live independent analysis inventory / visual peers ==='
PYTHONPATH="$TMP:$ENGINE:$APP" PYTHONDONTWRITEBYTECODE=1 "$VENV" "$TMP/safe_release_rollout_v2.py" --audit-peers

echo '=== Check original learning service and scene sources ==='
echo "435a2e81fda3f430093e79118ad7f0df0ade359ea0cc48bb533f105f22dd07e7  $ENGINE/safe_release_rollout.py" | sha256sum -c -
python3 - "$SCENE" "$TMP" <<'PY_CHECK'
import importlib.util,pathlib,sys
scene=pathlib.Path(sys.argv[1])
folder=pathlib.Path(sys.argv[2])
spec=importlib.util.spec_from_file_location('scene_fix',folder/'scene_fix.py')
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
patch,changed=mod.patch(scene.read_text(encoding='utf-8'))
(folder/'skip_scene.patched.py').write_text(patch,encoding='utf-8')
print('SCENE PREFLIGHT OK:', 'PATCH_REQUIRED' if changed else 'ALREADY_FIXED')
PY_CHECK

[[ ! -L "$BACKUPS" && ! -L "$DROP" && ! -L "$ENGINE/safe_release_rollout_v2.py" &&
   ! -L "$ENGINE/reload_when_idle.py" ]] || { echo 'STOP: unexpected symlink';exit 2; }
for f in safe_release_rollout_v2.py reload_when_idle.py; do
  if [[ -e "$ENGINE/$f" ]] && ! cmp -s "$TMP/$f" "$ENGINE/$f";then
    echo "STOP: existing unknown version of $f";exit 2;
  fi
done
install -d -m 0700 -o root -g root "$BACKUPS"
BACKUP_NAME="$BACKUPS/scene-original-$(date +%Y%m%dT%H%M%S)-$$.py"
cp -p -- "$SCENE" "$BACKUP_NAME"
chmod 0600 "$BACKUP_NAME"
BACKUP_DB="$(mktemp "$BACKUPS/provisioning.XXXXXX.sqlite3")"
python3 - "$DB" "$BACKUP_DB" <<'PY_BACKUP'
import sqlite3,sys
source,dest=sys.argv[1:]
with sqlite3.connect('file:'+source+'?mode=ro',uri=True,timeout=30) as old:
    with sqlite3.connect(dest,timeout=30) as new:
        old.backup(new)
        if new.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise RuntimeError('Backup validation failed')
print('DB BACKUP OK')
PY_BACKUP
chmod 0600 "$BACKUP_DB"

# Exact, atomic scene source replacement; otherwise refusal and no service change.
python3 - "$SCENE" "$TMP/skip_scene.patched.py" <<'PY_APPLY'
import os,pathlib,sys,tempfile
source=pathlib.Path(sys.argv[1]);updated=pathlib.Path(sys.argv[2]).read_bytes()
original=source.read_bytes()
if original==updated:
    print('SCENE ALREADY PATCHED')
else:
    stat=source.stat()
    handle,name=tempfile.mkstemp(prefix='.skip_scene-visual-peer-',dir=source.parent)
    try:
        with os.fdopen(handle,'wb') as stream:
            stream.write(updated);stream.flush();os.fsync(stream.fileno())
        os.chown(name,stat.st_uid,stat.st_gid)
        os.chmod(name,stat.st_mode&0o7777)
        if source.read_bytes()!=original:raise RuntimeError('Concurrent scene source update')
        os.replace(name,source)
        print('SCENE INSTALLED (original backup preserved)')
    finally:
        if os.path.exists(name):os.unlink(name)
PY_APPLY

for f in safe_release_rollout_v2.py reload_when_idle.py;do
  if [[ ! -e "$ENGINE/$f" ]];then
    install -m 0644 -o root -g root "$TMP/$f" "$ENGINE/$f"
  fi
done
install -d -m 0755 -o root -g root "$DROP_DIR"
cat > "$TMP/override" <<'OVERRIDE'
[Service]
ExecStart=
ExecStart=/opt/epimediahub/provisioning/.venv/bin/python /opt/episcene-learning/safe_release_rollout_v2.py --apply
OVERRIDE
if [[ -e "$DROP" ]] && ! cmp -s "$DROP" "$TMP/override";then
  echo 'STOP: foreign systemd service override; refusing overwrite';exit 2;
fi
if [[ ! -e "$DROP" ]];then
  install -m 0644 -o root -g root "$TMP/override" "$DROP"
fi

cat > "$TMP/reload-service" <<'UNIT_SERVICE'
[Unit]
Description=Reload EpiScene visual worker when idle
After=epimediahub-provisioning.service
[Service]
Type=oneshot
User=root
Group=root
UMask=0077
ExecStart=/usr/bin/python3 /opt/episcene-learning/reload_when_idle.py
UNIT_SERVICE
cat > "$TMP/reload-timer" <<'UNIT_TIMER'
[Unit]
Description=Finish EpiScene safe scene reload when no viewer or worker is active
[Timer]
OnBootSec=2min
OnUnitInactiveSec=10min
Persistent=true
Unit=episcene-visual-peer-reload.service
[Install]
WantedBy=timers.target
UNIT_TIMER
for ext in service timer;do
  source="$TMP/reload-$ext"
  dest="/etc/systemd/system/episcene-visual-peer-reload.$ext"
  if [[ -L "$dest" ]] || { [[ -e "$dest" ]] && ! cmp -s "$source" "$dest"; };then
    echo "STOP: foreign reload $ext unit";exit 2;
  fi
  if [[ ! -e "$dest" ]];then
    install -m 0644 -o root -g root "$source" "$dest"
  fi
done

touch "$RELOAD_FILE"
chmod 0600 "$RELOAD_FILE"
systemctl daemon-reload
echo '=== One initial controlled visual peer scheduling run ==='
if ! systemctl start "$SERVICE";then
  echo 'STOP: scheduler failed; reverting service override and scene code'
  rm -f -- "$DROP"
  cp -p -- "$BACKUP_NAME" "$SCENE"
  systemctl daemon-reload
  exit 3
fi
echo '=== Worker/Web module reload: only when idle ==='
python3 "$ENGINE/reload_when_idle.py"
systemctl enable --now episcene-visual-peer-reload.timer >/dev/null
systemctl show "$SERVICE" -p Result -p ExecMainStatus --no-pager
systemctl is-active episcene-safe-release-learning.timer
systemctl is-active episcene-visual-peer-reload.timer
journalctl -u "$SERVICE" -n 33 --no-pager -o cat || :
echo 'INSTALL OK: independent scene lookup, 55s earlier outro visual inspection, bounded peer learning.'
echo 'No machine release threshold was reduced; confirmed manual records remain authoritative.'
echo 'SQLite backup and old scene source preserved. Pending reload is finished automatically when idle.'
