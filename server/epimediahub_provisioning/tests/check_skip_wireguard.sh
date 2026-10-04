#!/usr/bin/env bash
# Actual encrypted peer-to-peer RPC in isolated Linux network namespaces (CI).
set -Eeuo pipefail
umask 0077
PY="${1:-python3}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK="$(mktemp -d)"
SERVER="epi-analysis-server-$$"
CLIENT="epi-analysis-client-$$"
PID=""
cleanup() {
  if [ -n "$PID" ]; then kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; fi
  ip netns delete "$CLIENT" 2>/dev/null || true
  ip netns delete "$SERVER" 2>/dev/null || true
  rm -rf "$TASK"
}
trap cleanup EXIT
test "$(id -u)" = 0
ip netns add "$SERVER"
ip netns add "$CLIENT"
ip link add epi-wg-sr type veth peer name epi-wg-cl
ip link set epi-wg-sr netns "$SERVER"
ip link set epi-wg-cl netns "$CLIENT"
ip -n "$SERVER" addr add 192.0.2.1/24 dev epi-wg-sr
ip -n "$CLIENT" addr add 192.0.2.2/24 dev epi-wg-cl
ip -n "$SERVER" link set epi-wg-sr up
ip -n "$CLIENT" link set epi-wg-cl up
ip -n "$SERVER" link set lo up
ip -n "$CLIENT" link set lo up
wg genkey > "$TASK/server.key"
wg genkey > "$TASK/client.key"
SERVER_KEY="$(wg pubkey < "$TASK/server.key")"
CLIENT_KEY="$(wg pubkey < "$TASK/client.key")"
for node in "$SERVER" "$CLIENT"; do ip -n "$node" link add wg-epi-analysis type wireguard; done
ip netns exec "$SERVER" wg set wg-epi-analysis private-key "$TASK/server.key" listen-port 51820 peer "$CLIENT_KEY" allowed-ips 10.87.26.2/32
ip netns exec "$CLIENT" wg set wg-epi-analysis private-key "$TASK/client.key" peer "$SERVER_KEY" endpoint 192.0.2.1:51820 allowed-ips 10.87.26.1/32 persistent-keepalive 1
ip -n "$SERVER" addr add 10.87.26.1/32 dev wg-epi-analysis
ip -n "$CLIENT" addr add 10.87.26.2/32 dev wg-epi-analysis
ip -n "$SERVER" link set wg-epi-analysis up
ip -n "$CLIENT" link set wg-epi-analysis up
ip -n "$SERVER" route add 10.87.26.2/32 dev wg-epi-analysis
ip -n "$CLIENT" route add 10.87.26.1/32 dev wg-epi-analysis
ip netns exec "$SERVER" "$PY" "$ROOT/skip_remote_worker.py" > "$TASK/worker.log" 2>&1 &
PID=$!
ip netns exec "$CLIENT" env PYTHONPATH="$ROOT" SKIP_ANALYSIS_REMOTE_URL=http://10.87.26.1:8790 "$PY" - <<'PY'
import random,time
from skip_remote_client import RemoteDeferred,health,match
for attempt in range(10):
    try:
        health(); break
    except RemoteDeferred:
        if attempt==9: raise
        time.sleep(.2)
rng=random.Random(49)
fp=[rng.getrandbits(32) for _ in range(100)]
target=[rng.getrandbits(32) for _ in range(11)]+fp
assert match(fp,target,125)==(1375,1.0)
print('Encrypted WireGuard RPC and exact-version matching OK')
PY
