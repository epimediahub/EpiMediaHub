# EpiScene shared knowledge (2026-10-21)

This is a **development component, not a Hetzner deployment or automatic approval**.

- Sources 8 (4K ANALYSE, language evidence separately guarded) and 10 (THE BEST) can contribute references to one SQLite knowledge store. Consumer playlist IDs are never accepted as sources.
- Episode identity requires a verified IMDb or TVDB ID plus season/episode. Matching names and equal runtimes alone are not proof of matching media cuts. Content SHA-256 fingerprint matching is required for direct cross-playlist reuse.
- Scene search priorities: recaps first 3 min, intros first 10 min, credits last 5 min, with fallback outside these windows.
- Accept both IntroDB \`GET /segments\` (IMDb) and TheIntroDB v4 \`GET /media\` (TVDB). These are **different services** and their payloads cannot be conflated.
- Third-party timestamps are kept as trusted **references** but are NOT sufficient to approve skipping for an unverified source cut.
- Conflicting fingerprints/boundaries go into review. No marker overwrites. Database writes are isolated to an explicit learning store, not \`provisioning.db\`.
- \`eligible_for_original_release_gate\` means **may be submitted to** EpiScene's existing audio/visual release checks; it is never a green light to bypass those checks.
- Production integration needs exact current Hetzner modules, real episode ID mappings, safe one-shot installer, verified backups and rollback, both analysis lanes confirmed progressing, original marker release path tested, and app consumption verified before activation.
- Last report 2026-10-21: 86 attempts, 27 marker proposals, 0 automatic approvals. This component alone does not fix the analyzer's slow visual phases.

Standalone offline regression:
\`\`\`sh
cd tools/episcene-learning-v1/shared-knowledge
python3 -m unittest -v test_shared_knowledge.py
\`\`\`

Do **not** merge or deploy this as a "complete update" without the production gates above.
