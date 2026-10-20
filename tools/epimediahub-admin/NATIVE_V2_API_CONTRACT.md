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

Additional audited native operations in development:

- POST `/admin/mobile/management/customers/<int:id>/rename`
- POST `/admin/mobile/management/resellers/<int:id>/rename`
  with `expected_name`, `name`, and a canonical UUID request ID. The
  `native_management_edits.py` helper performs metadata-only names updates
  with optimistic concurrency, journaled replay detection and rollback.
  It does not touch device assignments, IPTV config JSON, credits, licenses
  or VPN subscriptions. Editing customer/reseller provisioning fields
  still requires the original business logic.
- GET `/admin/mobile/management/devices/<int:id>/diagnostics`
  returns sanitized platform, recent synchronization status and error-code
  metadata. It never returns device hardware identifiers, playlist
  credentials, provider URLs, sync error text or raw report payloads.

The native EpiScene endpoint now includes results broken into
`done`, `review`, `partial`, `no_match` and `no_reference`,
plus a warning when a queue remains and there has been no confirmed
completion for at least 15 minutes. These remain read-only and scoped
to independent analysis lanes 8 and 10.

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

## Additional audited native actions — 2026-10-20 CRUD-flow JSON

The one-time production source-flow audit identified 26 handler functions.
Its literals/SQL were redacted and it was **not** permission to invent missing
playlist form fields, deletion confirmation constants, or EpiScene decisions.

The development branch now has a narrow form-data bridge:
`POST /admin/mobile/management/actions/<action>/<int:entity_id>`

Only these form actions are supported; `entity_id=0` is used only for creation.

| Action | Original production handler |
| --- | --- |
| `create-customer` | `v070_create_customer` |
| `create-reseller` | `v080_create_reseller` |
| `rename-device` | `v074_rename_device` |
| `sync-device` | `v070_sync_device` |
| `move-device` | `v070_move_device` |
| `assign-reseller` | `v080_assign_customer_reseller` |
| `delete-playlist` | `v076_delete_customer_playlist` |

Input is bounded `application/x-www-form-urlencoded` with only audited
field names plus `confirm=true` and canonical `request_id` UUID. A valid
administrator session and `X-Dashboard-CSRF` are mandatory. The existing
registered Flask business function receives the form and remains responsible
for quotas, validation, migrations, history, and config bumping; its redirect
is never interpreted as proof of success. Native responses are JSON only and
verified through a read-only postcondition. No credentials are echoed.

A private local SQLite replay journal reserves each request UUID *before*
invoking the existing business handler. A crash leaves it pending and a repeated
request is denied rather than potentially duplicating a creation. A per-action
OS lock serializes concurrent requests across worker processes. We do **not**
claim cross-channel exactly-once behavior with legacy browser form submissions.
No native delete is dispatched without an explicit confirmation dialog.

The Kotlin client uses native Compose dialogs for customer/reseller creation,
device rename/sync/move, customer-to-reseller assignment, and guarded playlist
removal, never embedding a browser. It does not automatically retry a write.

**Still blocked for a full V2 acceptance**: playlist create/edit cannot be
implemented safely from this redacted extract because the form contract is
hidden inside `_playlist_config()`. Customer/reseller/device deletion needs the
exact confirmation semantics and side-effect fixture verification. EpiScene
manual review needs the validated decision values and legacy CSRF form
requirements. Neither these tasks nor full real-device onboarding and
authenticated production integration have been tested. No V2 release/merge.

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
