# EpiMediaHub Admin V2 — Native Android API contract (development)

**Status: native Android screens + Python read-only JSON server adapter implemented and unit-tested, NOT installed on production. Native login and write actions NOT implemented.**
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

## Implemented in development — production schema audit received 2026-10-20

All requests must be HTTPS, admin-authenticated, authorized by server, no-store,
rate-limited and restricted to that caller's permitted entities. No plaintext customer
secrets or IPTV URLs should be included.

### Read-only overview

GET `/admin/mobile/management/overview`

```json
{"customers":12,"resellers":3,"active_licenses":11,"active_vpns":2}
```

Counts are *illustrative schema examples only*, not real production values. The live adapter deliberately returns `null` for `active_licenses` and `active_vpns` until business semantics have been verified; it never guesses active entitlements.

GET `/admin/mobile/management/customers`:

```json
{"customers":[{"id":"opaque-customer-id","name":"Example (not real data)","subtitle":"2 Playlists","playlist_count":2,"expires_at_epoch":null}]}
```

GET `/admin/mobile/management/resellers`:

```json
{"resellers":[{"id":"opaque-reseller-id","name":"Example (not real data)","subtitle":"Reseller","playlist_count":null,"expires_at_epoch":null}]}
```

The Android client calls the three GET endpoints and their native detail variants,
including server-side bounded search `?q=...` with SQL wildcard escaping.
`GET /admin/mobile/management/customers/<int:id>` returns enabled state and
sanitized device and playlist names; `GET /admin/mobile/management/resellers/<int:id>`
returns a reseller and its customer list. Each list is bounded to 100 entries,
with `has_more` flags. No `config_json`, stream URL, device identifier,
WireGuard key or credential is returned. The new routes exist **only in this PR**, not
in the deployed backend. A guarded deployment and authenticated live smoke test
are required before any Android release.

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

The initial schema/route inventory was received and used to implement the JSON
read adapter. Run `audit_native_admin_actions.py` once on the dashboard host to
capture **only** existing authentication and grant-handler AST call names and
request key names, never function source or credentials. Review the resulting
JSON before sharing. This is needed to connect existing login and 1-year-app/
7-day-VPN business actions safely without guessing required security checks.

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
