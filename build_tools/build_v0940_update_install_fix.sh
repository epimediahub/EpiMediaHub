#!/usr/bin/env bash
set -euo pipefail

W="${GITHUB_WORKSPACE:-$(pwd)}"
B="$W/EpiMediaHub_v0.9.39.ipk"
T=/tmp/epimedia0940
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

if 'PLUGIN_VERSION = "0.9.39"' not in t:
    raise SystemExit('Expected v0.9.39 base not found')
t=t.replace('PLUGIN_VERSION = "0.9.39"','PLUGIN_VERSION = "0.9.40"',1)

# Replace the old full /tmp backup + force-reinstall updater path. Persistent
# EpiMediaHub data is deliberately not package-owned, so copying the whole data
# tree (including caches) is both unnecessary and can exhaust RAM-backed /tmp.
pattern=re.compile(
    r'    # Preserve all user-owned Epi MediaHub state around opkg\..*?'
    r'    if rc != 0:\n'
    r'        raise Exception\("opkg konnte das Update nicht installieren \(Code %d\)\." % rc\)\n'
    r'    return True',
    re.S
)
replacement='''    # Persistent settings/playlists are not package-owned. Do not duplicate the
    # complete data/cache tree into RAM-backed /tmp before every package update.
    log_path = "/tmp/epimediahub_update.log"
    for stale in ("/tmp/epimediahub-update-backup", "/tmp/epimediahub-package-backup"):
        try:
            if os.path.isdir(stale):
                shutil.rmtree(stale)
        except Exception:
            pass

    output = ""
    rc = 255
    try:
        process = subprocess.Popen(
            ["opkg", "install", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
        raw = process.communicate()[0]
        rc = int(process.returncode or 0)
        if isinstance(raw, bytes):
            output = raw.decode("utf-8", "ignore")
        else:
            output = str(raw or "")
    except Exception as error:
        output = "%s: %s" % (error.__class__.__name__, str(error))
        rc = 255

    try:
        with open(log_path, "w") as handle:
            handle.write(output)
    except Exception:
        pass
    try:
        os.remove(target)
    except Exception:
        pass

    if rc != 0:
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        detail = "\\n".join(lines[-5:]) if lines else "Keine opkg-Ausgabe verfügbar."
        raise Exception("opkg-Fehler %d:\\n%s\\nLog: %s" % (rc, detail, log_path))
    return True'''
t,n=pattern.subn(lambda _match: replacement,t,count=1)
if n != 1:
    raise SystemExit('Updater backup/install block anchor missing or ambiguous: %d' % n)

notes='''_RELEASE_NOTES = {\n    "0.9.40": {\n        "de": ["Updater-Speicherfix: keine doppelte Vollsicherung von EPG-, Picon- und Metadaten-Caches mehr nach /tmp; das verhindert opkg-Abbrüche auf Boxen mit knappem temporärem Speicher.", "Der Updater protokolliert künftig die echte opkg-Ausgabe unter /tmp/epimediahub_update.log und zeigt bei Fehlern die letzten Meldungen direkt an.", "Audio-Kompatibilitätsfix aus v0.9.39 sowie Mediathek, EPG/Replay, QR-Web-Setup und Family-Funktionen bleiben erhalten."],\n        "en": ["Updater memory fix: no more duplicate full backups of EPG, picon and metadata caches to /tmp, preventing opkg failures on receivers with limited temporary storage.", "The updater now logs real opkg output to /tmp/epimediahub_update.log and shows the last error lines directly.", "The v0.9.39 audio compatibility fix plus Mediathek, EPG/replay, QR web setup and Family features are preserved."],\n        "tr": ["Güncelleyici bellek düzeltmesi: EPG, picon ve meta veri önbellekleri artık /tmp içine iki kez tam olarak yedeklenmiyor; sınırlı geçici bellekte opkg hataları önleniyor.", "Güncelleyici gerçek opkg çıktısını /tmp/epimediahub_update.log dosyasına kaydeder ve son hata satırlarını gösterir.", "v0.9.39 ses düzeltmesi ile Mediathek, EPG/tekrar, QR web kurulumu ve Family özellikleri korunur."],\n        "it": ["Correzione memoria updater: niente più doppio backup completo delle cache EPG, picon e metadati in /tmp, evitando errori opkg sui ricevitori con memoria temporanea limitata.", "L'updater salva ora l'output reale di opkg in /tmp/epimediahub_update.log e mostra direttamente le ultime righe di errore.", "Restano invariati il fix audio v0.9.39, Mediathek, EPG/replay, setup web QR e funzioni Family."],\n        "es": ["Corrección de memoria del actualizador: ya no se duplican copias completas de cachés EPG, picon y metadatos en /tmp, evitando fallos de opkg con poco espacio temporal.", "El actualizador guarda la salida real de opkg en /tmp/epimediahub_update.log y muestra las últimas líneas de error.", "Se conservan el arreglo de audio v0.9.39, Mediathek, EPG/replay, configuración web QR y funciones Family."],\n    },'''
if '_RELEASE_NOTES = {' not in t:
    raise SystemExit('Release notes anchor missing')
t=t.replace('_RELEASE_NOTES = {',notes,1)

p.write_text(t,encoding='utf-8')
PY

# Package hooks: no full user-data backup. The incoming package does not own
# these directories, so a legacy backup made by the old updater can be removed
# before extraction to free /tmp immediately.
cat > "$T/control/preinst" <<'SH'
#!/bin/sh
rm -rf /tmp/epimediahub-package-backup /tmp/epimediahub-update-backup 2>/dev/null || true
exit 0
SH
chmod 755 "$T/control/preinst"

