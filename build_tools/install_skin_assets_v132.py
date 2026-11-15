#!/usr/bin/env python3
"""Install the pinned offline portraits and historical team marks."""
import hashlib, json, os
from pathlib import Path
source=Path(__file__).resolve().parent.parent/'android/v1.0.32'
dest=Path(os.environ['PROJECT_ROOT'])/'app/src/main'
manifest=json.loads((source/'artwork_manifest.json').read_text())
assert manifest['storage']=='git_assets'
for name,digest in manifest['files'].items():
    assert name.startswith(('assets/','res/drawable-nodpi/'))and '..'not in Path(name).parts
    data=(source/'artwork'/name).read_bytes()
    assert hashlib.sha256(data).hexdigest()==digest, name
    path=dest/name;path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+'.tmp');temporary.write_bytes(data);temporary.replace(path)
print(f"Installed {manifest['portraitCount']} upper-body windows and {manifest['historicalMarkCount']} historical marks")
