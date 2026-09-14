#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.41.ipk"
T=/tmp/epimedia0942
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
if t.count('PLUGIN_VERSION = "0.9.41"') != 1:
    raise SystemExit('Expected exactly one v0.9.41 version marker')
t=t.replace('PLUGIN_VERSION = "0.9.41"','PLUGIN_VERSION = "0.9.42"',1)

replacements = [
('''                dialog=self.session.instantiateDialog(EpiMediathekHome); self.session.execDialog(dialog); _mediathek_debug("home_open_mode","persistent_exec")''',
 '''                self.session.open(EpiMediathekHome); _mediathek_debug("home_open_mode","session_open")'''),
('''            dialog=self.session.instantiateDialog(EpiMediathekDirectory,x["id"],x["label"])
            self.session.execDialog(dialog)
            _mediathek_debug("directory_open_mode","persistent_exec | %s | %s" % (clean_text(x.get("id","")),clean_text(x.get("label",""))))''',
 '''            self.session.open(EpiMediathekDirectory,x["id"],x["label"])
            _mediathek_debug("directory_open_mode","session_open | %s | %s" % (clean_text(x.get("id","")),clean_text(x.get("label",""))))'''),
('''                dialog=self.session.instantiateDialog(EpiMediathekDirectory,x.get("target",""),x.get("label",""))
                self.session.execDialog(dialog)
                _mediathek_debug("directory_open_mode","persistent_exec | %s | %s" % (clean_text(x.get("target","")),clean_text(x.get("label",""))))''',
 '''                self.session.open(EpiMediathekDirectory,x.get("target",""),x.get("label",""))
                _mediathek_debug("directory_open_mode","session_open | %s | %s" % (clean_text(x.get("target","")),clean_text(x.get("label",""))))'''),
('''                dialog=self.session.instantiateDialog(EpiMediathekList,x.get("channel",""),x.get("label",""),"",kind)
                self.session.execDialog(dialog)
                _mediathek_debug("list_open_mode","persistent_exec | %s | %s" % (clean_text(kind),clean_text(x.get("label",""))))''',
 '''                self.session.open(EpiMediathekList,x.get("channel",""),x.get("label",""),"",kind)
                _mediathek_debug("list_open_mode","session_open | %s | %s" % (clean_text(kind),clean_text(x.get("label",""))))'''),
]
for old,new in replacements:
    if old not in t:
        raise SystemExit('Mediathek open anchor missing:\n'+old[:120])
    t=t.replace(old,new,1)

# Add a concise release note entry when the release-note map exists.
anchor='_RELEASE_NOTES = {'
if anchor in t:
    note='''_RELEASE_NOTES = {\n    "0.9.42": {\n        "de": ["Mediathek-Öffnen auf OpenATV 7.6 repariert: Unterseiten werden wieder über den normalen Session-Stack geöffnet.", "Keine Änderungen an Live-TV, VOD, Family-PIN oder Jugendschutz."],\n        "en": ["Fixed opening Mediathek on OpenATV 7.6 by using the normal Enigma2 session stack for Mediathek screens.", "No changes to Live TV, VOD, Family PIN or parental controls."],\n    },'''
    t=t.replace(anchor,note,1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.42/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.42 Mediathek open fix/' "$T/control/control"

python3 -m py_compile "$P"
find "$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub" -type d -name __pycache__ -prune -exec rm -rf {} +

# Targeted Mediathek guards.
grep -Fq 'PLUGIN_VERSION = "0.9.42"' "$P"
grep -Fq 'self.session.open(EpiMediathekHome)' "$P"
grep -Fq 'self.session.open(EpiMediathekDirectory,x["id"],x["label"])' "$P"
grep -Fq 'self.session.open(EpiMediathekDirectory,x.get("target",""),x.get("label",""))' "$P"
grep -Fq 'self.session.open(EpiMediathekList,x.get("channel",""),x.get("label",""),"",kind)' "$P"
if grep -Fq 'instantiateDialog(EpiMediathek' "$P"; then
  echo 'ERROR: stale instantiateDialog Mediathek route remains' >&2; exit 1
fi

# Critical feature regression guards.
grep -Fq 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -Fq 'directory_back_parent_ok' "$P"
grep -Fq 'list_back_parent_ok' "$P"
grep -Fq 'home_back_parent_ok' "$P"
grep -Fq 'class EpiEPGGridScreen(Screen)' "$P"
grep -Fq 'def xtream_catchup_url' "$P"
grep -Fq 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -Fq 'FAMILY_PIN_HASH' "$P"
grep -Fq 'family_skins_unlocked' "$P"
grep -Fq 'parental_pin_hash' "$P"

# Rai app-local PIN must stay removed.
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.42 Mediathek guards: OK')
PY

sh -n "$T/control/preinst"
sh -n "$T/control/postinst"

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.42.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"

ar t EpiMediaHub_v0.9.42.ipk | grep -Fxq debian-binary
ar t EpiMediaHub_v0.9.42.ipk | grep -Fxq control.tar.gz
ar t EpiMediaHub_v0.9.42.ipk | grep -Fxq data.tar.gz
if ar p EpiMediaHub_v0.9.42.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.42.ipk)
echo "v0.9.42 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.42.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.42.ipk" > EpiMediaHub_v0.9.42.ipk.sha256
printf '{\n  "version": "0.9.42",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.42.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.42.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add EpiMediaHub_v0.9.42.ipk EpiMediaHub_v0.9.42.ipk.sha256 update.json
git commit -m 'Publish EpiMediaHub v0.9.42 Mediathek open fix'
git push
