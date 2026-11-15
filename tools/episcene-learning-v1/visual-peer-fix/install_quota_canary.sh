#!/usr/bin/env bash
# Quota-only EpiScene canary: preserve custom live collect() and plan().
# Preflight, backup, fail-closed source hash, 13 worker versions, rollback.
set -Eeuo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo 'STOP: root needed';exit 2; }
for x in curl python3 sha256sum flock systemctl mktemp install cp;do
 command -v "$x" >/dev/null || { echo 'STOP: missing prerequisite';exit 2; }
done
LIVE=/opt/episcene-learning/safe_release_rollout_v2.py
ENGINE=/opt/episcene-learning
PROV=/opt/epimediahub/provisioning
REMOTE=/opt/epimediahub/analysis
VENV="$PROV/.venv/bin/python"
TIMER=episcene-safe-release-learning.timer
SERVICE=episcene-safe-release-learning.service
WORKER=epimediahub-analysis-worker.service
EXPECTED=1b5ddd15ab6a6c9c21c57a9b24daaec0e8872f4d61f9a2618532a77071060703
PATCH_URL=https://raw.githubusercontent.com/epimediahub/EpiMediaHub/fd36884618b76596252dd36ff27c378153a9213d/tools/episcene-learning-v1/visual-peer-fix/patch_live_quota_only.py
[[ -f "$LIVE" && ! -L "$LIVE" && -x "$VENV" &&
   -f "$PROV/skip_remote_protocol.py" && -d "$REMOTE" ]] || {
 echo 'STOP: server layout not verified';exit 2; }
exec 9>/var/lib/epimediahub/.episcene-canary.lock
flock -n 9 || { echo 'STOP: another EpiScene patch underway';exit 2; }
test "$(sha256sum "$LIVE" | cut -d ' ' -f1)" = "$EXPECTED" || {
 echo 'STOP: installed code changed since audit, no updates';exit 2; }
[[ "$(systemctl show "$SERVICE" -p LoadState --value)" == "loaded" &&
   "$(systemctl show "$SERVICE" -p Type --value)" == "oneshot" &&
   "$(systemctl show "$SERVICE" -p ActiveState --value)" == "inactive" ]] || {
 echo 'STOP: service unexpectedly running or not installed';exit 2; }
systemctl is-active --quiet "$TIMER" || {
 echo 'STOP: release timer inactive';exit 2; }
systemctl is-active --quiet "$WORKER" || {
 echo 'STOP: analysis worker inactive';exit 2; }
systemctl show "$SERVICE" -p ExecStart --value | grep -Fq "$LIVE" || {
 echo 'STOP: service uses a different controller';exit 2; }
TMP="$(mktemp -d -t episcene-quota.XXXXXXXX)"
PAUSED=0
PATCHED=0
BACKUP=""
cleanup(){
 local code=$?
 trap - EXIT
 if [[ "$code" -ne 0 ]];then
  if [[ "$PATCHED" -eq 1 && -n "$BACKUP" ]];then
   cp -p "$BACKUP" "$LIVE" || echo 'WARNING: restore failed, investigate before release' >&2
  fi
  if [[ "$PAUSED" -eq 1 ]];then
   systemctl start "$TIMER" || echo 'WARNING: timer restart failed' >&2
  fi
  echo 'CANARY_STOPPED: original worker functions preserved; recovery attempted' >&2
 fi
 rm -rf -- "$TMP"
 exit "$code"
}
trap cleanup EXIT
curl --proto '=https' --tlsv1.2 -fsSL --retry 2 --connect-timeout 10 --max-time 45 \
 "$PATCH_URL" -o "$TMP/patch.py"
test -s "$TMP/patch.py" || { echo 'STOP: tool missing';exit 2; }
python3 "$TMP/patch.py" --source "$LIVE" --output "$TMP/candidate.py"
PYTHONPATH="$ENGINE:$PROV" PYTHONDONTWRITEBYTECODE=1 \
 "$VENV" "$TMP/candidate.py" --audit-peers > "$TMP/audit.json" 2>"$TMP/audit.log" || {
 echo 'STOP: candidate failed read-only planner audit';exit 2; }
