#!/usr/bin/env bash
# EpiScene 1-command READ-ONLY comparison of live, reviewed baseline and candidate.
# No updates, no DB writes, no restarts, no provider connections, no secrets.
set -Eeuo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo 'STOP: run as root for protected worker inventory'; exit 2; }
for bin in python3 curl mktemp;do command -v "$bin" >/dev/null || {
 echo "STOP: missing dependency"; exit 2;};done
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub"
# These are immutable GitHub commits (not moving branches).
TOOL_PIN="7f37b2f94179aa356376f12cc401d9169202fc5d"
BASELINE_PIN="a42a414eb6927d6ef31b7d7577ffa0d4e1ecce58"
CANDIDATE_PIN="a660258b415a4790bd97326ff5a06c8a07f6562e"
TARGET="tools/episcene-learning-v1/visual-peer-fix"
TMP="$(mktemp -d -t episcene-release-compat.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
fetch(){
 curl --proto '=https' --tlsv1.2 -fsSL --retry 2 \
   --connect-timeout 10 --max-time 45 "$BASE/$1/$TARGET/$2" -o "$TMP/$3"
 test -s "$TMP/$3" && test ! -L "$TMP/$3" || {
 echo 'STOP: missing pinned component'; exit 2; }
}
fetch "$TOOL_PIN" server_release_compatibility.py inspector.py
fetch "$BASELINE_PIN" safe_release_rollout_v2.py baseline.py
fetch "$CANDIDATE_PIN" safe_release_rollout_v2.py candidate.py
export PYTHONDONTWRITEBYTECODE=1
python3 - "$TMP" <<'PY_VERIFY'
import ast,pathlib,sys
folder=pathlib.Path(sys.argv[1])
for filename in ('inspector.py','baseline.py','candidate.py'):
    with (folder/filename).open('rb') as stream:
        ast.parse(stream.read(), filename=filename)
print('SOURCE_FORMAT_OK; no service touched')
PY_VERIFY
python3 "$TMP/inspector.py" --baseline "$TMP/baseline.py" --candidate "$TMP/candidate.py"
echo 'READ_ONLY_RELEASE_PREFLIGHT_DONE: Do NOT install candidate until full reviewed manifest and rollback ready.'
