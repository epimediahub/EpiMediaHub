#!/usr/bin/env bash
# One-paste READ-ONLY diagnostic for EpiScene. NO deployments, updates or restarts.
# All downloaded Python sources are pinned to an exact, already-reviewed
# Git commit; this script never fetches from a moving branch.
set -Eeuo pipefail
umask 077
[[ "$EUID" -eq 0 ]] || { echo "STOP: root rights required to read server diagnostics"; exit 2; }
for bin in curl python3 mktemp; do
  command -v "$bin" >/dev/null || { echo "STOP: missing $bin"; exit 2; }
done
PIN="e22ebf256cd6fdc34423ef366858da8c15c1ccc2"
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/$PIN/tools/episcene-learning-v1"
TMP="$(mktemp -d -t episcene-readonly-XXXXXXXX)"
trap 'rm -rf -- "$TMP"' EXIT
get() {
  curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
    --retry 2 --connect-timeout 10 --max-time 50 \
    "$BASE/$1" --output "$TMP/$2"
  [[ -s "$TMP/$2" && ! -L "$TMP/$2" ]] || { echo "STOP: expected source missing";exit 2; }
}
get "visual-peer-fix/auto_release_funnel_readonly.py" "release_funnel.py"
get "compute-lanes/worker_version_gate.py" "version_gate.py"
# Parse both pinned sources without importing production modules.
python3 - "$TMP/release_funnel.py" "$TMP/version_gate.py" <<'PY_CHECK'
import ast,sys
for name in sys.argv[1:]:
    with open(name,"rb") as f:
        ast.parse(f.read(),filename=name)
print("READ_ONLY_SOURCE_SYNTAX_OK",flush=True)
PY_CHECK
export PYTHONDONTWRITEBYTECODE=1
echo "=== EpiScene: unique pending automatic markers and actual evidence bottlenecks ==="
python3 "$TMP/release_funnel.py"
echo "=== EpiScene: installed worker component version inventory ==="
python3 "$TMP/version_gate.py"
echo "READ_ONLY_AUDIT_COMPLETE: nothing installed/restarted/approved."
echo "DEPLOY_BLOCKED: reviewed release manifest and actual server integration checks required."
