# EpiMediaHub Admin V2 — Kunden-Ablaufberichte (planned integration)

## User-approved design, 2026-10-20

### Monthly printable PDF
- Generate a report on the **last calendar day of each month** in **Europe/Berlin**, not only on the 31st. The target report is the **following calendar month**.
- One A4 landscape document, **one clearly separated section per playlist**; each playlist starts on a new page, continuing across as many pages as needed. Groups are ordered by playlist name, entries within each group by expiration date and then customer name.
- Columns: **Kundenname**, **Ablaufdatum**, **Kontaktiert** (empty checkbox), **Termin / Uhrzeit** (space for handwriting), and **Notizen / Ergebnis** (space for handwriting).
- Report headline displays period, playlist name, row count; every page has page number and private-administration footer.
- Duplicate customer names on different playlists are distinct entries. Do not mix a user's separate playlists; never collapse different expiration dates.
- Build one private PDF per period, using a deterministic period identifier, and make that **same artifact** available to authenticated authorized staff on desktop web and inside the native Android app.
- Print/download is intentionally optional on mobile. PDF has no IPTV URL, password, device ID, VPN secrets, access tokens or authentication cookies.

### Weekly reminders
- At the start of each calendar week (Monday, Europe/Berlin), prepare a concise view of customers expiring **Monday through Sunday inclusive**, grouped by playlist and sorted by day.
- Show weekly list natively in the Admin Android app and web Admin dashboard. No PDF is required for weekly view.
- Push text: **"EpiMediaHub: Die Wochenübersicht ist bereit."** The notification must not disclose customer names, playlists or expiration dates on lock screens.
- Monthly push: **"EpiMediaHub: Die Monatsübersicht ist zum Drucken bereit."**
- Notifications contain only authenticated navigation targets/report type. Dedupe per report period, retry safely, deliver only to registered admin FCM installations, support notification-off setting.

### Provider-supplied expiration confirmed by administrator

The administrator confirms that **the IPTV provider supplies expiry
automatically**, so no parallel manual expiration entry is required.

- The user reports that **most direct and reseller-owned customer accounts are Xtream**. Prioritize verified Xtream `user_info.exp_date` for the first provider adapter; do not exclude the minority of M3U accounts or synthesize dates for them.
- The administrator's aggregate view may include both direct and reseller-owned customer playlists. Any reseller-specific report must be filtered by `customers.reseller_id` bound to the authenticated server session; never permit the mobile client to request a different reseller's customer list. The read-only `expiry_report_rows.linked_expiries(..., reseller_id=...)` helper includes this filter with synthetic cross-reseller isolation tests.
- The server must refresh an authoritative expiration **for each individual
  customer-playlist provider account** and keep the verified timestamp and
  update time. Xtream account responses commonly expose `user_info.exp_date`
  as a Unix timestamp; `expiry_provider_adapter.py` validates this field
  strictly, converts its UTC instant to the Europe/Berlin calendar date, and
  treats `0`, missing or malformed fields as unknown (never "expires today").
- M3U does **not** have a universal expiry response format. Provider-specific
  authentication information must be checked independently before reporting
  M3U accounts. Don't claim their expiry can be inferred from their playlist URL.
- `expiry_report_rows.py` joins **fresh verified** per-playlist dates to the
  dashboard's customer and playlist names using the actual playlist primary key,
  without fetching config_json, credentials, token or stream URLs. A customer with
  4K and THE BEST on different dates appears in separate corresponding groups.
- Render monthly sheets with `expiry_report_pdf.py`, and weekly grouped
  dates via `expiry_report_calendar.py`. The source polling, isolated provider
  API network policy, persistent expiry snapshot cache and live schedule must
  be reviewed and installed before turning on automated web or mobile reports.
- Neither `annual_device_licenses.expires_at` nor `vpn_trials.expires_at`
  is an acceptable replacement for the IPTV provider's account expiration.

