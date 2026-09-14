#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.33.ipk"
T=/tmp/epimedia0934
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
import os,re
from pathlib import Path
p=Path(os.environ['P'])
t=p.read_text(encoding='utf-8')
if 'PLUGIN_VERSION = "0.9.33"' not in t:
    raise SystemExit('Expected v0.9.33 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.33"','PLUGIN_VERSION = "0.9.34"',1)

# ---- Country overview layout -------------------------------------------------
# Flags occupy x=72..150. Put the actual MenuList in a separate text column
# beginning at x=165 instead of faking spacing with leading blanks.
skin_start=t.index('MEDIATHEK_HOME_SKIN = build_fullscreen_skin(')
skin_end=t.index('MEDIATHEK_DIRECTORY_SKIN = build_fullscreen_skin(',skin_start)
skin=t[skin_start:skin_end]
skin2,n=re.subn(r'list_widget\("list",\s*55,\s*135,\s*650,\s*440,\s*25,\s*58\)',
                'list_widget("list",165,135,540,440,25,58)',skin,count=1)
if n!=1:
    raise SystemExit('Country list layout anchor not found')
t=t[:skin_start]+skin2+t[skin_end:]

home_start=t.index('class EpiMediathekHome(Screen):')
home_end=t.index('class EpiMediathekDirectory(Screen):',home_start)
home=t[home_start:home_end]

if '    noSkinReload=True\n' not in home:
    home=home.replace('class EpiMediathekHome(Screen):\n','class EpiMediathekHome(Screen):\n    noSkinReload=True\n',1)

# Remove the old leading-space workaround so text begins exactly in the new
# dedicated column.
old_list='self["list"]=MenuList(["            "+x["label"] for x in self.items])'
if old_list not in home:
    raise SystemExit('Country list text anchor not found')
home=home.replace(old_list,'self["list"]=MenuList([x["label"] for x in self.items])',1)

old_init='Screen.__init__(self,session); self.items=list(MEDIATHEK_COUNTRIES);'
if old_init not in home:
    raise SystemExit('MediathekHome init anchor not found')
home=home.replace(old_init,'Screen.__init__(self,session); self._backing=False; self.items=list(MEDIATHEK_COUNTRIES);',1)

old_actions='{"ok":self.openSelected,"green":self.openSelected,"cancel":self.close,"red":self.close,"up":self.keyUp,"down":self.keyDown}'
if old_actions not in home:
    raise SystemExit('MediathekHome close ActionMap not found')
home=home.replace(old_actions,'{"ok":self.openSelected,"green":self.openSelected,"cancel":self.safeBack,"red":self.safeBack,"up":self.keyUp,"down":self.keyDown}',1)

anchor='    def openSelected(self):\n'
if anchor not in home:
    raise SystemExit('MediathekHome openSelected anchor missing')
safe_back='''    def safeBack(self):
        if self._backing:return
        self._backing=True
        _mediathek_debug("home_back_begin","Mediathek")
        session=self.session
        try:
            _mediathek_debug("home_back_state","current=%s | in_exec=%s | stack=%s" % (
                session.current_dialog is self,
                getattr(session,"in_exec",None),
                len(getattr(session,"dialog_stack",[]) or [])
            ))
            if session.current_dialog is not self:
                raise RuntimeError("Mediathek home is not current dialog")
            if not getattr(session,"in_exec",False):
                raise RuntimeError("Session is not executing Mediathek home")
            if not getattr(session,"dialog_stack",None):
                raise RuntimeError("No parent dialog on stack")
            _mediathek_debug("home_back_execend_begin","Mediathek")
            session.execEnd()
            _mediathek_debug("home_back_execend_ok","Mediathek")
            session.popCurrent()
            _mediathek_debug("home_back_parent_ok","%s | %s" % (
                session.current_dialog.__class__.__name__ if session.current_dialog is not None else "None",
                getattr(session,"in_exec",None)
            ))
            return
        except Exception as error:
            _mediathek_debug("home_back_error","%s: %s" % (error.__class__.__name__,str(error)))
            self._backing=False

'''
home=home.replace(anchor,safe_back+anchor,1)
t=t[:home_start]+home+t[home_end:]

# ---- Open Mediathek home persistently from the app home ----------------------
# This makes the top-level BACK use the same proven synchronous pop model as
# provider/content screens instead of the delayed Screen.close() lifecycle.
needle='self.session.open(EpiMediathekHome)'
count=t.count(needle)
if count!=1:
    raise SystemExit('Expected exactly one main-home Mediathek open, found %d' % count)
t=t.replace(needle,
'''dialog=self.session.instantiateDialog(EpiMediathekHome)\n            self.session.execDialog(dialog)\n            _mediathek_debug("home_open_mode","persistent_exec")''',1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.34/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.34 safe Mediathek home exit and readable country layout/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.34"' "$P"
grep -q 'home_back_execend_ok' "$P"
grep -q 'home_back_parent_ok' "$P"
grep -q 'home_open_mode' "$P"
grep -q 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -q 'directory_back_parent_ok' "$P"
grep -q 'list_back_parent_ok' "$P"
# Existing Family/parental features remain intact and Rai remains PIN-free.
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
python3 - <<'PY'
import os,re
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
a=t.index('class EpiMediathekHome(Screen):'); b=t.index('class EpiMediathekDirectory(Screen):',a); h=t[a:b]
for needle in ('noSkinReload=True','self._backing=False','"cancel":self.safeBack','"red":self.safeBack','home_back_execend_ok','home_back_parent_ok','session.execEnd()','session.popCurrent()'):
    if needle not in h: raise SystemExit('Mediathek home safe-back guard missing: '+needle)
if '"cancel":self.close' in h or '"red":self.close' in h:
    raise SystemExit('Unsafe MediathekHome close ActionMap remains')
if '["            "+x["label"] for x in self.items]' in h:
    raise SystemExit('Country labels still use leading-space workaround')
ss=t[t.index('MEDIATHEK_HOME_SKIN = build_fullscreen_skin('):t.index('MEDIATHEK_DIRECTORY_SKIN = build_fullscreen_skin(')]
if 'list_widget("list",165,135,540,440,25,58)' not in ss:
    raise SystemExit('Country text-column layout missing')
if 'instantiateDialog(EpiMediathekHome)' not in t or 'execDialog(dialog)' not in t:
    raise SystemExit('Persistent MediathekHome open missing')
print('v0.9.34 Mediathek home navigation/layout guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.34.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.34.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.34.ipk)
echo "v0.9.34 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.34.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.34.ipk" > EpiMediaHub_v0.9.34.ipk.sha256
printf '{\n  "version": "0.9.34",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.34.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.34.ipk.sha256
rm -f EpiMediaHub_v0.9.33.ipk EpiMediaHub_v0.9.33.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.34 safe Mediathek home exit and country layout'
git push
