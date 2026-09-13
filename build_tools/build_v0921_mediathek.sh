#!/usr/bin/env bash
set -euo pipefail

# Build the Mediathek feature from the current stable 0.9.20 package,
# but publish it as a real new updater-visible release: 0.9.21.
TMP_SCRIPT=/tmp/build_v0921_mediathek_inner.sh
python3 - <<'PY'
from pathlib import Path
src = Path('build_tools/build_v0920_mediathek.sh').read_text(encoding='utf-8')
# Keep the stable package as input, but publish every generated artifact as 0.9.21.
src = src.replace('v0.9.20', 'v0.9.21')
src = src.replace('BASE="$WORKSPACE/EpiMediaHub_v0.9.21.ipk"', 'BASE="$WORKSPACE/EpiMediaHub_v0.9.20.ipk"')
# The source plugin itself must identify as 0.9.21.
needle = "p.write_text(t, encoding='utf-8')"
replacement = "t = t.replace('PLUGIN_VERSION = \\\"0.9.20\\\"', 'PLUGIN_VERSION = \\\"0.9.21\\\"', 1)\n" + needle
if needle not in src:
    raise SystemExit('plugin write anchor missing')
src = src.replace(needle, replacement, 1)
# Make the source-version validation match the new release.
src = src.replace("if 'PLUGIN_VERSION = \\\"0.9.20\\\"' not in t:", "if 'PLUGIN_VERSION = \\\"0.9.21\\\"' not in t:")
Path('/tmp/build_v0921_mediathek_inner.sh').write_text(src, encoding='utf-8')
PY
bash -x "$TMP_SCRIPT"
