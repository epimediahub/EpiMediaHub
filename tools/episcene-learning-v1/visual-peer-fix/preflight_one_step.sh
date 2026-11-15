#!/usr/bin/env bash
# One read-only snapshot for EpiScene release blockers AND worker versions.
# Run from this reviewed GitHub checkout ON the actual analysis host.
# Usage: bash preflight_one_step.sh [approved-private-worker-manifest.json]
# Never installs, repairs, restarts or downloads anything.
set -Eeuo pipefail
umask 077
HERE="$(CDPATH='' cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
GATE="$HERE/../compute-lanes/worker_version_gate.py"
FUNNEL="$HERE/auto_release_funnel_readonly.py"
[[ $# -le 1 ]] || { echo 'STOP: expected at most one approved manifest path' >&2; exit 2; }
[[ -f "$GATE" && ! -L "$GATE" && -f "$FUNNEL" && ! -L "$FUNNEL" ]] || {
  echo 'STOP: incomplete or unexpected preflight package' >&2; exit 2;
}
command -v python3 >/dev/null || { echo 'STOP: Python3 missing' >&2; exit 2; }
echo '=== Unique pending auto-release markers, by analysis playlist (read-only) ==='
python3 "$FUNNEL"
echo '=== All known worker components (read-only) ==='
if [[ $# -eq 1 ]]; then
  [[ -f "$1" && ! -L "$1" ]] || { echo 'STOP: approved manifest unavailable' >&2; exit 2; }
  python3 "$GATE" --manifest "$1"
  echo 'VERSION_GATE_MATCHES_APPROVED_MANIFEST: structural gate passed; run actual integration health checks before rollout'
else
  python3 "$GATE"
  echo 'STOP: no operator-reviewed SHA-256 manifest supplied; deployment NOT permitted'
  exit 2
fi
echo 'READ_ONLY_PREFLIGHT_FINISHED: no database writes, approvals or restarts'
