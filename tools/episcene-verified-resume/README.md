# EpiScene – verified restart gate (2026-10-17)

This is a **post-update safety gate**, not a claim that the unversioned Hetzner analysis engine has already been patched or deployed. It never edits customer playlists, analysis markers, job states, approval thresholds, or production SQLite records.

After a separately verified recognition-code deployment, it can:
- Pause only the existing analysis timer while the current bounded batch completes. Never terminate an active batch or playback; abort if a viewer becomes active.
- Restart only the EpiScene compute worker and provisioning API at a quiescent boundary; require both local HTTP health endpoints.
- Always restore the originally active timer on success/failure.
- Optionally request an ordinary analysis batch without resetting its queue.
- Demand *fresh* heartbeat, `analysis_completion` and successful terminal job events on each of lanes 8 and 10 with pre-existing queued/running work.
- Fail nonzero for stale heartbeat, one-lane-only progress, failed-only jobs, missing source inventory/schema, disabled timer or unavailable health endpoints.

Use `--timeout 900` for read-only post-deployment verification. Add `--restart --kick` only after verified installation of actual backend changes. Root is needed for restart. If production has been customized again, run read-only diagnostics instead of forcing a restart.

**Current limitation:** real EpiScene analyzer/provisioning source is installed at Hetzner under `/opt/epimediahub` and is *not* versioned in this GitHub repo. This PR intentionally does not guess or overwrite that code and cannot alone improve recognition precision or automatic approvals. The 2026-10-17 user report shows 288 interruptions and 1 new automatic approval; improvement requires inspection/patching of installed source and live testing. No GitHub connector can access or restart the Hetzner host directly.
