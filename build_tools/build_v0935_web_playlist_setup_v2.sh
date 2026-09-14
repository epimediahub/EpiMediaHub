#!/usr/bin/env bash
set -euo pipefail
SRC="${GITHUB_WORKSPACE:-$(pwd)}/build_tools/build_v0935_web_playlist_setup.sh"
TMP=/tmp/build_v0935_web_playlist_setup_fixed.sh
cp "$SRC" "$TMP"
python3 - "$TMP" <<'PY'
import sys
from pathlib import Path
p=Path(sys.argv[1])
t=p.read_text(encoding='utf-8')
old="web_code=r'''"
if old not in t:
    raise SystemExit('web_code opening delimiter not found')
t=t.replace(old,'web_code=r"""',1)
old_close="\n'''\nt=t.replace(profile_anchor,web_code+profile_anchor,1)"
if old_close not in t:
    raise SystemExit('web_code closing delimiter not found')
t=t.replace(old_close,'\n"""\nt=t.replace(profile_anchor,web_code+profile_anchor,1)',1)
p.write_text(t,encoding='utf-8')
PY
bash "$TMP"