python3 - "$TMP/audit.json" <<'PY_AUDIT'
import json,sys
try: data=json.load(open(sys.argv[1],encoding='utf8'))
except (OSError,ValueError): raise SystemExit('STOP: no valid audit output')
if (data.get('mode')!='READ_ONLY_VISUAL_PEER_PREFLIGHT' or
    data.get('no_provider_reads') is not True or
    data.get('no_marker_approvals') is not True):
    raise SystemExit('STOP: audit safety contract changed')
print('CANARY_PLANNER_PREFLIGHT_OK')
PY_AUDIT
version_gate(){
 PROV="$PROV" "$VENV" - <<'PY_VERSION'
import contextlib,io,json,os,sys,urllib.request
sys.path.insert(0,os.environ['PROV'])
with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
 import skip_remote_protocol as protocol
 local=protocol.versions()
if not isinstance(local,dict) or len(local)!=13:
 raise SystemExit('STOP: expected 13 local protocol modules')
with urllib.request.urlopen('http://127.0.0.1:8790/health',timeout=5) as response:
 remote=json.loads(response.read(65536))
if remote.get('status')!='ok' or remote.get('versions')!=local:
 raise SystemExit('STOP: 13-component worker version mismatch')
print('WORKER_VERSION_GATE: 13/13 MATCH')
PY_VERSION
}
version_gate
FILES=( "$PROV/skip_analysis_worker.py" "$PROV/skip_schedule.py" \
 "$PROV/skip_scene.py" "$PROV/skip_release.py" "$REMOTE/skip_remote_worker.py" )
for f in "${FILES[@]}";do test -f "$f" && test ! -L "$f" || {
 echo 'STOP: unexpected worker file';exit 2; };done
sha256sum "${FILES[@]}" > "$TMP/worker.sha256"
systemctl stop "$TIMER"
PAUSED=1
[[ "$(systemctl show "$SERVICE" -p ActiveState --value)" == "inactive" ]] || {
 echo 'STOP: learning service became active';exit 2; }
test "$(sha256sum "$LIVE" | cut -d ' ' -f1)" = "$EXPECTED" || {
 echo 'STOP: concurrent live modification';exit 2; }
BACKUP_DIR=/var/lib/epimediahub/episcene-canary-backups
[[ ! -L "$BACKUP_DIR" ]] || { echo 'STOP: unsafe backup dir';exit 2; }
install -d -m 0700 "$BACKUP_DIR"
BACKUP="$(mktemp "$BACKUP_DIR/safe_release_before.XXXXXXXX.py")"
cp -p "$LIVE" "$BACKUP"
chmod 0600 "$BACKUP"
python3 - "$LIVE" "$TMP/candidate.py" "$EXPECTED" <<'PY_SWAP'
import hashlib,os,pathlib,stat,sys,tempfile
target=pathlib.Path(sys.argv[1]);candidate=pathlib.Path(sys.argv[2])
expected=sys.argv[3]
if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
 raise SystemExit('STOP: concurrent source change')
st=target.stat()
fd,name=tempfile.mkstemp(prefix='.episcene-atomic-',dir=target.parent)
try:
 with os.fdopen(fd,'wb') as f:
  f.write(candidate.read_bytes());f.flush();os.fsync(f.fileno())
 os.chown(name,st.st_uid,st.st_gid)
 os.chmod(name,stat.S_IMODE(st.st_mode))
 if hashlib.sha256(target.read_bytes()).hexdigest()!=expected:
  raise SystemExit('STOP: source changed during staging')
 os.replace(name,target)
finally:
 if os.path.exists(name):os.unlink(name)
PY_SWAP
PATCHED=1
sha256sum -c "$TMP/worker.sha256" >/dev/null || {
 echo 'STOP: unrelated worker source changed';exit 2; }
version_gate
systemctl start "$TIMER"
systemctl is-active --quiet "$TIMER" || {
 echo 'STOP: release timer not restored';exit 2; }
PAUSED=0
echo 'CANARY_OK: only quotas 4/8/2 -> 6/16/3; collect/plan and 13 worker versions preserved'
echo 'Existing release timer handles subsequent jobs; no worker was restarted'
