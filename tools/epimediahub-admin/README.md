# EpiMediaHub Admin – server monitoring foundation

**Development-only GitHub code; not installed on Hetzner.** No Android APK or
live push service exists yet. This branch changes no production playlist,
customers, stored markers, analysis jobs or systemd services.

## Seven user-approved alert categories

1. EpiScene stalled with queued jobs and no progress for 15 minutes.
2. Analysis playlist expired or repeatedly rejected, plus optional expiry warning.
3. Worker version mismatch or repeated preflight failure.
4. Server/API unavailability after repeated unsuccessful health checks.
5. Android build or release-sync failure.
6. Abnormal aggregated customer playback failures.
7. Daily EpiScene report ready for the Berlin local calendar date.

`monitor_rules.evaluate(snapshot, now_epoch)` is a pure rules function.
`incident_store.IncidentStore(path)` uses a private (0600) SQLite file,
deduplicates by stable alert key, allows acknowledgement and explicit resolution,
and emits a new-notification key only when a problem first appears or recurs.
**Do not** automatically resolve merely because a signal is missing.

## Investigation: renewed playlist credentials

`audit_playlist_paths.py` is a **read-only diagnostic**, not a repair script.
It inspects table structures/row counts for internal analysis playlist IDs 8
and 10 and source code keyword *line numbers*. It never retrieves or prints
actual playlist usernames, passwords or URL values. Missing columns, unavailable
databases or unfamiliar schema are reported without a destructive fallback.

On the analysis server, once the script has been reviewed and transferred:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 audit_playlist_paths.py
```

The output identifies candidate places to review. It is not proof that URL
values are stale and does not modify any saved stream, job or marker. Do not
copy a new account's credentials across records or erase the catalog without
first verifying the live source resolver and taking a backup.

## Integration and privacy safeguards

- Feed **sanitized** numeric/service metrics into the rules only.
- Never pass passwords, bearer tokens, full stream URLs, device IDs or customer
  names into incidents, logs or FCM notifications.
- Store the incidents DB in a root-owned 0700 directory; the code protects the
  DB file itself with 0600 permissions and refuses insecure existing files.
- Persist acknowledgements, successful recovery evidence and dedup state.
- Use a truly **independent external probe** to detect total server outages.
- Any corrective restart must follow the existing EpiScene idle/drain guards.
- Playlist IDs, approvals and marker history must survive credential rotation.
- Only a backend service can deliver FCM; keys never belong in the Android app.
- Customer playback telemetry must be aggregated and privacy-reviewed.

Still to implement: real production metrics adapters, worker version/safe
reload integration, authenticated API, push transport, mobile dashboard,
separately signed private Android APK and end-to-end on-device tests.

## Tests

```bash
cd tools/epimediahub-admin
python3 -m unittest discover -v -p 'test_*.py'
```
