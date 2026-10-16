# EpiMediaHub Admin – monitoring rules (initial foundation)

This is **only a testable, side-effect-free rule engine**. It does not deploy a
server process, modify IPTV playlists, start analysis jobs, send push messages,
or provide an Android APK.

The seven user-approved categories are:
1. EpiScene stalled while jobs are queued (900 seconds);
2. analysis playlist expired/invalid, with optional 72-hour expiry warning;
3. worker checksum mismatch or repeated failed preflight;
4. server/API unreachable after three consecutive checks;
5. Android app build/release-sync failure;
6. clustered customer playback errors (at least 10 errors, 20 sessions,
   3 affected devices, and 20% error rate in a caller-defined time window);
7. daily EpiScene report generated for the Berlin local calendar day.

Import \`evaluate(snapshot, now_epoch)\` from \`monitor_rules.py\`.
Snapshots are normalized metric dictionaries. All time values are UTC Unix
seconds, except \`daily_report.generated_date_berlin\` (YYYY-MM-DD).

Key integration principles:
- **No secrets:** never pass passwords, tokens, full stream URLs, episode
  contents or identifying customer data into monitoring snapshots.
- **Fail closed:** missing timestamps and missing metrics never imply failure.
- **No spam:** persist returned stable \`Alert.key\` values, acknowledgements,
  resolved state and timestamps in a protected backend event database.
- **No automatic restart on mismatch:** deployment must compare checksums,
  stage backups, restart only with safe drain, then verify analysis progress.
- **Independent uptime check:** a monitor running on the Hetzner analysis
  server cannot detect its own complete outage. Run critical probes externally.
- **Client telemetry:** requires explicit implementation and a privacy review.
- **FCM integration:** only a protected server should send notifications.
  Never embed FCM server credentials in the Android app.
- **Playlist credential rotation:** the live Hetzner private backend source
  must be audited first. Preserve playlist IDs and analysis/marker history,
  invalidate stale stream URLs and re-derive stream locations only through
  authenticated provider configuration. Do not wipe the analysis database.

Planned follow-up work, intentionally **not** included in this commit:
metric adapters for current production services; secure incident database and
dedup/resolution workflow; authenticated admin API; Android login/dashboard,
notification settings, FCM, and a separately signed private admin APK.

Run tests:
\`\`\`bash
cd tools/epimediahub-admin
python3 -m unittest -v test_monitor_rules.py
\`\`\`
