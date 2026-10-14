#!/usr/bin/env bash
# One-step replacement of EpiScene's permanently deferred scene-reload gate.
# Preflight, exact digests, unit tests, source backup, activation + diagnostics.
set -Eeuo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo "STOP: root required";exit 2; }
REV=ccba3c208d59fcc91e9e8e7770deb9db6994f909
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$REV/tools/episcene-learning-v1/visual-peer-fix"
TARGET=/opt/episcene-learning/reload_when_idle.py
BACKUPS=/var/lib/epimediahub/visual-peer-fix-backups
UNIT=episcene-visual-peer-reload.service
TIMER=episcene-visual-peer-reload.timer
ANALYSIS_TIMER=epimediahub-skip-analysis.timer
PAUSED=/var/lib/epimediahub/episcene-visual-peer-analysis-timer-paused
PENDING=/var/lib/epimediahub/episcene-visual-peer-reload-pending
OLD=33d7516dd0277f6be943b763711f7a76b4ac3983e81ce1ff326a73c2d14941ea
NEW=477cb2e154a4f6061b591d59c3627dd7efca29020238ec9ede49190bb3514765
WORK="$(mktemp -d -t episcene-scene-reload.XXXXXXXX)"
BACKUP=""
trap 'rm -rf -- "$WORK"' EXIT
for cmd in python3 curl sha256sum systemctl install flock mktemp;do
  command -v "$cmd" >/dev/null || { echo "STOP: missing $cmd";exit 2; }
done
[[ -f "$TARGET" && ! -L "$TARGET" && -f "$PENDING" && ! -L "$PENDING" ]] || {
  echo "STOP: expected pending EpiScene scene reload unavailable";exit 2;
}
systemctl is-active --quiet "$TIMER" || {
  echo "STOP: existing scene reload timer is not active";exit 2;
}
if systemctl is-active --quiet "$UNIT";then
  echo 'STOP: existing reload is already running; wait until it finishes'
  exit 2
fi
systemctl show "$UNIT" -p ExecStart --value | grep -Fq "$TARGET" || {
  echo "STOP: reload unit points somewhere else";exit 2;
}
exec 9>/var/lib/epimediahub/.episcene-scene-reload-install.lock
flock -n 9 || { echo "STOP: concurrent scene reload install";exit 2; }
fetch() {
  local name="$1" digest="$2"
  curl -fsSL --retry 2 --max-time 45 "$BASE/$name" -o "$WORK/$name"
  printf '%s  %s\n' "$digest" "$WORK/$name" | sha256sum -c -
}
fetch reload_when_idle_v2.py "$NEW"
fetch test_reload_when_idle_v2.py 5d9351f3b1d8a175ffe6deabfb3f68a742276457d0e0c8ea7927a1ac084170b2
echo '=== Regression tests ==='
(cd "$WORK" && PYTHONDONTWRITEBYTECODE=1 python3 -m unittest -q test_reload_when_idle_v2)
echo '=== Current reload blocker (read-only) ==='
PYTHONDONTWRITEBYTECODE=1 python3 "$WORK/reload_when_idle_v2.py" --status
current="$(sha256sum "$TARGET" | cut -d' ' -f1)"
if [[ "$current" != "$OLD" && "$current" != "$NEW" ]];then
  echo 'STOP: live reload controller changed independently; no files modified'
  exit 2
fi
if [[ "$current" == "$NEW" ]];then
  echo 'ALREADY INSTALLED: updated scene reload drain'
else
  [[ ! -L "$BACKUPS" ]] || { echo 'STOP: backup directory symlink';exit 2; }
  install -d -m 0700 -o root -g root "$BACKUPS"
  BACKUP="$(mktemp "$BACKUPS/reload-original.XXXXXXXX.py")"
  cp -p -- "$TARGET" "$BACKUP"
  chmod 0600 "$BACKUP"
  python3 - "$TARGET" "$WORK/reload_when_idle_v2.py" "$OLD" <<'PY_INSTALL'
import hashlib,os,pathlib,stat,sys,tempfile
dest=pathlib.Path(sys.argv[1]);new=pathlib.Path(sys.argv[2]).read_bytes()
expected=sys.argv[3]
original=dest.read_bytes()
if hashlib.sha256(original).hexdigest()!=expected:
    raise RuntimeError('Live code changed since preflight')
st=dest.stat()
fd,tmp=tempfile.mkstemp(prefix='.reload-atomic-',dir=dest.parent)
try:
    with os.fdopen(fd,'wb') as out:
        out.write(new);out.flush();os.fsync(out.fileno())
    os.chown(tmp,st.st_uid,st.st_gid)
    os.chmod(tmp,stat.S_IMODE(st.st_mode))
    if dest.read_bytes()!=original:
        raise RuntimeError('Concurrent scene reload code edit')
    os.replace(tmp,dest)
    print('CONTROLLER UPDATED: backup stored; no database changes')
finally:
    if os.path.exists(tmp):os.unlink(tmp)
PY_INSTALL
fi
echo '=== Activate immediately if safe; otherwise bounded drain will retry ==='
if ! systemctl start "$UNIT";then
  if [[ -n "$BACKUP" ]];then
    cp -p -- "$BACKUP" "$TARGET"
  fi
  # An unsuccessful first drain must not leave new-job scheduling paused
  # after its owner script was rolled back.
  if [[ -f "$PAUSED" && ! -L "$PAUSED" ]];then
    systemctl start "$ANALYSIS_TIMER" || :
    rm -f -- "$PAUSED"
  fi
  echo "STOP: reload job failed; controller restored, timer recovery attempted"
  systemctl status "$UNIT" --no-pager || :
  exit 3
fi
echo '=== Reload result and next automatic attempt ==='
journalctl -u "$UNIT" -n 9 --no-pager -o cat || :
systemctl is-active "$TIMER"
echo 'INSTALL OK: scene reload now drains scheduled jobs without interrupting viewers or active batches.'
echo 'A playback lease will still defer reload; timer retries automatically.'
