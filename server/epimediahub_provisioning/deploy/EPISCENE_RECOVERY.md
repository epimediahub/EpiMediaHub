# EpiScene: Raspberry ↔ Hetzner recovery (2026-10-10)

## Observed failure
The daily EpiScene report for 2026-10-09 07:00 to 2026-10-10 07:00
records 137 completed attempts and 2,976 interruptions. The
last completed episode ended around 17:33 on October 9. Version-mismatch
errors then prevented progress, particularly on two repeatedly deferred jobs.
This historical report is **not** proof of the live node states.

## Read-only preflight (run on BOTH nodes; no service/database changes)
```bash
curl -fsSL https://raw.githubusercontent.com/epimediahub/EpiMediaHub/f1570edc74917ecd24f8e1c659d3ec2976e52266/server/epimediahub_provisioning/deploy/episcene_recovery_diagnose.py -o /tmp/episcene-recovery-diagnose.py && sudo python3 /tmp/episcene-recovery-diagnose.py
```
Compare the two sets of controller/worker hashes. The Raspberry's
`mismatching_modules` list is especially important. Examine worker and
analysis timers and queued/running job totals. A health endpoint returning
HTTP 200 is NOT enough: every entry in the version hash map must match.

## Recovery sequence — *after* comparing actual installed versions
1. Preserve the live SQLite database using the SQLite backup API,
   separately from program files. Preserve existing analysis passwords,
   access credentials, markers, schedules, progress, cache and daily reports.
2. Determine which installed source was modified on 2026-10-09.
   Do not blindly install an older GitHub branch or revert current reports.
3. Stage an identical tested analyzer bundle on Pi and Hetzner with
   atomic deployment/rollback. Use existing `install_skip_scene.sh`
   prepare/compute/control only if the exact content is compatible with
   independently configured analysis playlists and the daily reports.
4. Verify that `skip_remote_client.health()` returns matching component
   hashes and `episcene.policy`, then run a single bounded analysis attempt.
5. Restore the original analysis timer state only after the test passes.
   Verify successful episode progress rather than thousands of requeues.
6. Add a remote health preflight and backoff so the same broken job
   cannot be immediately requeued without useful work.

## Dashboard: analysis line expiration prediction
**User requirement:** Analysis lines are renewed/replaced manually by the
owner. Remove automatically forecast/predicted expiration dates and their
automatic expiration rules from **analysis-only playlists**. Do not auto-disable
or auto-replace an analysis playlist based on a guessed expiry. Actual
provider HTTP errors or failed authentication can be displayed as live
connection failures (not as expiration predictions), and the user must retain
the ability to edit or replace the credentials manually. Preserve all
existing customer playlist expiration, license and reseller settings.

The current production dashboard code is not fully represented by the
public source snapshot; inspect the actual installed template/API identified
by the preflight before changing this behavior. Do not touch
`skip_schedule_requests.expires_at`: it is an internal 7-day work-priority
timeout and has no relationship to paid analysis-line expiration.
