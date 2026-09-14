#!/usr/bin/env bash
set -euo pipefail

# Fix the one build-time regex substitution detail from the first guarded run.
# Using a callable replacement keeps backslash-n sequences literal in plugin.py.
python3 - <<'PY'
from pathlib import Path
p=Path('build_tools/build_v0940_update_install_fix.sh')
t=p.read_text(encoding='utf-8')
old='t,n=pattern.subn(replacement,t,count=1)'
new='t,n=pattern.subn(lambda _match: replacement,t,count=1)'
if t.count(old) != 1:
    raise SystemExit('Expected one regex replacement call, found %d' % t.count(old))
p.write_text(t.replace(old,new,1),encoding='utf-8')
PY

exec bash build_tools/build_v0940_update_install_fix.sh
