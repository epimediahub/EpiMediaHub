#!/usr/bin/env bash
# One-paste, read-only private EpiScene function compatibility audit.
# Neither this script nor its Python verifier installs/restarts anything.
set -Eeuo pipefail
umask 077
[[ "${EUID}" -eq 0 ]] || { echo 'STOP: run with sudo'; exit 2; }
for tool in curl python3 mktemp;do
 command -v "$tool" >/dev/null || { echo 'STOP: required program missing'; exit 2; }
done
TOOL_REV=27e3c7b02d3fff4793082e374770700ebee845df
BASE_REV=a42a414eb6927d6ef31b7d7577ffa0d4e1ecce58
CAND_REV=a660258b415a4790bd97326ff5a06c8a07f6562e
BASE_URL=https://raw.githubusercontent.com/epimediahub/EpiMediaHub
DIRECTORY=tools/episcene-learning-v1/visual-peer-fix
TMP="$(mktemp -d -t episcene-merge-audit.XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
download(){
 curl --proto '=https' --tlsv1.2 -fsSL --retry 2 --connect-timeout 10 \
   --max-time 50 "$BASE_URL/$1/$DIRECTORY/$2" -o "$TMP/$3"
 [[ -s "$TMP/$3" && ! -L "$TMP/$3" ]] || {
   echo 'STOP: checked GitHub revision not available';exit 2;
 }
}
download "$TOOL_REV" safe_release_merge_audit.py audit.py
download "$BASE_REV" safe_release_rollout_v2.py baseline.py
download "$CAND_REV" safe_release_rollout_v2.py candidate.py
export PYTHONDONTWRITEBYTECODE=1
python3 - "$TMP" <<'PY_VERIFY'
import ast,pathlib,sys
root=pathlib.Path(sys.argv[1])
for name in ("audit.py","baseline.py","candidate.py"):
    ast.parse((root/name).read_bytes(),filename=name)
print("EPISCENE_READ_ONLY_COMPAT_AUDIT_READY")
PY_VERIFY
python3 "$TMP/audit.py" --baseline "$TMP/baseline.py" --candidate "$TMP/candidate.py"
echo 'FINISHED: No live files, services, sessions or markers changed'
