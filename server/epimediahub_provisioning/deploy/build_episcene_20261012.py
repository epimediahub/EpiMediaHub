#!/usr/bin/env python3
"""Reproducibly embed reviewed source modules in the standalone installer."""
import base64
import hashlib
import json
from pathlib import Path
import re
import zlib

ROOT=Path(__file__).resolve().parents[1]
INSTALLER=Path(__file__).with_name('install_episcene_20261012.py')
MODULES=('skip_scene_reliability.py','skip_variant_reuse.py','skip_tail_check.py','skip_source_preferences.py')


def main():
    packed=zlib.compress(json.dumps({name:(ROOT/name).read_text() for name in MODULES},sort_keys=True,separators=(',',':')).encode(),9)
    text=INSTALLER.read_text()
    text,n=re.subn(r"(?m)^PAYLOAD = '[^']*'$",'PAYLOAD = '+repr(base64.b64encode(packed).decode()),text)
    if n!=1:
        raise RuntimeError('Unexpected installer payload anchor')
    text,n=re.subn(r"(?m)^PAYLOAD_SHA256 = '[^']*'$",'PAYLOAD_SHA256 = '+repr(hashlib.sha256(packed).hexdigest()),text)
    if n!=1:
        raise RuntimeError('Unexpected installer integrity anchor')
    INSTALLER.write_text(text)


if __name__=='__main__':
    main()
