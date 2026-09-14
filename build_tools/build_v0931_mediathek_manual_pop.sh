#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.30.ipk"
T=/tmp/epimedia0931
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
if 'PLUGIN_VERSION = "0.9.30"' not in t:
    raise SystemExit('Expected v0.9.30 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.30"','PLUGIN_VERSION = "0.9.31"',1)

old='''    def safeClose(self):
        # Keep the BACK path deliberately minimal.  Record the transition before
        # Enigma2 owns teardown so a later GUI restart can be diagnosed.
        if self._closing:return
        _mediathek_debug("list_close_begin", "%s | %s" % (self.source_kind, self.channel_label))
        self._closing=True
        try:self._load_timer.stop()
        except Exception as error:_mediathek_debug("load_timer_stop_error", str(error))
        try:self._poster_timer.stop()
        except Exception as error:_mediathek_debug("poster_timer_stop_error", str(error))
        _mediathek_debug("list_close_call", "%s | %s" % (self.source_kind, self.channel_label))
        self.close()
'''
new='''    def safeClose(self):
        # OpenATV 7.6 on the tested GigaBlue can enter a broken non-modal state
        # after the normal Screen/Session close path on this Mediathek list.
        # End the current dialog synchronously and pop the existing provider
        # directory from Session.dialog_stack instead.
        if self._closing:return
        self._closing=True
        detail="%s | %s" % (self.source_kind, self.channel_label)
        _mediathek_debug("list_back_begin", detail)
        try:self._load_timer.stop()
        except Exception as error:_mediathek_debug("load_timer_stop_error", str(error))
        try:self._poster_timer.stop()
        except Exception as error:_mediathek_debug("poster_timer_stop_error", str(error))
        session=self.session
        try:
            _mediathek_debug("list_back_state", "current=%s | in_exec=%s | stack=%s" % (
                session.current_dialog is self,
                getattr(session,"in_exec",None),
                len(getattr(session,"dialog_stack",[]) or [])
            ))
            if session.current_dialog is not self:
                raise RuntimeError("Mediathek list is not current dialog")
            if not getattr(session,"in_exec",False):
                raise RuntimeError("Session is not executing Mediathek list")
            if not getattr(session,"dialog_stack",None):
                raise RuntimeError("No parent dialog on stack")
            _mediathek_debug("list_back_execend_begin", detail)
            session.execEnd()
            _mediathek_debug("list_back_execend_ok", detail)
            session.popCurrent()
            _mediathek_debug("list_back_parent_ok", "%s | %s" % (
                session.current_dialog.__class__.__name__ if session.current_dialog is not None else "None",
                getattr(session,"in_exec",None)
            ))
            # The list was opened with instantiateDialog/execDialog and noSkinReload,
            # so Session no longer references it after popCurrent().  Avoid the
            # normal delayed close path here; Python can reclaim it later.
            return
        except Exception as error:
            _mediathek_debug("list_back_error", "%s: %s" % (error.__class__.__name__,str(error)))
            # Do not fall back to the normal Screen close path on this receiver.
            self._closing=False
'''
if old not in t:
    raise SystemExit('v0.9.30 safeClose block not found')
t=t.replace(old,new,1)
p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.31/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.31 synchronous Mediathek back navigation/' "$T/control/control"

python3 -m py_compile "$P"
grep -q 'PLUGIN_VERSION = "0.9.31"' "$P"
grep -q 'session.execEnd()' "$P"
grep -q 'session.popCurrent()' "$P"
grep -q 'list_back_parent_ok' "$P"
grep -q 'list_back_error' "$P"
grep -q 'list_open_mode' "$P"
grep -q 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -q 'fromMovieSelection=False' "$P"
# Rai remains PIN-free; unrelated family/parental features remain intact.
grep -q 'FAMILY_PIN_HASH' "$P"
grep -q 'family_skins_unlocked' "$P"
grep -q '_familyPinEntered' "$P"
python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
a=t.index('class EpiMediathekList(Screen):'); b=t.index('class EpiMediaHubHome(Screen):',a); x=t[a:b]
s=x[x.index('    def safeClose(self):'):x.index('    def selectedEntry(self):')]
if '\n        self.close()' in s or '\n        session.close(' in s:
    raise SystemExit('Unsafe Screen/Session close remains in Mediathek safeClose')
for needle in ('session.execEnd()','session.popCurrent()','list_back_execend_ok','list_back_parent_ok'):
    if needle not in s: raise SystemExit('Manual-pop guard missing: '+needle)
d=t[t.index('class EpiMediathekDirectory(Screen):'):a]
if 'Family · Rai International' in d or '_pin_done' in d:
    raise SystemExit('Rai PIN gate returned')
print('v0.9.31 synchronous Mediathek-back guard: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.31.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"
if ar p EpiMediaHub_v0.9.31.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.31.ipk)
echo "v0.9.31 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.31.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.31.ipk" > EpiMediaHub_v0.9.31.ipk.sha256
printf '{\n  "version": "0.9.31",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.31.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.31.ipk.sha256
rm -f EpiMediaHub_v0.9.30.ipk EpiMediaHub_v0.9.30.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.31 synchronous Mediathek back navigation'
git push
