#!/usr/bin/env python3
"""Install and verify a pinned, offline Android artwork package."""
import base64,hashlib,io,json,os,tarfile
from pathlib import Path
source=Path(__file__).resolve().parent.parent/'android/v1.0.31';destination=Path(os.environ['PROJECT_ROOT'])/'app/src/main'
manifest=json.loads((source/'artwork_manifest.json').read_text());parts=sorted((source/'artwork_parts').glob('part_*'))
assert parts,'No artwork parts'
packed=base64.b64decode(''.join(p.read_text().strip()for p in parts),validate=True)
assert len(packed)==manifest['bytes']and hashlib.sha256(packed).hexdigest()==manifest['sha256'],'Artwork archive mismatch'
with tarfile.open(fileobj=io.BytesIO(packed),mode='r:gz')as tar:
 seen=set()
 for member in tar.getmembers():
  assert member.isfile()and member.name in manifest['files']and member.name not in seen,'Unexpected artwork entry'
  assert member.name.startswith(('assets/','res/drawable-nodpi/'))and '..'not in Path(member.name).parts
  data=tar.extractfile(member).read();assert hashlib.sha256(data).hexdigest()==manifest['files'][member.name]
  file=destination/member.name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(data);seen.add(member.name)
 assert seen==set(manifest['files'])
print(f"Installed {len(seen)} verified assets for {manifest['teamCount']} sport teams")