cat > "$T/control/postinst" <<'SH'
#!/bin/sh
set -e
ROOT=/etc/enigma2/EpiMediaHub
DATA=/etc/enigma2/epimediahub
mkdir -p "$ROOT/playlists" "$DATA"
FILE="$ROOT/playlists.txt"
if [ ! -e "$FILE" ]; then
    cat > "$FILE" <<'EOF'
# Epi MediaHub - einfache Playlist-Verwaltung
# Eine Playlist pro Zeile: M3U-PLUS-URL # Playlistname
# Beispiel:
# http://server:port/get.php?username=USER&password=PASS&type=m3u_plus&output=ts # Wohnzimmer
EOF
    chmod 600 "$FILE" 2>/dev/null || true
fi
exit 0
SH
chmod 755 "$T/control/postinst"

sed -i 's/^Version:.*/Version: 0.9.40/' "$T/control/control"
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.40 updater memory and opkg diagnostics fix/' "$T/control/control"

python3 -m py_compile "$P"
# Do not ship build-runner-specific Python bytecode; Enigma2 will compile locally.
find "$T/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub" -type d -name __pycache__ -prune -exec rm -rf {} +

# New updater guards.
grep -Fq 'PLUGIN_VERSION = "0.9.40"' "$P"
grep -Fq '["opkg", "install", target]' "$P"
grep -Fq 'log_path = "/tmp/epimediahub_update.log"' "$P"
grep -Fq 'subprocess.PIPE' "$P"
grep -Fq 'stderr=subprocess.STDOUT' "$P"
grep -Fq 'opkg-Fehler %d:' "$P"
if grep -Fq '["opkg", "install", "--force-reinstall", target]' "$P"; then
  echo 'ERROR: force-reinstall updater path remains' >&2; exit 1
fi
if grep -Fq 'shutil.copytree(source, os.path.join(backup_root, name))' "$P"; then
  echo 'ERROR: full updater data backup remains' >&2; exit 1
fi
if grep -Fq 'BACK=/tmp/epimediahub-package-backup' "$T/control/preinst"; then
  echo 'ERROR: package preinst still performs duplicate full backup' >&2; exit 1
fi
grep -Fq 'rm -rf /tmp/epimediahub-package-backup /tmp/epimediahub-update-backup' "$T/control/preinst"
sh -n "$T/control/preinst"
sh -n "$T/control/postinst"

# v0.9.39 native playback/audio change must survive exactly.
python3 - <<'PY'
import os,re
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
if len(re.findall(r'eServiceReference\(\s*1\s*,',t)) != 6:
    raise SystemExit('Expected exactly six native type-1 playback refs from v0.9.39')
if 'eServiceReference(4097, 0, INTRO_SOUND)' not in t:
    raise SystemExit('Intro local service ref changed unexpectedly')
if 'eServiceReference(4097, 0, url)' not in t:
    raise SystemExit('Recording/timer service ref changed unexpectedly')
print('v0.9.40 audio regression guard: OK')
PY

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
grep -Fq 'list_widget("list",160,130,570,465,23,50)' "$P"
grep -Fq 'self["list"]=MenuList([x["label"] for x in self.items])' "$P"

python3 - <<'PY'
import os
from pathlib import Path
t=Path(os.environ['P']).read_text(encoding='utf-8')
ms=t.index('class EpiMediathekHome(Screen):'); me=t.index('class EpiMediaHubHome(Screen):',ms); m=t[ms:me]
if '_pin_done' in m or ('Rai' in m and 'openWithCallback(self._pin' in m):
    raise SystemExit('Rai provider PIN gate reintroduced')
print('v0.9.40 feature regression guards: OK')
PY

tar --owner=0 --group=0 -czf "$T/pkg/control.tar.gz" -C "$T/control" .
tar --owner=0 --group=0 -czf "$T/pkg/data.tar.gz" -C "$T/data" .
cd "$T/pkg"
ar r "$W/EpiMediaHub_v0.9.40.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$W"

# Package integrity / persistence guards.
ar t EpiMediaHub_v0.9.40.ipk | grep -Fxq debian-binary
ar t EpiMediaHub_v0.9.40.ipk | grep -Fxq control.tar.gz
ar t EpiMediaHub_v0.9.40.ipk | grep -Fxq data.tar.gz
if ar p EpiMediaHub_v0.9.40.ipk data.tar.gz | tar -tzf - | grep -Eq '^\.?/etc/enigma2/(EpiMediaHub|epimediahub)(/|$)'; then
  echo 'ERROR: package owns persistent user-data paths' >&2; exit 1
fi
S=$(stat -c%s EpiMediaHub_v0.9.40.ipk)
echo "v0.9.40 size: $S bytes"
[ "$S" -le 25165824 ] || { echo 'ERROR: package exceeds 24 MiB guard' >&2; exit 1; }
H=$(sha256sum EpiMediaHub_v0.9.40.ipk | awk '{print $1}')
echo "$H  EpiMediaHub_v0.9.40.ipk" > EpiMediaHub_v0.9.40.ipk.sha256
printf '{\n  "version": "0.9.40",\n  "url": "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.40.ipk",\n  "sha256": "%s"\n}\n' "$H" > update.json
sha256sum -c EpiMediaHub_v0.9.40.ipk.sha256
rm -f EpiMediaHub_v0.9.39.ipk EpiMediaHub_v0.9.39.ipk.sha256

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git commit -m 'Publish EpiMediaHub v0.9.40 updater install reliability fix'
git push
