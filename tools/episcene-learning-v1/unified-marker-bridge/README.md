# EpiScene Unified Marker Bridge (21 Oct 2026)

**Purpose:** one shared, reviewable knowledge layer for **4K ANALYSE (8)**
and **THE BEST (10)**. No Jellyfin or Silo runtime is required.
This is an *integration component*, not a production deployment or new Android APK.

## What exists in this package

- Reads **authenticated, still-active positive feedback** from
  \`feedback_versions\` in the existing EpiScene learning service.
  Reads \`skip_assets\` from the original analyzer **read-only**.
  Rejects weak \`source=device\` / \`status=approved\` claims.
  Rebuilds the isolated verified marker snapshot so revocations propagate.
- Two **independent external read-only adapters**:
  [IntroDB](https://introdb.app/docs/api) \`GET /segments\` (IMDb)
  and [TheIntroDB](https://theintrodb.github.io/theintrodb-npm/migration-v3-to-v4.html)
  \`GET /v4/media\` (prefer TVDB, fallback IMDb, duration-based version selection).
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
  \`review_candidates\`, **never directly to customer devices**.

### Integrating with the existing EpiScene service

Install the module alongside the backend and wire the existing server's
episode-resolution endpoint to \`evaluate()\`. Provide \`playlist_id\`,
\`asset_key\`, \`season\`, \`episode\`, \`duration_ms\`, IMDb or TVDB ID (when
available), and **verified content fingerprint** (only when actually measured).
Do **not** derive a cut fingerprint from title, stream URL, language, provider
name or duration alone.

\`ready_verified\` may be sent to the existing marker playback endpoint **only
after integration tests against the actual backend and app contract**. Keep
external \`review_candidates\` internal. If no actual content fingerprint exists,
sharing *across providers* is deliberately disabled. This safeguards German
and Italian releases with different recaps/edits.

Authenticated input example for resolution:

\`\`\`json
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
\`\`\`

### CLI (on backend, not on users' devices)

\`\`\`bash
python3 bridge.py sync-verified \
  --feedback /var/lib/episcene-learning/reference-round-40/feedback.sqlite3 \
  --production /var/lib/epimediahub/provisioning.db \
  --store /var/lib/episcene-learning/unified-markers.sqlite3

echo '{"playlist_id":8,"asset_key":"episode-123","season":1,"episode":1,"duration_ms":2700000,"imdb_id":"tt0903747"}' \
 | python3 bridge.py evaluate \
    --store /var/lib/episcene-learning/unified-markers.sqlite3
\`\`\`

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

\`\`\`bash
python3 -m unittest -v test_bridge.py
python3 -m py_compile bridge.py test_bridge.py
\`\`\`

All tests use in-memory fixtures / temporary SQLite files with no external
streams or HTTP requests. The GitHub Actions workflow performs these checks.
