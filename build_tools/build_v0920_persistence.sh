#!/usr/bin/env bash
set -euo pipefail

WORKSPACE="${GITHUB_WORKSPACE:-$(pwd)}"
ROOT=/tmp/epimedia0920/data/usr/lib/enigma2/python/Plugins/Extensions/EpiMediaHub
PLUGIN="$ROOT/plugin.py"

rm -rf /tmp/epimedia0920
mkdir -p /tmp/epimedia0920/{ar,data,control,pkg}
cd /tmp/epimedia0920/ar
ar x "$WORKSPACE/EpiMediaHub_v0.9.19.ipk"
tar -xzf data.tar.gz -C ../data
tar -xzf control.tar.gz -C ../control
cp debian-binary ../pkg/debian-binary

# User playlists/config must never be package-owned. The old .keep made opkg
# treat /etc/enigma2/EpiMediaHub/playlists as package data during reinstall.
rm -rf /tmp/epimedia0920/data/etc/enigma2/EpiMediaHub
rmdir /tmp/epimedia0920/data/etc/enigma2 2>/dev/null || true
rmdir /tmp/epimedia0920/data/etc 2>/dev/null || true

export PLUGIN
python3 - <<'PY'
import os
from pathlib import Path
p=Path(os.environ['PLUGIN'])
t=p.read_text(encoding='utf-8')
if 'PLUGIN_VERSION = "0.9.19"' not in t:
    raise SystemExit('Expected v0.9.19 base')
t=t.replace('PLUGIN_VERSION = "0.9.19"','PLUGIN_VERSION = "0.9.20"',1)
old='''    rc = subprocess.call(["opkg", "install", "--force-reinstall", target])
    try: os.remove(target)
    except Exception: pass
    if rc != 0:
        raise Exception("opkg konnte das Update nicht installieren (Code %d)." % rc)
    return True
'''
new='''    # Preserve all user-owned Epi MediaHub state around opkg. Older packages
    # accidentally shipped a .keep inside the playlist directory, so some opkg
    # reinstall paths could remove that directory while replacing package data.
    backup_root = "/tmp/epimediahub-update-backup"
    backup_pairs = [
        (DATA_DIR, "data"),
        ("/etc/enigma2/EpiMediaHub", "imports"),
    ]
    try:
        if os.path.isdir(backup_root):
            shutil.rmtree(backup_root)
        os.makedirs(backup_root)
        for source, name in backup_pairs:
            if os.path.exists(source):
                shutil.copytree(source, os.path.join(backup_root, name))
    except Exception:
        pass

    rc = subprocess.call(["opkg", "install", "--force-reinstall", target])

    # Restore user data even if the package manager touched one of the folders.
    try:
        for destination, name in backup_pairs:
            saved = os.path.join(backup_root, name)
            if not os.path.isdir(saved):
                continue
            if not os.path.isdir(destination):
                os.makedirs(destination)
            subprocess.call(["cp", "-a", saved + "/.", destination + "/"])
    except Exception:
        pass
    try:
        if os.path.isdir(backup_root):
            shutil.rmtree(backup_root)
    except Exception:
        pass
    try: os.remove(target)
    except Exception: pass
    if rc != 0:
        raise Exception("opkg konnte das Update nicht installieren (Code %d)." % rc)
    return True
'''
if old not in t:
    raise SystemExit('Updater install block not found')
t=t.replace(old,new,1)
anchor='_RELEASE_NOTES = {\n'
if anchor in t:
    notes='''_RELEASE_NOTES = {\n    "0.9.20": {\n        "de": ["Sicherheitsfix für Updates: Playlists, Profile und Einstellungen werden vor Paketwechseln gesichert und danach wiederhergestellt.", "Der Playlist-Ordner gehört nicht mehr zum IPK-Paket und kann von opkg bei Updates nicht mehr als Paketinhalt entfernt werden."],\n        "en": ["Update safety fix: playlists, profiles and settings are backed up before package replacement and restored afterwards.", "The playlist directory is no longer package-owned, preventing opkg from removing it as package content during updates."],\n        "tr": ["Güncelleme güvenlik düzeltmesi: oynatma listeleri, profiller ve ayarlar paket değişiminden önce yedeklenir ve sonra geri yüklenir.", "Oynatma listesi klasörü artık IPK paketine ait değildir."],\n        "it": ["Correzione sicurezza aggiornamenti: playlist, profili e impostazioni vengono salvati prima della sostituzione del pacchetto e ripristinati dopo.", "La cartella playlist non appartiene più al pacchetto IPK."],\n        "es": ["Corrección de seguridad de actualizaciones: listas, perfiles y ajustes se respaldan antes del cambio de paquete y se restauran después.", "La carpeta de listas ya no pertenece al paquete IPK."]\n    },\n'''
    t=t.replace(anchor,notes,1)
