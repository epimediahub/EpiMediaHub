# EpiScene bounded compute + smart priority (staging only)

**23 October 2026. No production worker or database has been modified by this PR.**

## Goal and separation of duties

1. Existing 4K ANALYSE (playlist 8) and THE BEST (playlist 10) keep **one
   provider stream each**, with no third account/stream.
2. Human-approved markers from **any authorized user/customer playlist** can
   inform advisory priority for episodes in an existing analysis playlist.
3. Separate local CPU processing of previously captured material is an
   optional **future** step, not a license to fetch additional IPTV episodes.
4. The deployed scheduler, analyser, scene/capture, remote and release worker
   files must be inventoried, contract-tested and SHA-256-aligned **before**
   any live priority or compute adapter is attached.
5. The automatic existing release, feedback learning, auth, VPN and player
   behavior must stay unchanged unless independently verified.

## Implemented here (read-only)

- smart_priority.py uses authenticated, active, positive feedback from any
  playlist and the original approved source record. Series title, season and
  episode must exactly agree with server-held asset data; only subsequent
  already queued episodes in playlists 8/10 can be proposed.
  Maximum two suggestions per analysis playlist, at most four episodes ahead.
  It never updates skip_jobs, invents episode metadata, streams content, or
  copies timestamps across incompatible provider cuts.
- offline_capacity.py bounds potential local CPU lanes to 0–2 after
  reserving CPU and RAM. With unknown/busy CPU utilization, it recommends
  zero. It does not create a process or schedule downloads.
- worker_version_gate.py inventories an allowlist of installed Python
  components and checks their full SHA-256 hashes and required active systemd
  services against an operator-reviewed pinned manifest. It never restarts
  anything, imports server worker code or opens IPTV streams. Hash agreement
  alone is not proof of runtime/API compatibility.

## Checks on the correct Hetzner analysis host

Run using an approved checkout of this branch, read-only:

    python3 tools/episcene-learning-v1/compute-lanes/worker_version_gate.py
    python3 tools/episcene-learning-v1/compute-lanes/offline_capacity.py
    python3 tools/episcene-learning-v1/compute-lanes/smart_priority.py
    python3 tools/episcene-learning-v1/diagnostics/runtime_deadlines.py

The inventory prints abbreviated file digests, not credentials. The priority
planner outputs job IDs but makes no changes. The memory/CPU adviser
deliberately outputs zero if current analyzer utilization is unknown.

Before any worker activation, the operator must inspect the exact deployed
files and generate a private, reviewed manifest covering at least:
analysis_worker, scheduler, scene, release. Add automation,
reliability and remote_worker wherever those files actually run.
The manifest records the full approved SHA-256 of every component and
the real worker-facing service names that must remain active. Different
components do not need matching literal version strings; their compatible
contract revisions need to be independently integration-tested.

Manifest shape (hashes omitted intentionally; never invent a trusted baseline):

    {
      "schema": 1,
      "integration_test_run": "<real reviewed integration run>",
      "components": {
        "analysis_worker": {"path": "/opt/epimediahub/provisioning/skip_analysis_worker.py", "sha256": "<real 64 hex>"},
        "scheduler": {"path": "/opt/epimediahub/provisioning/skip_schedule.py", "sha256": "<real 64 hex>"},
        "scene": {"path": "/opt/epimediahub/provisioning/skip_scene.py", "sha256": "<real 64 hex>"},
        "release": {"path": "/opt/epimediahub/provisioning/skip_release.py", "sha256": "<real 64 hex>"}
      },
      "services": ["<real active analysis worker>.service"]
    }

    python3 tools/episcene-learning-v1/compute-lanes/worker_version_gate.py --manifest /root/episcene-approved-versions.json

Non-zero exit code blocks a proposed rollout. Preserve original
systemd unit files, source paths and SHA-256 digests as rollback points.
Do not generate the approved manifest by copying whatever broken revision
happens to be installed; check real integration tests and deployed
service bindings first.

## Rollout still requiring real worker source and server access

- Inspect exact function contracts of deployed skip_analysis_worker.py,
  skip_schedule.py, skip_scene.py, the release module and any remote worker.
  Existing unified-marker-bridge/inspect_worker_binding_contract.py,
  inspect_worker_return_contract.py and inspect_active_runtime.py help.
- Add an opt-in, disabled-by-default scheduler hook that consumes advisory
  priority IDs within each existing lane. Never preempt an active stream;
  fairness must preserve ordinary queued work.
- Refactor the actual capture/compute boundary of the deployed analyzer.
  Only confirmed local, already captured audio/video work may run in extra
  process lanes, with CPU/RAM and job timeouts and no provider network calls.
  Capture and provider authorization stay in their original lanes.
- Stage test with real installed worker versions, original scheduler outcomes,
  zero increases in concurrent provider sessions, bounded memory, no regression
  in worker heartbeat, marker release or existing learning timers.
- Only after passing integration tests, pin the approved manifest, enable the
  hook with a reversible feature flag, run version/service gate again, and
  verify resumed job progress on both playlists. Roll back the hook if
  any check fails. Do not restart or replace all workers simultaneously.

Unit tests here use synthetic data only. GitHub CI success is not equivalent
to validated live deployment or aligned server worker versions.