### Expiration source correctness / release gate
- The already received provisioning schema contains `customers.name` and `customer_playlists(customer_id,name,config_json)`, but **no verified customer-playlist `expires_at` column**.
- The verified `skip_analysis_playlists.expires_at` field refers to **analysis playlists**, not customer subscription expiry.
- The annual device license `annual_device_licenses.expires_at` and VPN authorization expiry must **not** be used as an IPTV customer-playlist expiry without an explicit verified mapping.
- Before enabling live reports, inspect how actual customer playlist expiration dates are populated (explicit admin field, verified provider response, or independently auditable subscription record). If unknown, omit from upcoming-expiry list and separately report "Ablaufdatum nicht erfasst" internally; NEVER invent an expiration date.
- Validate Europe/Berlin time boundaries, month ends in February and leap years, and stale updates. Do not silently duplicate or drop an entry due to a timezone conversion.
- Only authorized admins can fetch these privacy-sensitive report rows/files; HTTP headers must use private, no-store; private storage mode 0600/0700. Never send the full PDF as a push attachment or expose a public URL.
- Reports are snapshots: generation time and source revision/measurement timestamp must be recorded. Honor established data-retention controls and log administrative downloads without storing customer details in logs.

## Implemented development modules (NOT deployed)

- `expiry_provider_adapter.py` validates Xtream `user_info.exp_date` timestamps without storing or returning provider credentials.
- `expiry_cache.py` stores backend-verified per-playlist expiry dates and check timestamps in a private service-owned SQLite cache. There is NO public/mobile upload route.
- `expiry_report_rows.py` joins only fresh provider-verified playlist IDs to customer names and playlist names, with optional authenticated reseller scoping.
- `expiry_report_calendar.py` provides Berlin calendar windows; `expiry_report_pdf.py` renders multi-page A4 landscape contact/appointment worksheets.
- `mobile_flask.py` now provides admin-authenticated, no-store routes:
  - `GET /admin/mobile/reports/expiry` (desktop HTML, protected by dashboard login)
  - `GET /admin/mobile/reports/expiry/month?year=YYYY&month=M`
  - `GET /admin/mobile/reports/expiry/month.pdf?year=YYYY&month=M`
  - `GET /admin/mobile/reports/expiry/week?from=YYYY-MM-DD` (must be Monday)
- The Android Admin Compose app has a dedicated **Abläufe** area for weekly/monthly grouping and Android system printing via authenticated in-memory PDF bytes, not a WebView or public download URL.
- `expiry_report_publish.py` prepares one stable PDF on each last calendar day (for NEXT month) and weekly report-ready events on Monday after 07:00 Berlin. It stores no customer names in FCM events, deduplicates events using stable period IDs, and is **disabled unless** the deployment operator sets `EPIMEDIAHUB_EXPIRY_PROVIDER_COVERAGE_CERTIFIED=YES` after independent verification of comprehensive provider refresh.
- Both new notification categories are recognized by private Firebase send logic and open the native report screen. Sending needs a configured backend service account, registered Android Admin installations, and active monitor outbox cycles.
- `audit_xtream_expiry_source.py` is a **read-only redacted production discovery audit** needed to locate the actual provider refresh pipeline. It writes only aggregate account-type counts, whitelisted configuration key presence counts and safe source function names; never names/IDs, hosts, URLs, usernames or passwords.
- Isolated Python regression tests cover session authorization, PDF confidentiality, provider date conversions, multi-playlist grouping, reseller isolation, time windows, cache stale rejection, publication idempotency and generic push event content. Android CI builds the new native navigation.

**Release blocker:** the production API/worker path that actually obtains Xtream `user_info.exp_date` for EACH customer-playlist account has not been inspected or wired to `expiry_cache.save_verified`. The evidence of account coverage must be audited before enabling report publication or notifications. Installation of ReportLab in the service Python environment and real Android device tests remain necessary. No current customer expiry is inferred from an app license, VPN, EpiScene account, M3U URL, or stale response.

## Development status (do not mistake for deployment)

The pure renderer `expiry_report_pdf.py` builds the A4 worksheet from externally **verified** `Expiry(customer,playlist,day)` records, and is covered by tests. It is not yet connected to production data, scheduler, web route, authenticated download, native list viewer or FCM. Leave this feature disabled until verified expiration mapping and end-to-end privacy/permission testing. Do not promise a real monthly or weekly notification yet.
