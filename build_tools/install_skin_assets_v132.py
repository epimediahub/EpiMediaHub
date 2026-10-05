#!/usr/bin/env python3
"""Install the pinned offline portrait and historical-mark archive."""
import base64, hashlib, io, json, os, tarfile
from pathlib import Path
source=Path(__file__).resolve().parent.parent/'android/v1.0.32'
dest=Path(os.environ['PROJECT_ROOT'])/'app/src/main'
manifest=json.loads((source/'artwork_manifest.json').read_text())
parts=sorted((source/'artwork_parts').glob('part_*'));assert parts
packed=base64.b64decode(''.join(p.read_text().strip()for p in parts),validate=True)
assert len(packed)==manifest['bytes']and hashlib.sha256(packed).hexdigest()==manifest['sha256']
with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz')as tar:
    seen=set()
    for member in tar.getmembers():
        assert member.isfile()and member.name in manifest['files']and member.name not in seen
        assert member.name.startswith(('assets/','res/drawable-nodpi/'))and '..'not in Path(member.name).parts
        data=tar.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==manifest['files'][member.name]
        path=dest/member.name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);seen.add(member.name)
    assert seen==set(manifest['files'])
print(f"Installed {manifest['portraitCount']} upper-body windows and {manifest['historicalMarkCount']} historical marks")