p.write_text(t,encoding='utf-8')
PY

# Package-level belt-and-suspenders protection. New preinst snapshots existing
# state before unpacking; postinst restores it and only creates defaults when
# the user truly has no file yet.
cat > /tmp/epimedia0920/control/preinst <<'SH'
#!/bin/sh
set -e
BACK=/tmp/epimediahub-package-backup
rm -rf "$BACK"
mkdir -p "$BACK"
if [ -d /etc/enigma2/EpiMediaHub ]; then
    cp -a /etc/enigma2/EpiMediaHub "$BACK/imports" 2>/dev/null || true
fi
if [ -d /etc/enigma2/epimediahub ]; then
    cp -a /etc/enigma2/epimediahub "$BACK/data" 2>/dev/null || true
fi
exit 0
SH
chmod 755 /tmp/epimedia0920/control/preinst

cat > /tmp/epimedia0920/control/postinst <<'SH'
#!/bin/sh
set -e
ROOT=/etc/enigma2/EpiMediaHub
DATA=/etc/enigma2/epimediahub
BACK=/tmp/epimediahub-package-backup
mkdir -p "$ROOT/playlists" "$DATA"
if [ -d "$BACK/imports" ]; then
    cp -a "$BACK/imports/." "$ROOT/" 2>/dev/null || true
fi
if [ -d "$BACK/data" ]; then
    cp -a "$BACK/data/." "$DATA/" 2>/dev/null || true
fi
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
rm -rf "$BACK" 2>/dev/null || true
exit 0
SH
chmod 755 /tmp/epimedia0920/control/postinst

sed -i 's/^Version:.*/Version: 0.9.20/' /tmp/epimedia0920/control/control
sed -i 's/^Description:.*/Description: Epi MediaHub - v0.9.20 playlist persistence safety fix/' /tmp/epimedia0920/control/control
python3 -m py_compile "$PLUGIN"
grep -q 'PLUGIN_VERSION = "0.9.20"' "$PLUGIN"
grep -q 'epimediahub-update-backup' "$PLUGIN"
if find /tmp/epimedia0920/data/etc -type f 2>/dev/null | grep -q .; then
    echo 'ERROR: v0.9.20 still owns files under /etc' >&2
    find /tmp/epimedia0920/data/etc -type f >&2 || true
    exit 1
fi

tar --owner=0 --group=0 -czf /tmp/epimedia0920/pkg/control.tar.gz -C /tmp/epimedia0920/control .
tar --owner=0 --group=0 -czf /tmp/epimedia0920/pkg/data.tar.gz -C /tmp/epimedia0920/data .
cd /tmp/epimedia0920/pkg
ar r "$WORKSPACE/EpiMediaHub_v0.9.20.ipk" debian-binary control.tar.gz data.tar.gz >/dev/null
cd "$WORKSPACE"
SIZE=$(stat -c%s EpiMediaHub_v0.9.20.ipk)
echo "v0.9.20 size: $SIZE bytes"
if [ "$SIZE" -gt 25165824 ]; then
    echo 'ERROR: v0.9.20 exceeds 24 MiB guard' >&2
    exit 1
fi
SHA=$(sha256sum EpiMediaHub_v0.9.20.ipk | awk '{print $1}')
echo "$SHA  EpiMediaHub_v0.9.20.ipk" > EpiMediaHub_v0.9.20.ipk.sha256
python3 - <<PY
import json
p='update.json'
d=json.load(open(p,encoding='utf-8'))
d['version']='0.9.20'
d['url']='https://raw.githubusercontent.com/epimediahub/EpiMediaHub/main/EpiMediaHub_v0.9.20.ipk'
d['sha256']='$SHA'
open(p,'w',encoding='utf-8').write(json.dumps(d,indent=2)+'\n')
PY
sha256sum -c EpiMediaHub_v0.9.20.ipk.sha256
rm -f EpiMediaHub_v0.9.19.ipk EpiMediaHub_v0.9.19.ipk.sha256
rm -f .github/workflows/inspect-enigma-v0919-persistence.yml inspection/v0919-persistence.txt

git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A EpiMediaHub_v0.9.19.ipk EpiMediaHub_v0.9.19.ipk.sha256 EpiMediaHub_v0.9.20.ipk EpiMediaHub_v0.9.20.ipk.sha256 update.json .github/workflows/inspect-enigma-v0919-persistence.yml inspection/v0919-persistence.txt
git commit -m 'Publish EpiMediaHub v0.9.20 playlist persistence fix'
git push
