"""Reproducible, self-contained installer; no downloads when executed on Hetzner."""
import base64
import hashlib
import json
from pathlib import Path
import sys
import textwrap
import zlib

sys.path.insert(0,str(Path(__file__).resolve().parent))
from install_skip_daily_reports import FILES


def build(destination):
    root=Path(__file__).resolve().parents[1]
    bundle={'installer':(root/'deploy/install_skip_daily_reports.py').read_text(),
            'files':{name:{'content':(root/name).read_text(),
                      'sha256':hashlib.sha256((root/name).read_bytes()).hexdigest()} for name in FILES}}
    packed=zlib.compress(json.dumps(bundle,ensure_ascii=False,separators=(',',':')).encode(),9)
    code='''#!/usr/bin/env bash
# EpiScene daily reports: run on the Hetzner host with the existing dashboard.
set -euo pipefail
if [[ "$(id -u)" != 0 ]]; then echo 'Bitte mit sudo ausführen.' >&2; exit 1; fi
python3 - <<'EPISCENE_INSTALL'
import base64,hashlib,json,zlib
encoded="""
'''+ '\n'.join(textwrap.wrap(base64.b64encode(packed).decode(),100))+'''
"""
packed=base64.b64decode(encoded)
assert hashlib.sha256(packed).hexdigest()=="'''+hashlib.sha256(packed).hexdigest()+'''", 'Unvollständiger Installer'
bundle=json.loads(zlib.decompress(packed))
exec(compile(bundle['installer'],'episcene-installer','exec'))
try:
    main(bundle['files'])
except Exception as error:
    import subprocess
    if isinstance(error,subprocess.CalledProcessError):
        print('Prüfung fehlgeschlagen:',error.stderr[-2500:] if error.stderr else str(error))
    else: print('Installation abgebrochen:',str(error))
    raise SystemExit(1)
EPISCENE_INSTALL
'''
    Path(destination).write_text(code)
    return hashlib.sha256(code.encode()).hexdigest()


if __name__=='__main__':
    print(build(sys.argv[1]))
