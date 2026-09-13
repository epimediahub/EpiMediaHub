#!/usr/bin/env bash
set -euo pipefail
W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.25.ipk"
T=/tmp/epimedia0926
P="$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub/plugin.py"
rm -rf "$T"; mkdir -p "$T/ar" "$T/data" "$T/control" "$T/pkg"
cd "$T/ar"; ar x "$B"; tar -xzf data.tar.gz -C ../data; tar -xzf control.tar.gz -C ../control; cp debian-binary ../pkg/debian-binary
rm -rf "$T/data/etc/enigma2/EpiMediaHub" "$T/data/etc/enigma2/epimediahub"
export P
python3 - <<'PY'
import os,re
from pathlib import Path
p=Path(os.environ['P']); t=p.read_text(encoding='utf-8')
t=t.replace('PLUGIN_VERSION = "0.9.25"','PLUGIN_VERSION = "0.9.26"',1)
t=re.sub(r'\n# Hidden Family Skin access.*?FAMILY_PIN_HASH\s*=\s*"[^"]+"\n','\n',t,count=1,flags=re.S)
t=t.replace('    settings.setdefault("family_skins_unlocked", False)\n','')
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
t=re.sub(r'^\s*\("accesscode",.*?\),\n','',t,flags=re.M)
t=re.sub(r'\n\s*elif key == "accesscode":\n\s*self\.session\.openWithCallback\(\n\s*self\._familyPinEntered,\n\s*EpiPinScreen,\n\s*tr\("pin_default"\)\n\s*\)\n','\n',t,count=1)
t=re.sub(r'\n    def _familyPinEntered\(self, pin\):\n.*?(?=\n    def openHelp\(self\):)','\n',t,count=1,flags=re.S)
t=t.replace('        family_unlocked = bool(self.settings.get("family_skins_unlocked", False))\n','')
t=t.replace('            if meta.get("family", False) and not family_unlocked:\n                continue\n','')
p.write_text(t,encoding='utf-8')
PY
sed -i 's/^Version:.*/Version: 0.9.26/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.26 no Family PIN, direct Rai access/' "$T/control/control"
python3 -m py_compile "$P"
if grep -q 'FAMILY_PIN_HASH\|family_skins_unlocked\|_familyPinEntered\|Family · Rai International\|Italien · Family\|Rai · PIN geschützt' "$P"; then echo 'Family PIN remains' >&2; exit 1; fi
grep -q 'parental_pin_hash' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8'); a=t.index('class EpiMediathekDirectory(Screen):'); b=t.index('class EpiMediathekList(Screen):',a); x=t[a:b]
assert 'openWithCallback' not in x
assert 'kind in ("mvw","rai")' in x
print('Family PIN removal guard: OK')
PY
tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"; ar r "$W/EpiMediaHub_v0.9.26.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null; cd "$W"
if ar p EpiMediaHub_v0.9.26.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then exit 1; fi
S=$(stat -c%s EpiMediaHub_v0.9.26.ipk); echo "v0.9.26 size: $S bytes"; [ "$S" -le 25165824 ]
H=$(sha256sum EpiMediaHub_v0.9.26.ipk|awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.26.ipk" > EpiMediaHub_v0.9.26.ipk.sha256
printf '{\n  "version": "0.9.26",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.26.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.26.ipk.sha256
rm -f EpiMediaHub_v0.9.25.ipk EpiMediaHub_v0.9.25.ipk.sha256 .github/workflows/inspect-v0925-family-pin.yml inspection/v0925-family-pin.txt
git config user.name 'github-actions[bot]'; git config user.email '41898282+github-actions[bot]@users.noreply.github.com'; git add -A; git commit -m 'Publish EpiMediaHub v0.9.26 without Family PIN'; git push
