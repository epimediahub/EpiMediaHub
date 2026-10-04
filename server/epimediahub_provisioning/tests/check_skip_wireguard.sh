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
import io,random,re,threading,time,urllib.parse,wave
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
import numpy as np
import skip_analysis as audio
from skip_remote_client import RemoteDeferred,health,local_execution,match
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

# The fixture exists only on the Pi namespace's loopback; the compute namespace
# cannot reach it. The decoder must read the fixed private relay through WireGuard.
rate=11025
t=np.arange(rate*42)/rate
pcm=(11000*np.sin(2*np.pi*(190+30*(np.floor(t/3)%7))*t)).astype('<i2')
stream=io.BytesIO()
with wave.open(stream,'wb') as writer:
    writer.setparams((1,2,rate,0,'NONE','not compressed'))
    writer.writeframes(pcm.tobytes())
data=stream.getvalue()
with TemporaryDirectory() as directory:
    file=Path(directory)/'episode.wav';file.write_bytes(data)
    with local_execution():
        expected=audio.fingerprint(str(file),15000,20000,with_coverage=True,require_complete=True)
ranges=[]
class Provider(BaseHTTPRequestHandler):
    def log_message(self,*_): pass
    def do_HEAD(self): self.relay(False)
    def do_GET(self): self.relay(True)
    def relay(self,body):
        header=self.headers.get('Range');ranges.append(header)
        start,end=0,len(data)-1
        if header:
            match=re.fullmatch(r'bytes=(\d+)-(\d*)',header)
            assert match
            start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
        self.send_response(206 if header else 200)
        self.send_header('Content-Type','audio/wav')
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(end-start+1))
        if header: self.send_header('Content-Range',f'bytes {start}-{end}/{len(data)}')
        self.end_headers()
        if body:
            try: self.wfile.write(data[start:end+1])
            except (BrokenPipeError,ConnectionResetError): pass
provider=ThreadingHTTPServer(('127.0.0.1',0),Provider)
provider.daemon_threads=True
thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
upstream=f'http://media.fixture:{provider.server_port}/series/private-user/private-password/42.wav'
try:
    with mock.patch.dict('os.environ',SKIP_ANALYSIS_PROVIDER_PATH='raspberry'), \
         mock.patch.object(audio,'public_address',return_value=(urllib.parse.urlsplit(upstream),('127.0.0.1',))), \
         mock.patch.object(audio,'run',side_effect=AssertionError('Pi decoder is forbidden')):
        with audio.provider_proxy(upstream) as source:
            assert source.via_pi and source.url.startswith('http://10.87.26.2:8791/')
            assert 'private-password' not in source.url
            assert audio.probe(source)==(42000,[])
            actual=audio.fingerprint(source,15000,20000,with_coverage=True,require_complete=True)
            assert actual==expected
    assert any(value and not value.startswith('bytes=0-') for value in ranges),ranges
    print('Encrypted private media relay, range seek and remote Chromaprint OK')
finally:
    provider.shutdown();provider.server_close();thread.join(timeout=2)
PY
