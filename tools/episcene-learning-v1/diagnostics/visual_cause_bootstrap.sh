#!/usr/bin/env bash
# One-paste read-only root-cause analysis of EpiScene visual evidence gaps.
# All 3 Python diagnostic files are fetched from one immutable Git commit.
# No install, service restart, job enqueue, media stream or database mutation.
set -Eeuo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo 'STOP: root required to read protected diagnostics'; exit 2; }
for cmd in curl python3 mktemp; do
  command -v "$cmd" >/dev/null || { echo "STOP: missing $cmd"; exit 2; }
done
PIN="b8cdb17817712f08ad0ade6d83ed1b6cf2054cde"
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$PIN/tools/episcene-learning-v1/diagnostics"
TMP="$(mktemp -d -t episcene-visual-readonly-XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
for name in visual_cause_summary.py release_gap_readonly.py runtime_deadlines.py; do
  curl --proto '=https' --tlsv1.2 -fsSL --retry 2 --connect-timeout 10 --max-time 60 \
    "$BASE/$name" -o "$TMP/$name"
  test -s "$TMP/$name" && test ! -L "$TMP/$name" || {
    echo 'STOP: read-only diagnostics package missing'; exit 2;
  }
done
python3 - "$TMP" <<'PY_PARSE'
import ast,pathlib,sys
folder=pathlib.Path(sys.argv[1])
for name in ("visual_cause_summary.py","release_gap_readonly.py","runtime_deadlines.py"):
    with (folder/name).open("rb") as source:
        ast.parse(source.read(),filename=name)
print("VERIFIED_READ_ONLY_DIAGNOSTICS_SYNTAX")
PY_PARSE
export PYTHONDONTWRITEBYTECODE=1
echo '=== EpiScene visual root-cause summary: analysis lanes 8/10 ==='
python3 "$TMP/visual_cause_summary.py"
echo 'END: No production code, workers or customer playlists changed'
