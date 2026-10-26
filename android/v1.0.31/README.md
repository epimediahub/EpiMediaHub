# EpiMediaHub Android 1.0.31

Each of the 134 sport teams has one base ID and two derived IDs: `__players` and `__legends`. Group membership includes the base only, so variants stay in a horizontal row on their team rather than becoming separate vertical entries. Existing group IDs, accents, badge resources and backdrop resources remain intact. Saved variant IDs use the existing theme preference and private-skin gate.

The catalog includes the previous 41 clubs, 20 national teams and 11 F1 teams, plus all 30 NBA and 32 NFL franchises. F1 featured drivers follow the official 2026 grid. Current US featured players are resolved from ESPN roster records rather than assuming last season's roster. Team-history and US motorsport icons are labeled as such for newer F1 teams.

Artwork is bundled offline. The pinned `artwork_manifest.json` verifies the archive and each extracted file before any source patch runs. Its source-credit JSON retains source URLs and player identities. The picture loader has an 8 MiB memory limit, uses only local asset URIs and does not crossfade. Only visible cards request images.

The paired Ferrari, Juventus and Lakers portraits were prepared with transparency; all other variants use reviewed individual athlete pictures. Handwritten-looking names are an autograph-style design, not a claim of verified athlete signatures.

Validation includes all-team catalog/badge/scene coverage, decodable assets, persisted selection and private lock, real Compose remote left/right/OK, phone swipe, home visibility on TV and compact landscape phones, plus every prior parental, catalog and playback regression and native Android audio check.
