# EpiMediaHub self-hosted Speedtest

Dedicated bounded HTTP backend for EpiMediaHub Android on the Hetzner Analysis
server (public IP 2.31.6.81). The existing EpiScene, WireGuard and Cloudflare
Tunnel are not modified.

## Stage 1: loopback install

On the Analysis server only, download and run the pinned installation script.
It installs ONLY epimediahub-speedtest.service on 127.0.0.1:8792; no public
ports, firewall, DNS, or existing services are changed.

Service status: systemctl status epimediahub-speedtest --no-pager
Health: curl -fsS http://127.0.0.1:8792/v1/health
Logs: journalctl -u epimediahub-speedtest -n 30 --no-pager
Stop: systemctl stop epimediahub-speedtest

Python stdlib only, systemd DynamicUser=yes, MemoryMax=256M, CPUQuota=150%,
ProtectSystem=strict. A sparse 128 MiB local payload is created.

## Stage 2: public HTTPS (only after stage 1 passes)

1. Create Cloudflare DNS A record speedtest.epimediahub.com -> 2.31.6.81.
   Set it to DNS ONLY (grey cloud), not Cloudflare proxy or Tunnel.
2. Verify public TCP 80/443 are free and no unrelated Caddy site would be changed.
3. Enable dedicated Caddy TLS site from Caddyfile.speedtest.example.
   Allow inbound TCP 80 and 443 in UFW and any Hetzner Cloud Firewall.
   Do NOT allow inbound 8792.
4. Test externally: curl -fsS https://speedtest.epimediahub.com/v1/health
5. Only after live HTTPS passes, integrate new origin in official Android updater.

## HTTP interface

POST /v1/session (empty body) -> {"session":"...", "ttlSeconds":300,...}
GET /v1/down?bytes=8388608&stream=0   (Authorization: Bearer <session>)
POST /v1/up                        (Authorization: Bearer <session>)
GET /v1/health                     (public diagnostic)

Session tokens expire in 300s and are bound to connecting public IP. The
test endpoint is not publicly reachable until Caddy is deliberately activated.
At most six new sessions per minute and 12 concurrent transfers globally.
Downloads max 32 MiB per request and 176 MiB per session; uploads max 16 MiB
per request and 64 MiB per session. Upload payloads are discarded, not stored.
Access logs never contain Authorization headers or tokens. All traffic goes
through HTTPS after Stage 2; no secrets embedded in Android app.

## Performance notes

The earlier iperf3 test between Analysis and Finland proved roughly 1 Gbit/s
in each direction with TCP over 8 seconds, not 1 Gbit/s HTTPS from Fire TV.
TLS, Android and transit performance still require an independent live test.
The backend's source is server.py; local QA is test_server.py. The isolated
service must not replace or alter any existing EpiScene services.
