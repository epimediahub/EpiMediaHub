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
src = src.replace("Version: 0.9.20", "Version: 0.9.21")
src = src.replace("d['version']='0.9.20'", "d['version']='0.9.21'")
# Fix the asset validation: the filename is generated dynamically in plugin.py.
src = src.replace("grep -q 'home_mediathek' \"$PLUGIN\"", "test -f \"$ROOT/home_mediathek.png\"")
# The source plugin itself must identify as 0.9.21.
needle = "p.write_text(t, encoding='utf-8')"
replacement = "t = t.replace('PLUGIN_VERSION = \\\"0.9.20\\\"', 'PLUGIN_VERSION = \\\"0.9.21\\\"', 1)\n" + needle
if needle not in src:
    raise SystemExit('plugin write anchor missing')
src = src.replace(needle, replacement, 1)
# Keep only one official Enigma package after a successful publish.
anchor = "git config user.name 'github-actions[bot]'"
cleanup = "rm -f EpiMediaHub_v0.9.20.ipk EpiMediaHub_v0.9.20.ipk.sha256\nrm -f .github/workflows/publish-enigma-v0920-mediathek.yml\n" + anchor
if anchor not in src:
    raise SystemExit('publish anchor missing')
src = src.replace(anchor, cleanup, 1)
Path('/tmp/build_v0921_mediathek_inner.sh').write_text(src, encoding='utf-8')
PY
bash -x "$TMP_SCRIPT"
