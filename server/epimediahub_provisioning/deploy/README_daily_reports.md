# EpiScene daily reports

The report covers the previous 07:00–07:00 period in `Europe/Berlin`. DST days
have 23 or 25 hours. The timer runs at 07:00, on boot and every 15 minutes for
idempotent catch-up. Historical reports are immutable and missing days are
generated after downtime. No ChatGPT reminder is required.

The first dashboard opening for a new report displays it automatically. Closing
it records that day in browser-local storage. The archive remains accessible
from the dashboard, and an open dashboard checks once per minute. Separate
browsers each have their own read status. Blocked browser storage does not block
access. All report routes use the existing administrator login.

## What is measured

- Individual job transitions and attempts, with actual start/end wall time.
- Unique episode files versus repeated attempts, grouped by playlist/series/season.
- Outcome and technical failure reason, interruptions and missing comparisons.
- Intro, recap and outro marker creation/changes, old/new boundaries, confidence,
  approval state, explicit human review and auto-approval evidence.
- Audio/visual detector evidence, consensus decisions and disagreement flags.
- Existing phase timers, controller CPU time and process peak RSS, plus cache
  lookup hits/misses. Visual cache lookups include internal post-write reads;
  they are not a measured percentage of saved compute/network traffic.
- SHA-256 source version identifiers and complete sanitized JSON event export.

Phase times can overlap. Controller CPU/RAM excludes the separate remote compute
process. Confidence is not a measured accuracy percentage; corrections are not a
representative ground-truth sample. Historical queue size, total remaining time,
network byte counts and remote CPU/RAM are not invented.

Collection begins at installation; no earlier attempt history is reconstructed.
Start reports and any partial first period are clearly labeled. Reports count
finished attempts, not currently running jobs. Archived logs remain in the
existing database and should be included in its normal backups. This version
does not automatically delete audit history.

## Install on the current Hetzner dashboard host

Run `sudo bash install_skip_daily_reports.sh`. It is self-contained and does not
download source or dependencies. It requires the existing deployment with
independent analysis playlists and `epimediahub-provisioning.service` using
`wsgi:app`. Existing application paths/user/group/data directory are respected.

The installer validates hashes and syntax, saves changed files, adds the WSGI
hook and template include to the actual live files, creates additive report
tables/triggers, restarts the web service, checks authenticated/anonymous views,
enables the Berlin timer and verifies the first report. The analysis engine and
its remote protocol component hashes remain unchanged. Analysis continues.
On a failed check the original files and timer state are restored. Customer and
analysis databases are never rolled back over newer live writes; additive audit
tables and any collected events remain intact.

Optional established paths can be supplied with `EPIMEDIAHUB_APP_DIR` and
`EPIMEDIAHUB_ENV_FILE`. Unexpected WSGI/template layouts or report unit drop-ins
are rejected before changing files.

## Verify on the server

```bash
systemctl status epimediahub-episcene-report.timer --no-pager
systemctl status epimediahub-episcene-report.service --no-pager
journalctl -u epimediahub-episcene-report.service -n 30 --no-pager
```

The oneshot service may show `inactive (dead)` after success; its exit status and
the active timer matter. Report links: `/admin/skip/reports` and
`/admin/skip/reports/YYYY-MM-DD.json`.

## Build and test

```bash
python3 deploy/build_skip_daily_report_installer.py deploy/install_skip_daily_reports.sh
python3 -m pytest -q tests/test_skip_daily_reports.py tests/test_skip_daily_report_installer.py
```

Test coverage includes retry deduplication, UTC/Berlin boundaries and DST,
missed-day catch-up, concurrent generators, immutable history, unknown runtime,
manual/automatic evidence, credential redaction, administrator access, escaped
HTML, preserved local modifications, corrupt bundle rejection and repeat installs.

Implementation checked against both the repository baseline and the recovered,
checksum-verified independent-analysis update used on the deployed system.
Deployment itself still requires running the installer on the server.
