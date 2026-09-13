#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.29.ipk"
T=/tmp/epimedia0930
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
if 'PLUGIN_VERSION = "0.9.29"' not in t:
    raise SystemExit('Expected v0.9.29 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.29"','PLUGIN_VERSION = "0.9.30"',1)

# OpenATV destroys session.open() dialogs in Session.processDelay() before the
# parent screen is resumed.  The receiver logs show the Mediathek list reaches
# self.close(), then Enigma is left non-executing before the directory returns.
# Execute content lists as non-temporary dialogs instead.  Closing them pops the
# existing directory back from the stack without running Screen.doClose() on the
# content list at that transition.
old='''        if kind=="dir": self.session.open(EpiMediathekDirectory,x.get("target",""),x.get("label","")); return
        if kind in ("mvw","rai"): self.session.open(EpiMediathekList,x.get("channel",""),x.get("label",""),"",kind); return
'''
new='''        if kind=="dir": self.session.open(EpiMediathekDirectory,x.get("target",""),x.get("label","")); return
        if kind in ("mvw","rai"):
            try:
                dialog=self.session.instantiateDialog(EpiMediathekList,x.get("channel",""),x.get("label",""),"",kind)
                self.session.execDialog(dialog)
                _mediathek_debug("list_open_mode","persistent_exec | %s | %s" % (clean_text(kind),clean_text(x.get("label",""))))
            except Exception as error:
                _mediathek_debug("list_open_error",str(error))
                try:self.session.open(MessageBox,"Mediathek konnte nicht geöffnet werden:\\n%s"%str(error),MessageBox.TYPE_ERROR,timeout=7)
                except Exception:pass
            return
'''
if old not in t:
    raise SystemExit('Mediathek list open block not found')
t=t.replace(old,new,1)

# Non-temporary execDialog screens should not be kept forever in Session.allDialogs.
# Defining noSkinReload on the class prevents instantiateDialog from adding the
# list to allDialogs.  Once the dialog is popped and no longer referenced it can
# be garbage-collected naturally, while the dangerous immediate doClose path is
# avoided.
anchor='class EpiMediathekList(Screen):\n'
if anchor not in t:
    raise SystemExit('EpiMediathekList anchor missing')
t=t.replace(anchor,'class EpiMediathekList(Screen):\n    noSkinReload=True\n',1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.30/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.30 safe Mediathek back navigation/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.30"' "$P"
grep -q 'dialog=self.session.instantiateDialog(EpiMediathekList' "$P"
grep -q 'self.session.execDialog(dialog)' "$P"
grep -q 'noSkinReload=True' "$P"
grep -q 'list_open_mode' "$P"
grep -q 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -q 'fromMovieSelection=False' "$P"
# Rai remains PIN-free; unrelated Family/parental features remain intact.
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
a=t.index('class EpiMediathekDirectory(Screen):'); b=t.index('class EpiMediathekList(Screen):',a); d=t[a:b]
if 'self.session.open(EpiMediathekList' in d:
    raise SystemExit('Temporary MediathekList session.open path still present')
if 'instantiateDialog(EpiMediathekList' not in d or 'execDialog(dialog)' not in d:
    raise SystemExit('Persistent Mediathek list navigation missing')
if 'Family · Rai International' in d or '_pin_done' in d:
    raise SystemExit('Rai PIN gate returned')
l=t[b:t.index('class EpiMediaHubHome(Screen):',b)]
if 'noSkinReload=True' not in l:
    raise SystemExit('Mediathek list noSkinReload guard missing')
print('v0.9.30 Mediathek persistent-navigation guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.30.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.30.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.30.ipk)
echo "v0.9.30 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.30.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.30.ipk" > EpiMediaHub_v0.9.30.ipk.sha256
printf '{\n  "version": "0.9.30",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.30.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.30.ipk.sha256
rm -f EpiMediaHub_v0.9.29.ipk EpiMediaHub_v0.9.29.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.30 safe Mediathek back navigation'
git push
