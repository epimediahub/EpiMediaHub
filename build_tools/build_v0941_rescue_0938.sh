#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
BASE_COMMIT="c8bbf22bab384c700164dc2c1d1dc6298e81f8c0"
T=/tmp/epimedia0941
P="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/plugin.py"

rm -rf "$T"
mkdir -p "$T/ar" "$T/data" "$T/control" "$T/pkg"

# Restore the exact last-known-starting v0.9.38 package from Git history.
git fetch --depth=1 origin "$BASE_COMMIT"
git show "$BASE_COMMIT:EpiMediaHub_v0.9.38.ipk" > "$T/base.ipk"

cd "$T/ar"
ar x "$T/base.ipk"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

# Persistent user data must stay outside the package payload.
rm -rf "$T/data/etc/enigma2/EpiMediaHub" "$T/data/etc/enigma2/epimediahub"

export P
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['P'])
t=p.read_text(encoding='utf-8')
if t.count('PLUGIN_VERSION = "0.9.38"') != 1:
    raise SystemExit('Expected exactly one v0.9.38 plugin version marker')
t=t.replace('PLUGIN_VERSION = "0.9.38"','PLUGIN_VERSION = "0.9.41"',1)
p.write_text(t,encoding='utf-8')
PY

# Rescue package install hooks: no cache/user-data backup, no data removal.
cat > "$T/control/preinst" <<'SH'
#!/bin/sh
rm -rf /tmp/epimediahub-package-backup /tmp/epimediahub-update-backup 2>/dev/null || true
exit 0
SH
chmod 755 "$T/control/preinst"

cat > "$T/control/postinst" <<'SH'
#!/bin/sh
set -e
mkdir -p /etc/enigma2/EpiMediaHub/playlists /etc/enigma2/epimediahub
exit 0
SH
chmod 755 "$T/control/postinst"

sed -i 's/^Version:.*/Version: 0.9.41/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.41 rescue rollback to known-good v0.9.38 runtime/' "$T/control/control"

python3 -m py_compile "$P"
find "$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub" -type d -name __pycache__ -prune -exec rm -rf {} +

# Rescue guards: this must remain the v0.9.38 runtime, only re-versioned.
grep -Fq 'PLUGIN_VERSION = "0.9.41"' "$P"
grep -Fq 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -Fq 'directory_back_parent_ok' "$P"
grep -Fq 'list_back_parent_ok' "$P"
grep -Fq 'home_back_parent_ok' "$P"
grep -Fq 'class EpiEPGGridScreen(Screen)' "$P"
grep -Fq 'def xtream_catchup_url' "$P"
grep -Fq 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -Fq 'def _playlist_web_generate_qr' "$P"
grep -Fq 'FAMILY_PIN_HASH' "$P"
grep -Fq 'family_skins_unlocked' "$P"
grep -Fq 'parental_pin_hash' "$P"

# Confirm the v0.9.39 native-player experiment is NOT present.
python3 - <<'PY'
import os,re
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
if re.search(r'eServiceReference\(\s*1\s*,', t):
    raise SystemExit('Rescue build unexpectedly contains v0.9.39 native type-1 refs')
required=(
    'eServiceReference(4097, 0, next_url)',
    'eServiceReference(4097, 0, target_url)',
    'eServiceReference(4097, 0, entry.get("url", ""))',
    'eServiceReference(4097,0,url)',
    'eServiceReference(4097, 0, entry.get("url"))',
)
for item in required:
    if item not in t:
        raise SystemExit('Expected v0.9.38 playback ref missing: '+item)
print('v0.9.41 rescue runtime guard: exact v0.9.38 playback family retained')
PY

python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.41 rescue feature guards: OK')
PY

sh -n "$T/control/preinst"
sh -n "$T/control/postinst"

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.41.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"

ar t EpiMediaHub_v0.9.41.ipk | grep -Fxq debian-binary
ar t EpiMediaHub_v0.9.41.ipk | grep -Fxq control.tar.gz
ar t EpiMediaHub_v0.9.41.ipk | grep -Fxq data.tar.gz
if ar p EpiMediaHub_v0.9.41.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: rescue package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.41.ipk)
echo "v0.9.41 size: $S bytes"
H=$(sha256sum EpiMediaHub_v0.9.41.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.41.ipk" > EpiMediaHub_v0.9.41.ipk.sha256
printf '{\n  "version": "0.9.41",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.41.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.41.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add EpiMediaHub_v0.9.41.ipk EpiMediaHub_v0.9.41.ipk.sha256 update.json
git commit -m 'Publish EpiMediaHub v0.9.41 rescue rollback to v0.9.38 runtime'
git push
