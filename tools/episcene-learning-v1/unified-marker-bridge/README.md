# EpiScene Unified Marker Bridge (21 Oct 2026)

**Purpose:** one shared, reviewable knowledge layer for **4K ANALYSE (8)**
and **THE BEST (10)**. No Jellyfin or Silo runtime is required.
This is an *integration component*, not a production deployment or new Android APK.

## What exists in this package

- Reads **authenticated, still-active positive feedback** from
  `feedback_versions` in the existing EpiScene learning service.
  Reads `skip_assets` from the original analyzer **read-only**.
  Rejects weak `source=device` / `status=approved` claims.
  Rebuilds the isolated verified marker snapshot so revocations propagate.
- Two **independent external read-only adapters**:
  [IntroDB](https://introdb.app/docs/api) `GET /segments` (IMDb)
  and [TheIntroDB](https://theintrodb.github.io/theintrodb-npm/migration-v3-to-v4.html)
  `GET /v4/media` (prefer TVDB, fallback IMDb, duration-based version selection).
  They are **not** the same database. Missing IDs skip the corresponding source.
  HTTPS URLs are fixed, timeouts and response-size bounds apply.
- Search hints: recap first 3 minutes, intro first 10 minutes, outro last
  5 minutes. These are initial **search priorities**, not hard exclusion rules.
- Rejects invalid, reversed, negative or beyond-duration marker boundaries.
  Supports TheIntroDB's null start / null end and multiple segments.
- Cross-playlist reuse only for the **same actual cut** with the same 64-hex
  SHA-256 content fingerprint and near-identical duration. An authenticated
  match for the exact same asset also works without fingerprint.
- Conflicting confirmed markers are withheld; external markers go to
  `review_candidates`, **never directly to customer devices**.

### Integrating with the existing EpiScene service

Install the module alongside the backend and wire the existing server's
episode-resolution endpoint to `evaluate()`. Provide `playlist_id`,
`asset_key`, `season`, `episode`, `duration_ms`, IMDb or TVDB ID (when
available), and **verified content fingerprint** (only when actually measured).
Do **not** derive a cut fingerprint from title, stream URL, language, provider
name or duration alone.

`ready_verified` may be sent to the existing marker playback endpoint **only
after integration tests against the actual backend and app contract**. Keep
external `review_candidates` internal. If no actual content fingerprint exists,
sharing *across providers* is deliberately disabled. This safeguards German
and Italian releases with different recaps/edits.

Authenticated input example for resolution:

```json
{
  "playlist_id": 8,
  "asset_key": "episode-123",
  "season": 1,
  "episode": 3,
  "duration_ms": 2700000,
  "imdb_id": "tt0903747",
  "tvdb_id": 81189,
  "fingerprint": "",
  "title": "Sample series"
}
```

### CLI (on backend, not on users' devices)

```bash
python3 bridge.py sync-verified \
  --feedback /var/lib/episcene-learning/reference-round-40/feedback.sqlite3 \
  --production /var/lib/epimediahub/provisioning.db \
  --store /var/lib/episcene-learning/unified-markers.sqlite3

echo '{"playlist_id":8,"asset_key":"episode-123","season":1,"episode":1,"duration_ms":2700000,"imdb_id":"tt0903747"}' \
 | python3 bridge.py evaluate \
    --store /var/lib/episcene-learning/unified-markers.sqlite3
```

Use the service's established protection and permissions for the output SQLite
file. The command deliberately cannot modify the production analyzer or
feedback database.

### Deliberately **not** claimed as completed

This PR does not contain the deployed Hetzner provisioning application, the
current streaming player's source/API contract, an authenticated in-app update,
an audio/video *fingerprint generator*, automated job scheduling, source
response caching or production release orchestration. Those must be integrated
and tested in their respective running services before rollout.

**In particular:** A SHA-256 content hash of a whole file usually cannot
be computed for an IPTV URL without full access. A proper *cut* fingerprint
needs a sampled A/V fingerprint algorithm or equivalent verified matching
evidence; a hash of provider metadata would be unsafe. Until then, verified
source-specific markers and external review candidates work, but automatic
cross-provider publication stays gated.

### Verification

```bash
python3 -m unittest -v test_bridge.py
python3 -m py_compile bridge.py test_bridge.py
```

All tests use in-memory fixtures / temporary SQLite files with no external
streams or HTTP requests. The GitHub Actions workflow performs these checks.


## Backend integration step (October 21, 2026)

The next-stage integration is implemented in `runtime_integration.py`.
It exposes **functions**, not an unauthenticated HTTP endpoint.

1. **Authenticated playback**: the existing playback handler must validate
   the real device/session, playlist ownership and stream asset identity;
   call `playback_resolution(payload, authorize=trusted_authorizer,
   store=private_knowledge_file)` only after those checks.
   The callback MUST independently validate both playlist ID and asset key.
   Render returned `markers` in the existing Fire TV/Android seek overlay.
   Never consume `review_candidates` as active skip buttons.
2. **Analysis**: the scheduler may call
   `external_review_resolution(payload,cache=private_advisory_db)` for
   **analysis IDs 8 and 10 only**. This sends requests only to IntroDB /
   TheIntroDB and opens zero provider video streams. The result must feed
   the existing independent visual/audio verifier, not bypass it.
   `planning_hints` is restricted to one suggested task per provider and
   does NOT modify the live scheduler or reserve slots.
3. **Knowledge sync**: from the checked-out repo, on the *correct* Hetzner
   host, use `sudo bash install_unified.sh --check`. Only when every
   preflight and schema check is green, execute
   `sudo bash install_unified.sh --apply` **once**. The installer sets up a
   separate private verified-marker database and hourly systemd snapshot.
   Existing approval tables, clients and workers are not rewritten.
   Existing/unknown systemd units or knowledge files result in a safe STOP.

### Remaining external dependencies

- The deployed Hetzner source of the existing Flask/API application and its
  **real** device-session/playlist authorization handler are required to call
  `playback_resolution` from an actual secured route.
- The current Android TV/player 1.x source is required to display these
  verified skip markers; the old Enigma2 packages and Android 0.4.x patches
  in this repository are **not** an adequate substitute.
- Actual identical-cut matching still needs a verified A/V fingerprint or
  another reliable mapping supplied by the existing analyzer. A SHA-256 of
  an image-window cache is **not** evidence that two full files share a cut.
- TheIntroDB API v4 respects `mapping`; passing a season/episode number
  without knowing its release order can select an unrelated episode.
- Public external hints require per-episode metadata (IMDb/TVDB IDs)
  from an authorized metadata source. We do not open customer streams or
  infer IDs from similarity of display titles.

**Release status:** Installing the hourly private snapshot is useful backend
preparation. It is **not** end-to-end production integration or an updated
customer player APK, and should never be represented as such.
