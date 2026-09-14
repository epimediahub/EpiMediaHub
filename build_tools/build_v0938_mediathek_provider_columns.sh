#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.37.ipk"
T=/tmp/epimedia0938
P="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/plugin.py"

rm -rf "$T"
mkdir -p "$T/ar" "$T/data" "$T/control" "$T/pkg"
cd "$T/ar"
ar x "$B"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary
rm -rf "$T/data/etc/enigma2/EpiMediaHub" "$T/data/etc/enigma2/epimediahub"

export P
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['P'])
t=p.read_text(encoding='utf-8')

if 'PLUGIN_VERSION = "0.9.37"' not in t:
    raise SystemExit('Expected v0.9.37 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.37"','PLUGIN_VERSION = "0.9.38"',1)

# Mediathek provider directory: give icons and provider names truly separate columns.
# This avoids relying on font-dependent leading spaces that can let picons cover text.
old_skin='''    list_widget("list",55,130,675,465,23,50) +\n    ''.join('<widget name="provider_icon%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="5" />' % (i,pos(72,136+(i*50)),size(72,40)) for i in range(9)) +'''
new_skin='''    list_widget("list",160,130,570,465,23,50) +\n    ''.join('<widget name="provider_icon%d" position="%s" size="%s" alphatest="on" scale="1" zPosition="5" />' % (i,pos(72,136+(i*50)),size(72,40)) for i in range(9)) +'''
if t.count(old_skin) != 1:
    raise SystemExit('Mediathek provider skin anchor missing or ambiguous: %d' % t.count(old_skin))
t=t.replace(old_skin,new_skin,1)

old_list='''self["list"]=MenuList(["            "+x["label"] for x in self.items])'''
new_list='''self["list"]=MenuList([x["label"] for x in self.items])'''
if t.count(old_list) != 1:
    raise SystemExit('Mediathek provider list anchor missing or ambiguous: %d' % t.count(old_list))
t=t.replace(old_list,new_list,1)

notes='''_RELEASE_NOTES = {\n    "0.9.38": {\n        "de": ["Mediathek-Anbieteransicht: Picons und Anbieternamen haben jetzt getrennte Spalten und überdecken sich nicht mehr."],\n        "en": ["Mediathek provider view: icons and provider names now use separate columns and no longer overlap."],\n        "tr": ["Mediathek sağlayıcı görünümünde simgeler ve sağlayıcı adları artık ayrı sütunlarda ve üst üste gelmiyor."],\n        "it": ["Vista provider Mediathek: icone e nomi ora usano colonne separate e non si sovrappongono più."],\n        "es": ["Vista de proveedores Mediathek: los iconos y los nombres ahora usan columnas separadas y ya no se superponen."],\n    },'''
if '_RELEASE_NOTES = {' not in t:
    raise SystemExit('Release notes anchor missing')
t=t.replace('_RELEASE_NOTES = {',notes,1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.38/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.38 Mediathek provider icon\/name layout fix/' "$T/control/control"

python3 -m py_compile "$P"

# New layout guards.
grep -Fq 'PLUGIN_VERSION = "0.9.38"' "$P"
grep -Fq 'list_widget("list",160,130,570,465,23,50)' "$P"
grep -Fq 'self["list"]=MenuList([x["label"] for x in self.items])' "$P"
if grep -Fq 'self["list"]=MenuList(["            "+x["label"] for x in self.items])' "$P"; then
  echo 'ERROR: font-dependent provider padding still present' >&2; exit 1
fi

# Critical existing features/fixes must survive unchanged.
grep -Fq 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -Fq 'directory_back_parent_ok' "$P"
grep -Fq 'list_back_parent_ok' "$P"
grep -Fq 'home_back_parent_ok' "$P"
grep -Fq 'class EpiEPGGridScreen(Screen)' "$P"
grep -Fq 'def xtream_catchup_url' "$P"
grep -Fq 'RecordTimerEntry' "$P"
grep -Fq 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -Fq 'def _playlist_web_generate_qr' "$P"
grep -Fq 'FAMILY_PIN_HASH' "$P"
grep -Fq 'family_skins_unlocked' "$P"
grep -Fq 'parental_pin_hash' "$P"

python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
# Prove the provider icon column ends before the text column starts in logical 1280x720 coordinates.
if 'pos(72,136+(i*50)),size(72,40)' not in t:
    raise SystemExit('Provider icon geometry changed unexpectedly')
if 'list_widget("list",160,130,570,465,23,50)' not in t:
    raise SystemExit('Provider text column geometry missing')
if 72 + 72 >= 160:
    raise SystemExit('Provider icon/text columns overlap')
# Rai app-local PIN must stay absent while family/parental controls remain.
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.38 Mediathek provider column guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.38.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"

if ar p EpiMediaHub_v0.9.38.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.38.ipk)
echo "v0.9.38 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.38.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.38.ipk" > EpiMediaHub_v0.9.38.ipk.sha256
printf '{\n  "version": "0.9.38",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.38.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.38.ipk.sha256
rm -f EpiMediaHub_v0.9.37.ipk EpiMediaHub_v0.9.37.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.38 Mediathek provider layout fix'
git push
