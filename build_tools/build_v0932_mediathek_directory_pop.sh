#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.31.ipk"
T=/tmp/epimedia0932
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
if 'PLUGIN_VERSION = "0.9.31"' not in t:
    raise SystemExit('Expected v0.9.31 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.31"','PLUGIN_VERSION = "0.9.32"',1)

home_start=t.index('class EpiMediathekHome(Screen):')
dir_start=t.index('class EpiMediathekDirectory(Screen):',home_start)
player_start=t.index('if MoviePlayer is not None:',dir_start)
home=t[home_start:dir_start]
directory=t[dir_start:player_start]

# Open the provider directory as a persistent dialog, matching the now-proven
# v0.9.31 content-list strategy.  This avoids the delayed Session.close path at
# the next BACK level as well.
old_home='''        try:self.session.open(EpiMediathekDirectory,x["id"],x["label"])
        except Exception as e:self.session.open(MessageBox,"Mediathek konnte nicht geöffnet werden:\\n%s"%str(e),MessageBox.TYPE_ERROR,timeout=8)
'''
new_home='''        try:
            dialog=self.session.instantiateDialog(EpiMediathekDirectory,x["id"],x["label"])
            self.session.execDialog(dialog)
            _mediathek_debug("directory_open_mode","persistent_exec | %s | %s" % (clean_text(x.get("id","")),clean_text(x.get("label",""))))
        except Exception as e:
            _mediathek_debug("directory_open_error",str(e))
            try:self.session.open(MessageBox,"Mediathek konnte nicht geöffnet werden:\\n%s"%str(e),MessageBox.TYPE_ERROR,timeout=8)
            except Exception:pass
'''
if old_home not in home:
    raise SystemExit('MediathekHome directory-open block not found')
home=home.replace(old_home,new_home,1)

if '    noSkinReload=True\n' not in directory:
    directory=directory.replace('class EpiMediathekDirectory(Screen):\n','class EpiMediathekDirectory(Screen):\n    noSkinReload=True\n',1)

old_init='Screen.__init__(self,session); self.directory_id=directory_id; self.items=list(MEDIATHEK_DIRS.get(directory_id,[]));'
new_init='Screen.__init__(self,session); self.directory_id=directory_id; self._backing=False; self.items=list(MEDIATHEK_DIRS.get(directory_id,[]));'
if old_init not in directory:
    raise SystemExit('Directory init anchor not found')
directory=directory.replace(old_init,new_init,1)

old_actions='''{"ok":self.openSelected,"green":self.openSelected,"cancel":self.close,"red":self.close,"up":self.keyUp,"down":self.keyDown}'''
new_actions='''{"ok":self.openSelected,"green":self.openSelected,"cancel":self.safeBack,"red":self.safeBack,"up":self.keyUp,"down":self.keyDown}'''
if old_actions not in directory:
    raise SystemExit('Directory ActionMap close bindings not found')
directory=directory.replace(old_actions,new_actions,1)

anchor='''    def openSelected(self):
'''
if anchor not in directory:
    raise SystemExit('Directory openSelected anchor missing')
safe_back='''    def safeBack(self):
        if self._backing:return
        self._backing=True
        detail="%s" % clean_text(self.directory_id)
        _mediathek_debug("directory_back_begin",detail)
        session=self.session
        try:
            _mediathek_debug("directory_back_state","current=%s | in_exec=%s | stack=%s" % (
                session.current_dialog is self,
                getattr(session,"in_exec",None),
                len(getattr(session,"dialog_stack",[]) or [])
            ))
            if session.current_dialog is not self:
                raise RuntimeError("Mediathek directory is not current dialog")
            if not getattr(session,"in_exec",False):
                raise RuntimeError("Session is not executing Mediathek directory")
            if not getattr(session,"dialog_stack",None):
                raise RuntimeError("No parent dialog on stack")
            _mediathek_debug("directory_back_execend_begin",detail)
            session.execEnd()
            _mediathek_debug("directory_back_execend_ok",detail)
            session.popCurrent()
            _mediathek_debug("directory_back_parent_ok","%s | %s" % (
                session.current_dialog.__class__.__name__ if session.current_dialog is not None else "None",
                getattr(session,"in_exec",None)
            ))
            return
        except Exception as error:
            _mediathek_debug("directory_back_error","%s: %s" % (error.__class__.__name__,str(error)))
            self._backing=False

'''
directory=directory.replace(anchor,safe_back+anchor,1)

# Nested provider directories (e.g. German regional broadcasters) use the same
# persistent/open + synchronous-pop model.
old_nested='''        if kind=="dir": self.session.open(EpiMediathekDirectory,x.get("target",""),x.get("label","")); return
'''
new_nested='''        if kind=="dir":
            try:
                dialog=self.session.instantiateDialog(EpiMediathekDirectory,x.get("target",""),x.get("label",""))
                self.session.execDialog(dialog)
                _mediathek_debug("directory_open_mode","persistent_exec | %s | %s" % (clean_text(x.get("target","")),clean_text(x.get("label",""))))
            except Exception as error:
                _mediathek_debug("directory_open_error",str(error))
            return
'''
if old_nested not in directory:
    raise SystemExit('Nested Mediathek directory-open path not found')
directory=directory.replace(old_nested,new_nested,1)

t=t[:home_start]+home+directory+t[player_start:]
p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.32/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.32 safe Mediathek provider back navigation/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.32"' "$P"
grep -q 'directory_back_parent_ok' "$P"
grep -q 'directory_open_mode' "$P"
grep -q 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -q 'list_back_parent_ok' "$P"
grep -q 'fromMovieSelection=False' "$P"
# Rai remains PIN-free; unrelated Family/parental features remain intact.
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
h=t[t.index('class EpiMediathekHome(Screen):'):t.index('class EpiMediathekDirectory(Screen):')]
d=t[t.index('class EpiMediathekDirectory(Screen):'):t.index('if MoviePlayer is not None:',t.index('class EpiMediathekDirectory(Screen):'))]
for needle in ('instantiateDialog(EpiMediathekDirectory','execDialog(dialog)','directory_open_mode'):
    if needle not in h: raise SystemExit('Home persistent-directory guard missing: '+needle)
for needle in ('noSkinReload=True','"cancel":self.safeBack','"red":self.safeBack','directory_back_execend_ok','directory_back_parent_ok','session.execEnd()','session.popCurrent()'):
    if needle not in d: raise SystemExit('Directory safe-back guard missing: '+needle)
if '"cancel":self.close' in d or '"red":self.close' in d:
    raise SystemExit('Unsafe Directory close ActionMap remains')
if 'self.session.open(EpiMediathekDirectory' in d:
    raise SystemExit('Nested temporary Directory open remains')
if 'Family · Rai International' in d or '_pin_done' in d:
    raise SystemExit('Rai PIN gate returned')
print('v0.9.32 Mediathek directory navigation guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.32.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.32.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.32.ipk)
echo "v0.9.32 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.32.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.32.ipk" > EpiMediaHub_v0.9.32.ipk.sha256
printf '{\n  "version": "0.9.32",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.32.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.32.ipk.sha256
rm -f EpiMediaHub_v0.9.31.ipk EpiMediaHub_v0.9.31.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.32 safe Mediathek provider back navigation'
git push
