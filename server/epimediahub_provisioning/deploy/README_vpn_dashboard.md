# EpiMediaHub VPN Finnland – Dashboard

Adds `/admin/vpn` and `/reseller/vpn` to the existing dashboard. Install on the
dashboard host first, then install the agent on the Finland WireGuard server.
The existing backend, analysis jobs and Lifetime-credit ledger are preserved.

## Install

Run `install_vpn_dashboard.sh` as root on the host containing
`/opt/epimediahub/provisioning` and the current customer database. The installer
tests a staged copy with a database backup before replacing any installed files.
It adds only the VPN module, assets, navigation links and a WSGI import. It backs
up changed code and SQLite, restarts the web service and rolls back code if the
health check fails. It never rolls back customer or analysis data.

On the Finland server run `install_vpn_finland_agent.sh`. Use the same dashboard
origin as the API, normally `https://api.epimediahub.com`. Enter the private
token from the dashboard host's `/var/lib/epimediahub/vpn-agent.token` at the
hidden prompt. If EPIMEDIAHUB_DATA_DIR differs, use the path printed by the
dashboard installer. Never paste the token or private WireGuard keys into chat.

The agent needs existing `wg0`, WireGuard tools and Python 3.9+. It keeps its
configuration root-only at `/etc/epimediahub-vpn-agent.json` and runs as
`epimediahub-vpn-agent.service`. No automatic SSH access is established.

## First use

1. Open **VPN Finnland** in the Admin dashboard.
2. Assign the public client key and its existing VPN address to the correct
   registered Android/Fire-TV device. The beta profile is still imported on the
   device. Do not enter the server key or a private key. A new assignment starts
   suspended, so grant its test period before expecting traffic.
3. Grant an admin test period, or define VPN tariffs and reseller VPN-credit
   prices. No price or duration is assumed. Credit orders require a configured
   price; payment approval and activation are transactional and idempotent.
4. Wait for **Freigegeben**. **Bestätigung offen** is not a successful
   activation. Reseller-paid activations are blocked while the agent is offline.
5. Validate playback, expiry, revoke/resume and an explicit direct fallback on
   the Fire TV before making the VPN available to customers.

## Scope and integrity

- One public key and one live VPN address per registered device. Device changes
  are admin-only, preserve the remaining term and charge no credits. Revocations
  are applied before replacement grants. Deleted devices retain a revocation
  tombstone until the agent clears their rules.
- Only dashboard-assigned peers are managed. Unassigned WireGuard peers remain
  untouched. IP collisions with unmanaged peers stop the reconciliation.
- The agent clears AllowedIPs to block managed peer traffic, preserving PSKs.
  Managed peer blocks in `wg0.conf` have no AllowedIPs on disk; `SaveConfig` is
  disabled so a reboot cannot restore an expired runtime grant. The original
  config is backed up root-only as `wg0.conf.before-epimediahub-vpn`.
- Runtime grants expire after at most a 60-second lease and at their licence
  deadline. The agent checks deadlines independently of HTTP requests. On
  dashboard failure, restart or service stop, owned peers are blocked. Restoring
  an old WireGuard config manually would bypass that policy.
- `/v1/vpn-agent/desired` and `/applied` require a private bearer token over HTTPS.
  A stale, partial or mismatched acknowledgement cannot mark rules as applied.
  The agent does not receive customer names, device sessions or client secrets.
- Reseller ownership is checked in every write, independently of the displayed
  controls. All VPN browser writes require a session CSRF token. Billing uses
  a separate append-only VPN ledger, and existing App/Lifetime credits are not
  consumed. This does not contact a payment provider or charge a bank account.
- Beta **1.0.40** does not consume server-provided VPN settings and does not
  upload speedtest results. Playlist VPN/Direct selection and speedtests remain
  in the app. The dashboard explicitly says this; it does not invent live data.
- A WireGuard public key can be copied to another device along with its private
  key. This addon enforces provisioning/licence ownership, not hardware
  attestation. Commercial app-side automatic profile provisioning is a separate
  integration. System-wide leak freedom is not claimed.

## Development checks

`python -m unittest discover -s server/epimediahub_provisioning/tests -p 'test_vpn_*.py' -v`

`python server/epimediahub_provisioning/deploy/build_vpn_installers.py`

Tests cover real Flask/SQLite routes, tenant isolation, CSRF, duplicate charging,
immutable order prices, expiry, deleted devices, stale acknowledgements and the
agent using a simulated WireGuard process. Hardware acceptance on Finland/Fire
TV remains required; these tests are not a live VPN benchmark.
