#!/usr/bin/env bash
set -euo pipefail
W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.25.ipk"
T=/tmp/epimedia0927
P="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/plugin.py"
rm -rf "$T"; mkdir -p "$T/ar" "$T/data" "$T/control" "$T/pkg"
cd "$T/ar"; ar x "$B"; tar -xzf data.tar.gz -C ../data; tar -xzf control.tar.gz -C ../control; cp debian-binary ../pkg/debian-binary
rm -rf "$T/data/etc/enigma2/EpiMediaHub" "$T/data/etc/enigma2/epimediahub"
export P
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['P']); t=p.read_text(encoding='utf-8')
if 'PLUGIN_VERSION = "0.9.25"' not in t: raise SystemExit('Expected v0.9.25 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.25"','PLUGIN_VERSION = "0.9.27"',1)
# Only the Rai Mediathek loses its PIN gate. Family-skin access and parental PINs remain unchanged.
t=t.replace('"label":"Italien · Family"','"label":"Italien"')
t=t.replace('"meta":"Rai · PIN geschützt"','"meta":"RaiPlay"')
t=t.replace('"info":"Familienbereich für frei erreichbare Rai-Inhalte. Geo-Sperren werden nicht umgangen."','"info":"Frei erreichbare Rai-Inhalte. Geo-Sperren werden nicht umgangen."')
t=t.replace('"availability":"Family · Deutschland: titelabhängig"','"availability":"Deutschland: titelabhängig"')
old='''    def _pin_done(self,pin,item):
        if pin is None:return
        if hashlib.sha256(clean_text(pin).encode("utf-8")).hexdigest()!=FAMILY_PIN_HASH:
            self.session.open(MessageBox,"PIN ist falsch.",MessageBox.TYPE_ERROR,timeout=3);return
        self._open_item(item)
    def openSelected(self):
        x=self.selected()
        if not x:return
        if x.get("kind")=="rai":
            try:self.session.openWithCallback(lambda pin:self._pin_done(pin,x),EpiPinScreen,title="Family · Rai International")
            except Exception as e:self.session.open(MessageBox,str(e),MessageBox.TYPE_ERROR,timeout=6)
            return
        self._open_item(x)
'''
new='''    def openSelected(self):
        x=self.selected()
        if not x:return
        self._open_item(x)
'''
if old not in t: raise SystemExit('Rai PIN block not found')
t=t.replace(old,new,1)
p.write_text(t,encoding='utf-8')
PY
sed -i 's/^Version:.*/Version: 0.9.27/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.27 Rai direct access, Family features retained/' "$T/control/control"
python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.27"' "$P"
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
grep -q 'parental_pin_hash' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8'); a=t.index('class EpiMediathekDirectory(Screen):'); b=t.index('class EpiMediathekList(Screen):',a); x=t[a:b]
if 'Family · Rai International' in x or '_pin_done' in x or 'openWithCallback' in x: raise SystemExit('Rai PIN callback still present')
if 'kind in ("mvw","rai")' not in x: raise SystemExit('Rai direct-open path missing')
print('Rai-only PIN removal guard: OK')
PY
tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"; ar r "$W/EpiMediaHub_v0.9.27.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null; cd "$W"
if ar p EpiMediaHub_v0.9.27.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then exit 1; fi
S=$(stat -c%s EpiMediaHub_v0.9.27.ipk); echo "v0.9.27 size: $S bytes"; [ "$S" -le 25165824 ]
H=$(sha256sum EpiMediaHub_v0.9.27.ipk|awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.27.ipk" > EpiMediaHub_v0.9.27.ipk.sha256
printf '{\n  "version": "0.9.27",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.27.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.27.ipk.sha256
rm -f EpiMediaHub_v0.9.25.ipk EpiMediaHub_v0.9.25.ipk.sha256 EpiMediaHub_v0.9.26.ipk EpiMediaHub_v0.9.26.ipk.sha256
rm -f .github/workflows/inspect-v0925-family-pin.yml inspection/v0925-family-pin.txt
rm -f .github/workflows/publish-enigma-v0926-no-family-pin.yml build_tools/build_v0926_remove_family_pin.sh
git config user.name 'github-actions[bot]'; git config user.email '41898282+github-actions[bot]@users.noreply.github.com'; git add -A; git commit -m 'Publish EpiMediaHub v0.9.27 Rai without PIN'; git push
