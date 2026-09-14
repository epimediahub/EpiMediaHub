#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.40.ipk"
T=/tmp/epimedia0941
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
if 'PLUGIN_VERSION = "0.9.40"' not in t:
    raise SystemExit('Expected v0.9.40 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.40"','PLUGIN_VERSION = "0.9.41"',1)

old='''        self._web_setup_auto_shown = False\n        try:\n            self.onLayoutFinish.append(self._autoWebSetupIfEmpty)\n        except Exception:\n            pass\n        try:\n            self.onClose.append(self._stopExpiryJob)'''
new='''        self._web_setup_auto_shown = False\n        self._web_setup_timer = eTimer()\n        connect_timer(self._web_setup_timer, self._autoWebSetupIfEmpty)\n        try:\n            self.onShown.append(self._scheduleAutoWebSetupIfEmpty)\n        except Exception:\n            pass\n        try:\n            self.onClose.append(self._stopWebSetupAutoTimer)\n            self.onClose.append(self._stopExpiryJob)'''
if old not in t:
    raise SystemExit('Web setup lifecycle anchor missing')
t=t.replace(old,new,1)

anchor='''    def _autoWebSetupIfEmpty(self):\n        if self._web_setup_auto_shown:\n            return\n        self._web_setup_auto_shown = True\n'''
replacement='''    def _scheduleAutoWebSetupIfEmpty(self):\n        if self._web_setup_auto_shown:\n            return\n        try:\n            self._web_setup_timer.start(50, True)\n        except Exception:\n            pass\n\n    def _stopWebSetupAutoTimer(self):\n        try:\n            self._web_setup_timer.stop()\n        except Exception:\n            pass\n\n    def _autoWebSetupIfEmpty(self):\n        try:\n            self._web_setup_timer.stop()\n        except Exception:\n            pass\n        if self._web_setup_auto_shown:\n            return\n        # OpenATV 7.6 forbids opening a modal child while the parent is still\n        # being skinned/instantiated. Wait until this screen is the executing\n        # current dialog, then open the automatic web setup.\n        session = self.session\n        if getattr(session, "current_dialog", None) is not self or not getattr(session, "in_exec", False):\n            try:\n                self._web_setup_timer.start(100, True)\n            except Exception:\n                pass\n            return\n        self._web_setup_auto_shown = True\n'''
if anchor not in t:
    raise SystemExit('Auto web setup method anchor missing')
t=t.replace(anchor,replacement,1)

# Add release notes if the dict exists.
notes_anchor='_RELEASE_NOTES = {'
if notes_anchor in t:
    notes='''_RELEASE_NOTES = {\n    "0.9.41": {\n        "de": ["Start-Crash bei leerer Playlist-Verwaltung behoben: Das automatische QR/Web-Setup öffnet erst, wenn der Playlist-Screen vollständig modal aktiv ist.", "OpenATV-7.6-Schutz: current_dialog/in_exec werden geprüft; falls nötig wird das Öffnen per Enigma2-Timer verschoben.", "Audio-Fix, Mediathek, EPG/Replay, QR-Web-Setup und Family-Funktionen bleiben erhalten."],\n        "en": ["Fixed startup crash with no playlists: automatic QR/web setup now opens only after the playlist screen is fully active and modal.", "OpenATV 7.6 guard checks current_dialog/in_exec and defers opening via Enigma2 timer when required.", "Audio fix, Mediathek, EPG/replay, QR web setup and Family features are preserved."],\n    },'''
    t=t.replace(notes_anchor,notes,1)

p.write_text(t,encoding='utf-8')
PY

sed -i 's/^Version:.*/Version: 0.9.41/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.41 web setup modal startup fix/' "$T/control/control"

python3 -m py_compile "$P"
find "$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub" -type d -name __pycache__ -prune -exec rm -rf {} +

# New crash-fix guards.
grep -Fq 'PLUGIN_VERSION = "0.9.41"' "$P"
grep -Fq 'self.onShown.append(self._scheduleAutoWebSetupIfEmpty)' "$P"
grep -Fq 'def _scheduleAutoWebSetupIfEmpty(self):' "$P"
grep -Fq 'self._web_setup_timer.start(50, True)' "$P"
grep -Fq 'getattr(session, "current_dialog", None) is not self' "$P"
grep -Fq 'not getattr(session, "in_exec", False)' "$P"
if grep -Fq 'self.onLayoutFinish.append(self._autoWebSetupIfEmpty)' "$P"; then
  echo 'ERROR: unsafe onLayoutFinish auto web setup remains' >&2; exit 1
fi

# Existing critical features/fixes must survive.
grep -Fq 'class EpiWebPlaylistSetup(Screen)' "$P"
grep -Fq 'def _playlist_web_generate_qr' "$P"
grep -Fq 'class EpiMediathekPlayer(MoviePlayer)' "$P"
grep -Fq 'directory_back_parent_ok' "$P"
grep -Fq 'list_back_parent_ok' "$P"
grep -Fq 'home_back_parent_ok' "$P"
grep -Fq 'class EpiEPGGridScreen(Screen)' "$P"
grep -Fq 'def xtream_catchup_url' "$P"
grep -Fq 'RecordTimerEntry' "$P"
grep -Fq 'FAMILY_PIN_HASH' "$P"
grep -Fq 'family_skins_unlocked' "$P"
grep -Fq 'parental_pin_hash' "$P"
grep -Fq 'log_path = "/tmp/epimediahub_update.log"' "$P"
grep -Fq '["opkg", "install", target]' "$P"

python3 - <<'PY'
import os,re
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
if len(re.findall(r'eServiceReference\(\s*1\s*,',t)) != 6:
    raise SystemExit('Expected exactly six native type-1 playback refs from v0.9.39')
if 'eServiceReference(4097, 0, INTRO_SOUND)' not in t:
    raise SystemExit('Intro ref changed unexpectedly')
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.41 regression guards: OK')
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
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.41.ipk)
echo "v0.9.41 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.41.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.41.ipk" > EpiMediaHub_v0.9.41.ipk.sha256
printf '{\n  "version": "0.9.41",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.41.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.41.ipk.sha256
rm -f EpiMediaHub_v0.9.40.ipk EpiMediaHub_v0.9.40.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.41 web setup modal startup fix'
git push
