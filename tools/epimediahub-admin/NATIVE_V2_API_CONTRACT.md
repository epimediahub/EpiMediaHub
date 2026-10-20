# EpiMediaHub Admin V2 — Native Android API contract (development)

**Status: design + Android read-only client implemented; production server adapter NOT implemented.**
Do not publish a V2 release or register these paths by guessing the production schema.

## Goal

Daily administration entirely in Android Jetpack Compose. No customer, reseller, license,
playlist or VPN management page embedded as HTML or WebView. The existing web dashboard
may continue as an independent operator tool. Authentication must become native as well;
the current login WebView on the development branch is temporary and must go before release.

## Existing authenticated read endpoints (production)

- GET /admin/mobile/bootstrap — administrator session / CSRF capability
- GET /admin/mobile/episcene/status — read-only lanes 8 and 10
- GET /admin/mobile/alerts.json — incident list
- POST /admin/mobile/alerts/ack — CSRF-protected alert acknowledgment
- GET /admin/mobile/update/status — signed private update metadata
- GET /admin/mobile/update/apk — protected update download

## New proposed endpoints — awaiting production schema audit

All requests must be HTTPS, admin-authenticated, authorized by server, no-store,
rate-limited and restricted to that caller's permitted entities. No plaintext customer
secrets or IPTV URLs should be included.

### Read-only overview

GET `/admin/mobile/management/overview`

```json
{"customers":12,"resellers":3,"active_licenses":11,"active_vpns":2}
```

Counts are *illustrative schema examples only*, not real production values.

GET `/admin/mobile/management/customers`:

```json
{"customers":[{"id":"opaque-customer-id","name":"Example (not real data)","subtitle":"2 Playlists","playlist_count":2,"expires_at_epoch":null}]}
```

GET `/admin/mobile/management/resellers`:

```json
{"resellers":[{"id":"opaque-reseller-id","name":"Example (not real data)","subtitle":"Reseller","playlist_count":null,"expires_at_epoch":null}]}
```

The Android client currently requests precisely these three GET endpoints and correctly
reports 401/403/404 without synthesizing counts or records. The server routes do not exist
in the deployed backend and need verified adapters.

### Native detail + write actions (not yet implemented)

- GET customer / reseller details with playlists, expiry and available actions.
- POST annual app-license grant and POST 7-day VPN trial **only through existing
  provisioning/business logic**, respecting stock, eligibility and device binding.
- Actions must be idempotent (replays cannot issue duplicate credits/trials).
- Admin CSRF, per-action authorization, reauthentication for sensitive actions,
  explicit confirmation with target, duration and cost, atomic transactions and audit
  records are mandatory.
- Unverified write routes must not be exposed as tappable controls. Never use legacy
  browser session cookies in URLs or log them.

### Native authentication (not yet implemented)

First inspect `dashboard_security.py` and the production login and MFA flow; then
create a narrow authenticated mobile session contract preserving MFA, CSRF,
revocation and rate limits. Do not put administrator passwords into persistent storage.
Biometrics unlock the device view, not the backend account/session.

## Next step (read-only, one time)

Run `audit_native_management_contract.py` on the provisioning/dashboard host.
It exports only table/column names and static route signatures to a 0600 JSON
file under /root — no customer rows, credential values, stream URLs or auth tokens.
Review this output before sharing. Use its route/schema map to implement actual
server adapters and end-to-end integration tests.

## Mandatory release gates

1. Confirm no HTML/WebView navigation for any admin operation, including login.
2. Verify real GET/detail/write flows against isolated test fixtures.
3. Verify authentication, MFA, CSRF, role restrictions and session expiry.
4. Verify double taps, retries, network loss and API timeout never duplicate licenses.
5. Verify normal and reseller identities never leak customer records.
6. Confirm updater version monotonicity and fixed release signing key; update through
   existing in-app updater only.
7. Run Android compilation/lint, backend regression suite and on-device acceptance.
8. Publish one integrated V2 APK and no intermediate customer/device installs.
