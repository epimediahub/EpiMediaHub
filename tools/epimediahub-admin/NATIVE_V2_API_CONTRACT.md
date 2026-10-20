# EpiMediaHub Admin V2 — Native Android API contract (development)

**Status: native Jetpack Compose management, login and explicit admin app-year / VPN-trial grants implemented in development and checked with isolated backend QA. NOT deployed or acceptance-tested on production or device.**
Do not publish a V2 release or register these paths by guessing the production schema.

## Goal

Daily administration entirely in Android Jetpack Compose. No customer, reseller, license,
playlist or VPN management page embedded as HTML or WebView. The existing web dashboard may continue independently. Android uses its own native
login UI, which posts to the existing Flask administrator login and validates the
resulting secure session via `/admin/mobile/bootstrap`. No WebView is included.

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

### Native detail + privileged write actions (development)

The following read endpoints return bounded, private entity summaries:
- GET `/admin/mobile/management/customers/<int:customer_id>`
- GET `/admin/mobile/management/resellers/<int:reseller_id>`

The following actions now have server-side wrappers in `native_management_actions.py`:
- POST `/admin/mobile/management/devices/<int:id>/grant-year`
- POST `/admin/mobile/management/devices/<int:id>/vpn-trial7`

Every write requires the existing admin session, a fresh `X-Dashboard-CSRF`
header, explicit `{"confirm":true,"request_id":"<canonical UUID>"}`, and a
positive device eligibility check. The wrapper delegates execution to the
*actual existing* Flask handler registered as `admin_grant_year` or
`grant_trial_auto`; it does not duplicate the original business SQL or
override the provider requirements. The final JSON result is `applied:true`
only if a new active entitlement is verified in SQLite. Existing active
entitlements respond 409. Invalid/adminless requests fail closed. A client
timeout is reported as *unconfirmed*, never as guaranteed failure.

Additional release gates:
- Verify production view-function names, database key mappings, 365-day and
  7-day semantics against isolated production-shaped fixtures; do not infer
  success from legacy redirects or flash messages.
- Ensure each business handler serializes concurrent grants and strictly
  enforces one trial/one active annual entitlement as intended.
- Validate session/CSRF cookies with the production reverse proxy; test native
  login failure, successful login, logout and biometric reentry on a device.
- Introduce a durable replay journal before activating high-impact native
  credits/payment flows, and verify legacy direct action routes are protected
  against CSRF.
- Do not expose IPTV config JSON, streaming URLs, VPN private keys or tokens.
- Customer/reseller modification, device assignment and playlist CRUD still
  need their native business adapters before complete V2 release.

### Native authentication (development)

`NativeAdminAuth.kt` uses a native password input with no persistent
password storage. It POSTs form data over HTTPS directly to the existing
administrator login endpoint and never renders the HTML response. It accepts
the first-party session cookie only after authenticated
`GET /admin/mobile/bootstrap`, checks on each biometric unlock, and can
log out. No additional password database is introduced. This needs an
on-device live acceptance test and review of brute-force protections.

## Next step (read-only, one time)

The initial schema/route inventory was received and used to implement the JSON
read adapter. Run `audit_native_admin_actions.py` once on the dashboard host to
capture **only** existing authentication and grant-handler AST call names and
request key names, never function source or credentials. Review the resulting
JSON before sharing. This is needed to connect existing login and 1-year-app/
7-day-VPN business actions safely without guessing required security checks.

## Mandatory release gates

1. Confirm no HTML/WebView navigation for any admin operation, including login (CI guard now present).
2. Verify real GET/detail/write flows against isolated test fixtures.
3. Verify authentication, MFA, CSRF, role restrictions and session expiry.
4. Verify double taps, retries, network loss and API timeout never duplicate licenses.
5. Verify normal and reseller identities never leak customer records.
6. Confirm updater version monotonicity and fixed release signing key; update through
   existing in-app updater only.
7. Run Android compilation/lint, backend regression suite and on-device acceptance.
8. Publish one integrated V2 APK and no intermediate customer/device installs.
